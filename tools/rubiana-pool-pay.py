#!/usr/bin/env python3
"""Pagamento da pool Rubiana (v0).
1) credita aos mineradores as rodadas cujo bloco ja amadureceu (100 confirmacoes);
2) paga, numa unica transacao, quem tem saldo igual ou maior que o minimo.
A taxa da rede e dividida entre quem recebe; a pool nao cobra taxa.
Uso: python3 tools/rubiana-pool-pay.py --address <endereco_da_pool> [--cli "..."] [--data pool-data.json] [--min-pay 0.001] [--dry-run]"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rubiana_common import rpc  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--address", required=True)
ap.add_argument("--cli", default="./build/bin/rubiana-cli -testnet")
ap.add_argument("--data", default="pool-data.json")
ap.add_argument("--min-pay", type=float, default=0.001)
ap.add_argument("--dry-run", action="store_true")
args = ap.parse_args()
CLI = args.cli.split()
MIN_SAT = int(round(args.min_pay * 1e8))


def fmt(v):
    return f"{v // 10**8}.{v % 10**8:08d}"


with open(args.data) as f:
    d = json.load(f)
d.setdefault("saldos", {})
d.setdefault("pagamentos", [])
tip = int(rpc(CLI, "getblockcount"))

creditadas = 0
for r in d["rounds"]:
    if r.get("estado") != "pendente" or tip - r["altura"] + 1 < 101:
        continue
    bh = rpc(CLI, "getblockhash", r["altura"])
    blk = json.loads(rpc(CLI, "getblock", bh, 2))
    if not any(o["scriptPubKey"].get("address") == args.address for o in blk["tx"][0]["vout"]):
        r["estado"] = "orfao"
        continue
    total = sum(r["work"].values())
    partes = {a: int(r["recompensa"] * w / total) for a, w in r["work"].items()}
    resto = r["recompensa"] - sum(partes.values())
    partes[max(r["work"], key=r["work"].get)] += resto
    for a, v in partes.items():
        d["saldos"][a] = d["saldos"].get(a, 0) + v
    r["estado"] = "creditado"
    creditadas += 1

pagar = {a: v for a, v in d["saldos"].items() if v >= MIN_SAT}
print(f"rodadas creditadas agora: {creditadas}; a pagar (saldo >= {args.min_pay}): {len(pagar)}")
for a, v in sorted(d["saldos"].items(), key=lambda x: -x[1]):
    print(f"  {a[-8:]}: saldo {fmt(v)}" + (" -> paga" if a in pagar else " (abaixo do minimo)"))

if pagar and not args.dry_run:
    amounts = "{" + ", ".join(f'"{a}": {fmt(v)}' for a, v in pagar.items()) + "}"
    sub = json.dumps(list(pagar))
    try:
        txid = rpc(CLI + ["-named"], "sendmany", f"amounts={amounts}", "fee_rate=1", f"subtractfeefrom={sub}")
    except RuntimeError as e:
        print("ERRO ao pagar:", e)
        txid = None
    if txid:
        for a, v in pagar.items():
            d["saldos"][a] -= v
        d["pagamentos"].append({"txid": txid, "valores": dict(pagar)})
        print(f"PAGO: {len(pagar)} minerador(es), total {fmt(sum(pagar.values()))}, txid {txid}")
with open(args.data, "w") as f:
    json.dump(d, f, indent=1)
