#!/usr/bin/env python3
"""Minerador solo de TESTE da Rubiana, versao 2 (usa o motor rubiana-miner).
Uso:
  python3 tools/rubiana-solo-miner.py "<rubiana-cli e opcoes>" <endereco> <rubiana-miner> [--threads N] [--full] [--blocks N]
"""
import argparse
import hashlib
import json
import os
import queue
import struct
import subprocess
import sys
import threading
import time

ap = argparse.ArgumentParser()
ap.add_argument("cli")
ap.add_argument("address")
ap.add_argument("miner")
ap.add_argument("--threads", type=int, default=1)
ap.add_argument("--full", action="store_true")
ap.add_argument("--blocks", type=int, default=0)
args = ap.parse_args()
CLI = args.cli.split("|") if "|" in args.cli else args.cli.split()


def rpc(*a):
    r = subprocess.run(CLI + [str(x) for x in a], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or r.stdout.strip())
    return r.stdout.strip()


def dsha(b):
    return hashlib.sha256(hashlib.sha256(b).digest()).digest()


def varint(n):
    if n < 0xFD:
        return bytes([n])
    if n <= 0xFFFF:
        return b"\xfd" + struct.pack("<H", n)
    return b"\xfe" + struct.pack("<I", n)


def push_int(n):
    # Altura do bloco no inicio do script da coinbase (regra BIP34).
    if n == 0:
        return b"\x00"
    if 1 <= n <= 16:
        return bytes([0x50 + n])
    data = bytearray()
    while n:
        data.append(n & 0xFF)
        n >>= 8
    if data[-1] & 0x80:
        data.append(0)
    return bytes([len(data)]) + bytes(data)


def build_coinbase(height, value, spk, commitment, extranonce):
    script_sig = push_int(height) + bytes([len(extranonce)]) + extranonce
    vin = b"\x00" * 32 + b"\xff\xff\xff\xff" + varint(len(script_sig)) + script_sig + b"\xff\xff\xff\xff"
    vouts = struct.pack("<q", value) + varint(len(spk)) + spk
    vouts += struct.pack("<q", 0) + varint(len(commitment)) + commitment
    version = struct.pack("<i", 2)
    locktime = struct.pack("<I", 0)
    legacy = version + b"\x01" + vin + b"\x02" + vouts + locktime
    witness = version + b"\x00\x01" + b"\x01" + vin + b"\x02" + vouts + b"\x01\x20" + b"\x00" * 32 + locktime
    return legacy, witness


def merkle_root(hashes):
    while len(hashes) > 1:
        if len(hashes) % 2:
            hashes.append(hashes[-1])
        hashes = [dsha(hashes[i] + hashes[i + 1]) for i in range(0, len(hashes), 2)]
    return hashes[0]


def make_job(t, spk):
    txs = t["transactions"]
    legacy, witness = build_coinbase(
        t["height"], t["coinbasevalue"], spk, bytes.fromhex(t["default_witness_commitment"]), os.urandom(8)
    )
    hashes = [dsha(legacy)] + [bytes.fromhex(x["txid"])[::-1] for x in txs]
    header76 = (
        struct.pack("<i", t["version"])
        + bytes.fromhex(t["previousblockhash"])[::-1]
        + merkle_root(hashes)
        + struct.pack("<II", t["curtime"], int(t["bits"], 16))
    )
    return header76, witness, txs


class Engine:
    def __init__(self):
        cmd = [args.miner, "--threads", str(args.threads)] + (["--full"] if args.full else [])
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        self.q = queue.Queue()
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        for line in self.p.stdout:
            self.q.put(line.split())

    def send(self, line):
        self.p.stdin.write(line + "\n")
        self.p.stdin.flush()

    def stats(self):
        self.send("STATS")
        end = time.time() + 5
        while time.time() < end:
            try:
                m = self.q.get(timeout=1)
            except queue.Empty:
                continue
            if m and m[0] == "STATS":
                return int(m[1]), float(m[2])
        return None


def main():
    info = json.loads(rpc("validateaddress", args.address))
    if not info.get("isvalid"):
        sys.exit("endereco invalido")
    spk = bytes.fromhex(info["scriptPubKey"])
    eng = Engine()
    if eng.q.get(timeout=60)[0] != "READY":
        sys.exit("o motor nao ficou pronto")
    print(f"motor pronto: {args.threads} thread(s), modo {'completo' if args.full else 'leve'}")
    found = 0
    job_id = 0
    last = (0, 0.0)
    try:
        while args.blocks == 0 or found < args.blocks:
            t = json.loads(rpc("getblocktemplate", '{"rules":["segwit"]}'))
            header76, witness, txs = make_job(t, spk)
            job_id += 1
            eng.send(f"JOB {job_id} {header76.hex()} {t['target']}")
            deadline = time.time() + (180 if job_id == 1 else 30)
            nonce = None
            while nonce is None and time.time() < deadline:
                try:
                    m = eng.q.get(timeout=1)
                except queue.Empty:
                    continue
                if m and m[0] == "FOUND" and int(m[1]) == job_id:
                    nonce = int(m[2])
            if nonce is None:
                print("sem resultado neste trabalho; pedindo novo modelo...")
                continue
            block = header76 + struct.pack("<I", nonce) + varint(1 + len(txs)) + witness
            block += b"".join(bytes.fromhex(x["data"]) for x in txs)
            res = rpc("submitblock", block.hex())
            if res == "":
                found += 1
            rate = ""
            s = eng.stats()
            if s and s[1] > last[1]:
                rate = f", ~{(s[0] - last[0]) / (s[1] - last[1]):.0f} H/s"
                last = s
            print(f"bloco {t['height']}: nonce {nonce}, resposta do no: {res or 'aceito'}{rate}")
    except KeyboardInterrupt:
        print("interrompido")
    finally:
        try:
            eng.send("QUIT")
        except Exception:
            pass
    print(f"{found} bloco(s) minerado(s)")


main()
