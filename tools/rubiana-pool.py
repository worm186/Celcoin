#!/usr/bin/env python3
"""Pool de TESTE da Rubiana (v0). Escuta so em 127.0.0.1. Pagamento: so contabilidade.
Uso: python3 tools/rubiana-pool.py --address <endereco_da_pool> [--share-factor N] [--port P]
     python3 tools/rubiana-pool.py --report
"""
import argparse
import asyncio
import json
import os
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rubiana_common import make_job, rpc, varint  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--cli", default="./build/bin/bitcoin-cli -testnet")
ap.add_argument("--address")
ap.add_argument("--engine", default="./build/bin/rubiana-miner")
ap.add_argument("--port", type=int, default=3333)
ap.add_argument("--share-factor", type=int, default=4)
ap.add_argument("--report", action="store_true")
ap.add_argument("--data", default="pool-data.json")
args = ap.parse_args()
CLI = args.cli.split()
DATA = args.data


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


class Pool:
    def __init__(self, spk):
        self.spk = spk
        self.data = load()
        self.jobs = {}
        self.counter = 0
        self.writers = {}
        self.seen = set()
        self.vlock = asyncio.Lock()
        self.vp = None

    def save(self):
        with open(DATA, "w") as f:
            json.dump(self.data, f, indent=1)

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
                w = (await self.vp.stdout.readline()).decode().split()
                if w and w[0] == "HASH":
                    return w[1] if len(w) > 1 and w[1] != "ERRO" else None

    def send(self, w, obj):
        try:
            w.write((json.dumps(obj) + "\n").encode())
        except Exception:
            pass

    def job_msg(self, jid):
        j = self.jobs[jid]
        return {
            "method": "job",
            "params": {
                "job_id": jid,
                "header76": j["header76"].hex(),
                "target": f"{j['target']:064x}",
                "share_target": f"{j['share']:064x}",
            },
        }

    async def new_job(self):
        t = json.loads(await self.rpcc("getblocktemplate", '{"rules":["segwit"]}'))
        header76, witness, txs = make_job(t, self.spk)
        self.counter += 1
        jid = str(self.counter)
        target = int(t["target"], 16)
        share = min(target * args.share_factor, 2**256 - 1)
        self.jobs[jid] = {
            "header76": header76, "witness": witness, "txs": txs, "height": t["height"],
            "value": t["coinbasevalue"], "target": target, "share": share,
        }
        for old in list(self.jobs)[:-20]:
            del self.jobs[old]
        msg = self.job_msg(jid)
        for w in list(self.writers):
            self.send(w, msg)

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

    async def on_submit(self, addr, p):
        job = self.jobs.get(str(p.get("job_id")))
        if not job:
            return {"accepted": False, "error": "trabalho desconhecido"}
        nonce = int(p["nonce"])
        key = (str(p["job_id"]), nonce)
        if key in self.seen:
            return {"accepted": False, "error": "repetido"}
        self.seen.add(key)
        header80 = job["header76"] + struct.pack("<I", nonce)
        h = await self.verify(header80.hex())
        if not h:
            return {"accepted": False, "error": "falha na conferencia"}
        hv = int.from_bytes(bytes.fromhex(h), "little")
        if hv > job["share"]:
            return {"accepted": False, "error": "share invalido"}
        work = (2**256) / job["share"]
        d = self.data
        d["round_work"][addr] = d["round_work"].get(addr, 0) + work
        d["total_work"][addr] = d["total_work"].get(addr, 0) + work
        d["total_shares"][addr] = d["total_shares"].get(addr, 0) + 1
        is_block = hv <= job["target"]
        if is_block:
            block = header80 + varint(1 + len(job["txs"])) + job["witness"]
            block += b"".join(bytes.fromhex(x["data"]) for x in job["txs"])
            res = await self.rpcc("submitblock", block.hex())
            if res == "":
                d["rounds"].append({"altura": job["height"], "finder": addr, "recompensa": job["value"],
                                    "work": dict(d["round_work"]), "estado": "pendente"})
                d["round_work"] = {}
                print(f"BLOCO {job['height']} encontrado por {addr}", flush=True)
            else:
                is_block = False
        self.save()
        return {"accepted": True, "block": is_block}

    async def handle(self, reader, writer):
        addr = None
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                msg = json.loads(line)
                m, p = msg.get("method"), msg.get("params", {})
                if m == "login":
                    a = p.get("address", "")
                    info = json.loads(await self.rpcc("validateaddress", a))
                    if not info.get("isvalid"):
                        self.send(writer, {"id": msg.get("id"), "error": "endereco invalido"})
                        continue
                    addr = a
                    self.writers[writer] = addr
                    self.send(writer, {"id": msg.get("id"), "result": {"ok": True}})
                    if self.jobs:
                        self.send(writer, self.job_msg(str(self.counter)))
                elif m == "submit" and addr:
                    self.send(writer, {"id": msg.get("id"), "result": await self.on_submit(addr, p)})
        except Exception as e:
            print("conexao encerrada:", e, flush=True)
        finally:
            self.writers.pop(writer, None)
            writer.close()


async def main():
    info = json.loads(rpc(CLI, "validateaddress", args.address))
    if not info.get("isvalid"):
        sys.exit("endereco da pool invalido")
    pool = Pool(bytes.fromhex(info["scriptPubKey"]))
    await pool.start_verifier()
    asyncio.create_task(pool.refresh_loop())
    server = await asyncio.start_server(pool.handle, "127.0.0.1", args.port)
    print(f"pool ouvindo em 127.0.0.1:{args.port} (fator de share {args.share_factor})", flush=True)
    async with server:
        await server.serve_forever()


if args.report:
    report()
else:
    if not args.address:
        sys.exit("informe --address")
    asyncio.run(main())
