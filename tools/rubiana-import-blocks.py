#!/usr/bin/env python3
"""Envia blocos (um por linha, em hexadecimal) para um no, para testar a validacao.
Uso: python rubiana-import-blocks.py "<rubiana-cli>|<opcoes>" blocos.txt"""
import subprocess
import sys

cli = sys.argv[1].split("|")
for n, linha in enumerate(open(sys.argv[2]), 1):
    bloco = linha.strip()
    if not bloco:
        continue
    r = subprocess.run(cli + ["submitblock", bloco], capture_output=True, text=True)
    saida = r.stdout.strip() or r.stderr.strip()
    print(n, saida if saida else "aceito", flush=True)
