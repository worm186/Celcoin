#!/usr/bin/env python3
"""Pool de TESTE da Rubiana (v1): dificuldade de share por minerador (vardiff) e limite da fila.
Escuta so em 127.0.0.1. O pagamento fica no rubiana-pool-pay.py.
Uso: python3 tools/rubiana-pool.py --address <endereco_da_pool> [--share-seconds 10] [--port P] [--data ARQ]
     python3 tools/rubiana-pool.py --report [--data ARQ]
"""
import argparse
import asyncio
import json
import os
import signal
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rubiana_common import make_job, rpc, varint  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--cli", default="./build/bin/rubiana-cli -testnet")
ap.add_argument("--address")
ap.add_argument("--engine", default="./build/bin/rubiana-miner")
ap.add_argument("--port", type=int, default=3333)
ap.add_argument("--share-seconds", type=float, default=10.0)  # alvo: 1 share a cada N segundos por minerador
ap.add_argument("--init-rate", type=float, default=50.0)  # palpite de H/s de um minerador novo
ap.add_argument("--max-pending", type=int, default=200)  # limite da fila de conferencia
ap.add_argument("--share-factor", type=int, default=0)  # ignorado (compatibilidade com a v0)
ap.add_argument("--report", action="store_true")
ap.add_argument("--data", default="pool-data.json")
args = ap.parse_args()
CLI = args.cli.split()
DATA = args.data
MAXT = 2**256 - 1


def load():
    if os.path.exists(DATA):
        with open(DATA) as f:
            return json.load(f)
    return {"round_work": {}, "total_work": {}, "total_shares": {}, "rounds": []}


def report():
    d = load()
    tot = sum(d["total_work"].values()) or 1
    for a, w in sorted(d["total_work"].items(), key=lambda x: -x[1]):
        print(f"{a}: {d['total_shares'].get(a, 0)} shares, {100 * w / tot:.1f}% do trabalho")
    print(f"blocos encontrados pela pool: {len(d['rounds'])}")
    for r in d["rounds"][-10:]:
        tw = sum(r["work"].values()) or 1
        partes = ", ".join(f"{a[-6:]}={r['recompensa'] * w / tw / 1e8:.4f}" for a, w in r["work"].items())
        print(f"  bloco {r['altura']} (recompensa {r['recompensa'] / 1e8:.2f}): {partes}")


class Miner:
    def __init__(self, writer, addr, share):
        self.writer = writer
        self.addr = addr
        self.share = share  # alvo de share atual (inteiro; menor = mais dificil)
        self.t0 = time.time()
        self.times = []  # instantes dos shares aceitos na janela atual
        self.assigned = {}  # job_id -> alvos entregues (do mais antigo ao mais novo)
        self.last_penalty = 0.0


