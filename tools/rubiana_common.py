"""Funcoes comuns dos scripts da Rubiana (RPC pelo bitcoin-cli, coinbase, merkle)."""
import hashlib
import os
import struct
import subprocess


def rpc(cli, *a):
    r = subprocess.run(cli + [str(x) for x in a], capture_output=True, text=True)
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
