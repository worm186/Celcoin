#!/usr/bin/env python3
"""Rubiana - minerador solo para PC (v0).
Sobe o no, cria a carteira e minera sozinho para o seu endereco.
Uso: python3 tools/rubiana-mine.py [--rede testnet|regtest] [--threads N] [--full] [--blocks N]
Ctrl+C para parar."""
import argparse
import json
import os
import subprocess
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)

ap = argparse.ArgumentParser()
ap.add_argument("--rede", default="testnet", choices=["testnet", "regtest"])
ap.add_argument("--threads", type=int, default=max(1, (os.cpu_count() or 2) // 2))
ap.add_argument("--full", action="store_true", help="modo completo (precisa de 2 GB de memoria livre)")
ap.add_argument("--blocks", type=int, default=0, help="parar depois de N blocos (0 = ate Ctrl+C)")
ap.add_argument("--bin", default=os.path.join(RAIZ, "build", "bin"))
ap.add_argument("--carteira", default="minerador")
args = ap.parse_args()

flag = ["-" + args.rede]
EXT = ".exe" if os.name == "nt" else ""
daemon = os.path.join(args.bin, "rubianad" + EXT)
cli_path = os.path.join(args.bin, "rubiana-cli" + EXT)
engine = os.path.join(args.bin, "rubiana-miner" + EXT)
for f in (daemon, cli_path, engine):
    if not os.path.exists(f):
        sys.exit("nao encontrei " + f + " (compile primeiro)")
CLI = [cli_path] + flag


def cli(*a, wallet=False):
    cmd = CLI + (["-rpcwallet=" + args.carteira] if wallet else []) + [str(x) for x in a]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, (r.stdout.strip() or r.stderr.strip())


started = False
code, out = cli("getblockcount")
if code != 0 and "-28" not in out:
    print("iniciando o no...", flush=True)
    if os.name == "nt":
        subprocess.Popen([daemon] + flag + ["-dnsseed=0", "-fixedseeds=0"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)
    else:
        subprocess.run([daemon] + flag + ["-daemon", "-dnsseed=0", "-fixedseeds=0"], check=True)
    started = True

t0 = time.time()
while True:
    code, out = cli("getblockcount")
    if code == 0:
        break
    if time.time() - t0 > 180:
        sys.exit("o no demorou demais para ficar pronto: " + out)
    time.sleep(2)
print("no pronto, altura " + out, flush=True)

code, out = cli("loadwallet", args.carteira)
if code != 0 and "already loaded" not in out.lower():
    code, out = cli("createwallet", args.carteira)
    if code != 0:
        sys.exit("nao consegui preparar a carteira: " + out)

pasta = os.path.expanduser("~/.rubiana")
os.makedirs(pasta, exist_ok=True)
arq = os.path.join(pasta, "endereco-" + args.rede + ".txt")
addr = None
if os.path.exists(arq):
    a = open(arq).read().strip()
    code, out = cli("getaddressinfo", a, wallet=True)
    if code == 0 and json.loads(out).get("ismine"):
        addr = a
if not addr:
    code, out = cli("getnewaddress", wallet=True)
    if code != 0:
        sys.exit("nao consegui criar o endereco: " + out)
    addr = out
    open(arq, "w").write(addr + "\n")

modo = "completo" if args.full else "leve"
print("endereco de mineracao: " + addr)
print("minerando solo na " + args.rede + ": " + str(args.threads) + " thread(s), modo " + modo + ". Ctrl+C para parar.", flush=True)

solo = os.path.join(AQUI, "rubiana-solo-miner.py")
cmd = [sys.executable, solo, "|".join(CLI), addr, engine, "--threads", str(args.threads)]
if args.full:
    cmd.append("--full")
if args.blocks > 0:
    cmd += ["--blocks", str(args.blocks)]
try:
    subprocess.run(cmd)
except KeyboardInterrupt:
    pass
finally:
    code, bal = cli("getbalance", wallet=True)
    code2, alt = cli("getblockcount")
    print("\naltura da cadeia: " + alt)
    print("saldo da carteira (so conta o que ja amadureceu, apos 100 blocos): " + bal)
    if started:
        cli("stop")
        print("no encerrado.")