class Pool:
    def __init__(self, spk):
        self.spk = spk
        self.data = load()
        self.jobs = {}
        self.seen = {}
        self.counter = 0
        self.cur = None
        self.miners = {}
        self.vlock = asyncio.Lock()
        self.vp = None
        self.pending = 0
        self.dirty = False
        self.tasks = set()

    def save(self):
        with open(DATA, "w") as f:
            json.dump(self.data, f, indent=1)
        self.dirty = False

    async def rpcc(self, *a):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: rpc(CLI, *a))

    async def start_verifier(self):
        self.vp = await asyncio.create_subprocess_exec(
            args.engine, "--threads", "1", stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE
        )
        await self.vp.stdout.readline()  # READY

    async def verify(self, header80_hex):
        async with self.vlock:
            self.vp.stdin.write((f"HASH {header80_hex}\n").encode())
            await self.vp.stdin.drain()
            while True:
                line = await self.vp.stdout.readline()
                if not line:
                    return None
                w = line.decode().split()
                if w and w[0] == "HASH":
                    return w[1] if len(w) > 1 and w[1] != "ERRO" else None

    def send(self, w, obj):
        try:
            w.write((json.dumps(obj) + "\n").encode())
        except Exception:
            pass

    def send_job(self, m, jid):
        j = self.jobs[jid]
        m.assigned.setdefault(jid, []).append(m.share)
        for old in list(m.assigned):
            if old not in self.jobs:
                del m.assigned[old]
        self.send(m.writer, {"method": "job", "params": {
            "job_id": jid, "header76": j["header76"].hex(),
            "target": f"{j['target']:064x}", "share_target": f"{m.share:064x}"}})

    async def new_job(self):
        t = json.loads(await self.rpcc("getblocktemplate", '{"rules":["segwit"]}'))
        header76, witness, txs = make_job(t, self.spk)
        self.counter += 1
        jid = str(self.counter)
        self.jobs[jid] = {"header76": header76, "witness": witness, "txs": txs, "height": t["height"],
                          "value": t["coinbasevalue"], "target": int(t["target"], 16)}
        self.cur = jid
        for old in list(self.jobs)[:-20]:
            del self.jobs[old]
            self.seen.pop(old, None)
        for m in list(self.miners.values()):
            self.send_job(m, jid)

    async def refresh_loop(self):
        last_tip, last_t = None, 0.0
        while True:
            try:
                tip = await self.rpcc("getbestblockhash")
                if tip != last_tip or time.time() - last_t > 30:
                    await self.new_job()
                    last_tip, last_t = tip, time.time()
            except Exception as e:
                print("erro no no:", e, flush=True)
            await asyncio.sleep(1)

    async def vardiff_loop(self):
        while True:
            await asyncio.sleep(5)
            now = time.time()
            for m in list(self.miners.values()):
                m.times = [x for x in m.times if now - x <= 60]
                elapsed = now - m.t0
                if elapsed < 30:
                    continue
                ratio = (len(m.times) / min(60.0, elapsed)) * args.share_seconds
                if not m.times:
                    ratio = 0.25
                if 0.7 <= ratio <= 1.4:
                    continue
                ratio = max(0.25, min(4.0, ratio))
                m.share = max(1, min(MAXT, int(m.share / ratio)))
                m.t0 = now
                m.times = []
                if self.cur:
                    self.send_job(m, self.cur)
            if self.dirty:
                self.save()

    async def on_submit(self, m, p):
        jid = str(p.get("job_id"))
        job = self.jobs.get(jid)
        if not job:
            return {"accepted": False, "error": "trabalho desconhecido"}
        nonce = int(p["nonce"])
        seen = self.seen.setdefault(jid, set())
        if nonce in seen:
            return {"accepted": False, "error": "repetido"}
        seen.add(nonce)
        if self.pending >= args.max_pending:
            now = time.time()
            if now - m.last_penalty > 5:
                m.last_penalty = now
                m.share = max(1, m.share // 4)
                m.t0 = now
                m.times = []
                if self.cur:
                    self.send_job(m, self.cur)
            return {"accepted": False, "error": "fila cheia"}
        self.pending += 1
        try:
            h = await self.verify((job["header76"] + struct.pack("<I", nonce)).hex())
        finally:
            self.pending -= 1
        if not h:
            return {"accepted": False, "error": "falha na conferencia"}
        hv = int.from_bytes(bytes.fromhex(h), "little")
        used = None
        for t in reversed(m.assigned.get(jid, [])):
            if hv <= t:
                used = t
                break
        is_block = hv <= job["target"]
        if used is None and is_block:
            used = job["target"]
        if used is None:
            return {"accepted": False, "error": "share invalido"}
        d = self.data
        work = (2**256) / used
        d["round_work"][m.addr] = d["round_work"].get(m.addr, 0) + work
        d["total_work"][m.addr] = d["total_work"].get(m.addr, 0) + work
        d["total_shares"][m.addr] = d["total_shares"].get(m.addr, 0) + 1
        m.times.append(time.time())
        self.dirty = True
        if is_block:
            header80 = job["header76"] + struct.pack("<I", nonce)
            block = header80 + varint(1 + len(job["txs"])) + job["witness"]
            block += b"".join(bytes.fromhex(x["data"]) for x in job["txs"])
            res = await self.rpcc("submitblock", block.hex())
            if res == "":
                d["rounds"].append({"altura": job["height"], "finder": m.addr, "recompensa": job["value"],
                                    "work": dict(d["round_work"]), "estado": "pendente"})
                d["round_work"] = {}
                self.save()
                print(f"BLOCO {job['height']} encontrado por {m.addr}", flush=True)
            else:
                is_block = False
        return {"accepted": True, "block": is_block}

    async def reply_submit(self, writer, m, msg):
        try:
            res = await self.on_submit(m, msg.get("params", {}))
        except Exception as e:
            res = {"accepted": False, "error": str(e)}
        self.send(writer, {"id": msg.get("id"), "result": res})

    async def handle(self, reader, writer):
        m = None
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                msg = json.loads(line)
                meth, p = msg.get("method"), msg.get("params", {})
                if meth == "login":
                    a = p.get("address", "")
                    info = json.loads(await self.rpcc("validateaddress", a))
                    if not info.get("isvalid"):
                        self.send(writer, {"id": msg.get("id"), "error": "endereco invalido"})
                        continue
                    init = max(1, min(MAXT, int(2**256 / (args.init_rate * args.share_seconds))))
                    m = Miner(writer, a, init)
                    self.miners[writer] = m
                    self.send(writer, {"id": msg.get("id"), "result": {"ok": True}})
                    if self.cur:
                        self.send_job(m, self.cur)
                elif meth == "submit" and m:
                    t = asyncio.create_task(self.reply_submit(writer, m, msg))
                    self.tasks.add(t)
                    t.add_done_callback(self.tasks.discard)
        except Exception as e:
            print("conexao encerrada:", e, flush=True)
        finally:
            self.miners.pop(writer, None)
            writer.close()


async def main():
    info = json.loads(rpc(CLI, "validateaddress", args.address))
    if not info.get("isvalid"):
        sys.exit("endereco da pool invalido")
    pool = Pool(bytes.fromhex(info["scriptPubKey"]))
    await pool.start_verifier()
    loops = [asyncio.create_task(pool.refresh_loop()), asyncio.create_task(pool.vardiff_loop())]
    server = await asyncio.start_server(pool.handle, "127.0.0.1", args.port)
    print(f"pool ouvindo em 127.0.0.1:{args.port} (1 share a cada {args.share_seconds} s por minerador)", flush=True)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for s in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(s, stop.set)
    async with server:
        await stop.wait()
    pool.save()
    for t in loops:
        t.cancel()
    if pool.vp:
        pool.vp.terminate()


if args.report:
    report()
else:
    if not args.address:
        sys.exit("informe --address")
    asyncio.run(main())
