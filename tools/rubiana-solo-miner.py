#!/usr/bin/env python3
"""Minerador solo de TESTE da Rubiana (prototipo).
Pede o modelo de bloco ao no, procura o nonce com o rubiana-search (RandomX)
e envia o bloco pronto. Uso:
  python3 tools/rubiana-solo-miner.py "<bitcoin-cli e opcoes>" <endereco> <rubiana-search> [blocos]
"""
import hashlib
import json
import os
import struct
import subprocess
import sys
import time

CLI = sys.argv[1].split()
ADDRESS = sys.argv[2]
SEARCH = sys.argv[3]
NBLOCKS = int(sys.argv[4]) if len(sys.argv) > 4 else 1


def rpc(*args):
    r = subprocess.run(CLI + [str(a) for a in args], capture_output=True, text=True)
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


def mine_one(spk):
    t = json.loads(rpc("getblocktemplate", '{"rules":["segwit"]}'))
    height = t["height"]
    txs = t["transactions"]
    extranonce = os.urandom(8)
    legacy, witness = build_coinbase(height, t["coinbasevalue"], spk, bytes.fromhex(t["default_witness_commitment"]), extranonce)
    hashes = [dsha(legacy)] + [bytes.fromhex(x["txid"])[::-1] for x in txs]
    root = merkle_root(hashes)
    header76 = (
        struct.pack("<i", t["version"])
        + bytes.fromhex(t["previousblockhash"])[::-1]
        + root
        + struct.pack("<II", t["curtime"], int(t["bits"], 16))
    )
    start = int.from_bytes(os.urandom(4), "little")  # nonce inicial aleatorio
    t0 = time.time()
    r = subprocess.run([SEARCH, header76.hex(), t["target"], str(start), "100000"], capture_output=True, text=True)
    out = r.stdout.split()
    if not out or out[0] != "FOUND":
        print("nenhum nonce neste lote; pedindo novo modelo...", r.stderr.strip())
        return False
    nonce = int(out[1])
    block = header76 + struct.pack("<I", nonce) + varint(1 + len(txs)) + witness + b"".join(bytes.fromhex(x["data"]) for x in txs)
    res = rpc("submitblock", block.hex())
    print(f"bloco {height}: nonce {nonce}, {time.time() - t0:.1f}s, resposta do no: {res or 'aceito'}")
    return res == ""


def main():
    info = json.loads(rpc("validateaddress", ADDRESS))
    if not info.get("isvalid"):
        sys.exit("endereco invalido")
    spk = bytes.fromhex(info["scriptPubKey"])
    done = 0
    tentativas = 0
    while done < NBLOCKS and tentativas < NBLOCKS * 5:
        tentativas += 1
        if mine_one(spk):
            done += 1
    print(f"{done} bloco(s) minerado(s)")


main()
