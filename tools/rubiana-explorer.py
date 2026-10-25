#!/usr/bin/env python3
"""Explorador de blocos da Rubiana (v0, so leitura). Le do no pelo bitcoin-cli e serve uma pagina web.
Uso: python3 tools/rubiana-explorer.py [--cli "./build/bin/bitcoin-cli -testnet"] [--port 8080]
Para abrir transacoes pelo id, inicie o no com -txindex=1."""
import argparse
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rubiana_common import rpc  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--cli", default="./build/bin/bitcoin-cli -testnet")
ap.add_argument("--port", type=int, default=8080)
args = ap.parse_args()
CLI = args.cli.split()
CACHE = {}
HALVING = 500000
START_REWARD = 86 * 10**8
SAFE = re.compile(r"[0-9a-zA-Z]{1,100}")


def safe(s):
    if not SAFE.fullmatch(s):
        raise ValueError("entrada invalida")
    return s


def js(*a):
    return json.loads(rpc(CLI, *a))


def reward_at(h):
    era = h // HALVING
    return START_REWARD >> era if era < 64 else 0


def supply_at(h):
    total, era = 0, 0
    while h > 0 and era < 64:
        n = min(h, HALVING)
        total += n * (START_REWARD >> era)
        h -= n
        era += 1
    return total


def block_summary(h):
    if h in CACHE:
        return CACHE[h]
    b = js("getblock", h, 2)
    cb = b["tx"][0]
    miner = next((o["scriptPubKey"]["address"] for o in cb["vout"] if "address" in o["scriptPubKey"]), None)
    s = {
        "height": b["height"], "hash": b["hash"], "time": b["time"], "ntx": len(b["tx"]), "size": b["size"],
        "bits": b["bits"], "nonce": b["nonce"], "epoch": b["time"] // 172800, "miner": miner,
        "reward": sum(o["value"] for o in cb["vout"]),
        "txs": [{"txid": t["txid"], "vin": len(t["vin"]), "vout": len(t["vout"]),
                 "out": round(sum(o["value"] for o in t["vout"]), 8)} for t in b["tx"]],
    }
    if b.get("confirmations", 0) > 6:
        CACHE[h] = s
    return s


def api_summary():
    info = js("getblockchaininfo")
    mp = js("getmempoolinfo")
    try:
        hps = float(rpc(CLI, "getnetworkhashps", 60))
    except Exception:
        hps = 0.0
    tip = info["blocks"]
    return {"chain": info["chain"], "blocks": tip, "bits": info["bits"], "hashps": hps, "mempool": mp["size"],
            "reward": reward_at(tip + 1) / 1e8, "supply": supply_at(tip) / 1e8}


def api_blocks(n):
    tip = int(rpc(CLI, "getblockcount"))
    out = []
    for height in range(tip, max(-1, tip - n), -1):
        s = block_summary(rpc(CLI, "getblockhash", height))
        out.append({k: v for k, v in s.items() if k != "txs"})
    return out


def api_block(q):
    safe(q)
    h = rpc(CLI, "getblockhash", q) if q.isdigit() else q
    return block_summary(h)


def api_tx(txid):
    t = js("getrawtransaction", safe(txid), "true")
    return {
        "txid": t["txid"], "blockhash": t.get("blockhash"), "confirmations": t.get("confirmations", 0),
        "vin": [{"coinbase": v["coinbase"]} if "coinbase" in v else {"txid": v["txid"], "vout": v["vout"]} for v in t["vin"]],
        "vout": [{"n": o["n"], "value": o["value"], "address": o["scriptPubKey"].get("address")} for o in t["vout"]],
    }


def api_addr(a):
    safe(a)
    if not js("validateaddress", a).get("isvalid"):
        raise ValueError("endereco invalido")
    r = js("scantxoutset", "start", json.dumps([f"addr({a})"]))
    return {"endereco": a, "saldo": r["total_amount"], "utxos": len(r["unspents"])}


