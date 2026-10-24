#!/usr/bin/env python3
"""Minerador da pool Rubiana (v0). Usa o motor rubiana-miner.
Uso: python3 tools/rubiana-pool-miner.py --address <endereco> [--pool 127.0.0.1:3333] [--threads N] [--full] [--seconds S]"""
import argparse
import json
import socket
import subprocess
import threading
import time

ap = argparse.ArgumentParser()
ap.add_argument("--pool", default="127.0.0.1:3333")
ap.add_argument("--address", required=True)
ap.add_argument("--engine", default="./build/bin/rubiana-miner")
ap.add_argument("--threads", type=int, default=1)
ap.add_argument("--full", action="store_true")
ap.add_argument("--seconds", type=int, default=0)
args = ap.parse_args()

host, port = args.pool.rsplit(":", 1)
sock = socket.create_connection((host, int(port)))
rf = sock.makefile("r")
wlock = threading.Lock()
elock = threading.Lock()
stats = {"enviados": 0, "aceitos": 0, "rejeitados": 0, "blocos": 0}
nid = [1]


def psend(obj):
    with wlock:
        sock.sendall((json.dumps(obj) + "\n").encode())


cmd = [args.engine, "--threads", str(args.threads)] + (["--full"] if args.full else [])
eng = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)


def esend(s):
    with elock:
        eng.stdin.write(s + "\n")
        eng.stdin.flush()


def pool_reader():
    for line in rf:
        try:
            m = json.loads(line)
        except ValueError:
            continue
        if m.get("method") == "job":
            p = m["params"]
            esend(f"JOB {p['job_id']} {p['header76']} {p['target']} {p['share_target']}")
        elif isinstance(m.get("result"), dict) and "accepted" in m["result"]:
            r = m["result"]
            if r["accepted"]:
                stats["aceitos"] += 1
                if r.get("block"):
                    stats["blocos"] += 1
            else:
                stats["rejeitados"] += 1


def engine_reader():
    for line in eng.stdout:
        w = line.split()
        if w and w[0] == "SHARE":
            nid[0] += 1
            stats["enviados"] += 1
            psend({"id": nid[0], "method": "submit", "params": {"job_id": w[1], "nonce": int(w[2])}})


threading.Thread(target=pool_reader, daemon=True).start()
threading.Thread(target=engine_reader, daemon=True).start()
psend({"id": 1, "method": "login", "params": {"address": args.address}})
t0 = time.time()
try:
    while args.seconds == 0 or time.time() - t0 < args.seconds:
        time.sleep(1)
except KeyboardInterrupt:
    pass
time.sleep(2)
esend("QUIT")
print(f"RESUMO: enviados {stats['enviados']}, aceitos {stats['aceitos']}, rejeitados {stats['rejeitados']}, blocos {stats['blocos']}")
