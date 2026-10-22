#!/usr/bin/env python3
"""Teste do motor v2: gera shares num alvo facil e confere cada um com o comando HASH.
Uso: python3 tools/test-motor.py <rubiana-miner> [threads] [segundos]"""
import os
import queue
import struct
import subprocess
import sys
import threading
import time

MINER = sys.argv[1]
THREADS = sys.argv[2] if len(sys.argv) > 2 else "2"
SECS = int(sys.argv[3]) if len(sys.argv) > 3 else 20
RATE = 70  # H/s esperados no modo leve com 2 threads (so para escolher o alvo do teste)

header76 = struct.pack("<i", 0x20000000) + os.urandom(32) + os.urandom(32) + struct.pack("<II", 1792488689, 0x2000FFFF)
share_hex = (2**256 // RATE).to_bytes(32, "big").hex()
block_hex = (2**256 // (RATE * 16)).to_bytes(32, "big").hex()

p = subprocess.Popen([MINER, "--threads", THREADS], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
q = queue.Queue()
threading.Thread(target=lambda: [q.put(x.split()) for x in p.stdout], daemon=True).start()


def send(s):
    p.stdin.write(s + "\n")
    p.stdin.flush()


def wait(kind, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        try:
            m = q.get(timeout=1)
        except queue.Empty:
            continue
        if m and m[0] == kind:
            return m
    return None


wait("READY")
t0 = time.time()
send(f"JOB 1 {header76.hex()} {block_hex} {share_hex}")
shares = []
blocks = 0
while time.time() < t0 + SECS:
    try:
        m = q.get(timeout=1)
    except queue.Empty:
        continue
    if m[0] == "SHARE":
        shares.append((int(m[2]), m[3], int(m[4])))
    elif m[0] == "FOUND":
        blocks += 1
send("STATS")
st = wait("STATS")
send("STOP")
rate = int(st[1]) / (time.time() - t0) if st else 0
ok = 0
for nonce, h, _ in shares:
    send("HASH " + (header76 + struct.pack("<I", nonce)).hex())
    m = wait("HASH")
    if m and len(m) > 1 and m[1] == h and int.from_bytes(bytes.fromhex(h), "little") <= int(share_hex, 16):
        ok += 1
send("QUIT")
print(f"RESUMO: taxa ~{rate:.0f} H/s, shares {len(shares)}, conferidos pelo HASH {ok}, blocos candidatos {blocks}")