PAGE = r"""<!doctype html>
<html lang="pt-br"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Rubiana - Explorador</title>
<style>
body{font-family:system-ui,sans-serif;margin:0;background:#0f1220;color:#e8eaf6}
header{padding:12px 14px;background:#1a1f3a;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
h1{font-size:18px;margin:0;flex:1;cursor:pointer}
input{padding:8px;border-radius:6px;border:0;flex:1;min-width:160px}
button{padding:8px 12px;border:0;border-radius:6px;background:#7c4dff;color:#fff}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px;padding:10px}
.card{background:#1a1f3a;border-radius:10px;padding:10px}
.card b{display:block;font-size:11px;color:#9fa8da;font-weight:normal}
.card span{font-size:17px}
table{width:100%;border-collapse:collapse;font-size:13px}
td,th{padding:8px 6px;border-bottom:1px solid #2a2f50;text-align:left}
tr.c{cursor:pointer}
tr.c:hover{background:#1a1f3a}
pre{white-space:pre-wrap;word-break:break-all;background:#1a1f3a;padding:12px;border-radius:8px;margin:10px}
.mono{font-family:monospace}
a{color:#b39ddb}
</style></head><body>
<header><h1 onclick="home()">Rubiana - Explorador</h1>
<input id="q" placeholder="altura, hash, txid ou endereço" onkeydown="if(event.key==='Enter')buscar()">
<button onclick="buscar()">Buscar</button></header>
<div class="cards" id="cards"></div>
<div id="conteudo"></div>
<script>
const $=s=>document.querySelector(s);
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const j=async u=>{const r=await fetch(u);return r.json()};
const ago=t=>{const s=Math.max(0,Math.floor(Date.now()/1000)-t);return s<60?s+' s':s<3600?Math.floor(s/60)+' min':s<86400?Math.floor(s/3600)+' h':Math.floor(s/86400)+' d'};
const sh=h=>h?h.slice(0,8)+'..'+h.slice(-6):'-';
const voltar='<a href="#" onclick="home();return false">&lt;- voltar</a>\n\n';
let modo='home';
async function home(){
  modo='home';
  const [s,b]=await Promise.all([j('/api/summary'),j('/api/blocks?n=20')]);
  if(modo!=='home')return;
  if(s.erro||b.erro){$('#conteudo').innerHTML='<pre>'+esc(s.erro||b.erro)+'</pre>';return}
  const tempo=b.length>1?(b[0].time-b[b.length-1].time)/(b.length-1):0;
  const cards=[['Rede',s.chain],['Altura',s.blocks],['Bits (dificuldade)',s.bits],['Taxa de hash (estimada)',s.hashps.toFixed(0)+' H/s'],['Tempo médio de bloco',tempo.toFixed(0)+' s'],['Recompensa',s.reward+' RUBIA'],['Emitido',Math.round(s.supply).toLocaleString('pt-BR')+' de 86.000.000'],['Mempool',s.mempool+' tx'],['Época da chave RandomX',b.length?b[0].epoch:'-']];
  $('#cards').innerHTML=cards.map(c=>'<div class="card"><b>'+c[0]+'</b><span>'+esc(c[1])+'</span></div>').join('');
  $('#conteudo').innerHTML='<table><tr><th>Altura</th><th>Há</th><th>Tx</th><th>Minerador</th><th>Hash</th></tr>'+b.map(x=>'<tr class="c" onclick="bloco(\''+x.hash+'\')"><td>'+x.height+'</td><td>'+ago(x.time)+'</td><td>'+x.ntx+'</td><td class="mono">'+sh(x.miner)+'</td><td class="mono">'+sh(x.hash)+'</td></tr>').join('')+'</table>';
}
async function bloco(q){
  modo='bloco';
  const x=await j('/api/block?q='+encodeURIComponent(q));
  if(x.erro){$('#conteudo').innerHTML='<pre>'+esc(x.erro)+'</pre>';return}
  $('#cards').innerHTML='';
  $('#conteudo').innerHTML='<pre>'+voltar+'Bloco '+x.height+'\nhash: '+x.hash+'\ndata: '+new Date(x.time*1000).toLocaleString('pt-BR')+'\ntransações: '+x.ntx+'   tamanho: '+x.size+' bytes\nbits: '+x.bits+'   nonce: '+x.nonce+'   época da chave: '+x.epoch+'\nminerador: '+esc(x.miner)+'\nrecompensa (coinbase): '+x.reward+'</pre><table><tr><th>Transação</th><th>Entradas</th><th>Saídas</th><th>Total</th></tr>'+x.txs.map(t=>'<tr class="c" onclick="tx(\''+t.txid+'\')"><td class="mono">'+sh(t.txid)+'</td><td>'+t.vin+'</td><td>'+t.vout+'</td><td>'+t.out+'</td></tr>').join('')+'</table>';
}
async function tx(id){
  modo='tx';
  const t=await j('/api/tx?id='+encodeURIComponent(id));
  $('#cards').innerHTML='';
  $('#conteudo').innerHTML='<pre>'+voltar+esc(JSON.stringify(t,null,1))+'</pre>';
}
async function endereco(a){
  modo='endereco';
  const t=await j('/api/address?a='+encodeURIComponent(a));
  $('#cards').innerHTML='';
  $('#conteudo').innerHTML='<pre>'+voltar+esc(JSON.stringify(t,null,1))+'</pre>';
}
async function buscar(){
  const q=$('#q').value.trim();
  if(!q)return home();
  if(/^\d+$/.test(q))return bloco(q);
  if(/^[0-9a-fA-F]{64}$/.test(q)){
    const x=await j('/api/block?q='+q);
    return x.erro?tx(q):bloco(q);
  }
  return endereco(q);
}
setInterval(()=>{if(modo==='home')home()},5000);
home();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, body, ctype="application/json", code=200):
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path == "/":
                self.reply(PAGE, "text/html")
            elif u.path == "/api/summary":
                self.reply(json.dumps(api_summary()))
            elif u.path == "/api/blocks":
                self.reply(json.dumps(api_blocks(min(int(q.get("n", 20)), 100))))
            elif u.path == "/api/block":
                self.reply(json.dumps(api_block(q["q"])))
            elif u.path == "/api/tx":
                self.reply(json.dumps(api_tx(q["id"])))
            elif u.path == "/api/address":
                self.reply(json.dumps(api_addr(q["a"])))
            else:
                self.reply('{"erro": "nao encontrado"}', code=404)
        except Exception as e:
            self.reply(json.dumps({"erro": str(e)}), code=500)


print(f"explorador em http://127.0.0.1:{args.port}", flush=True)
ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
