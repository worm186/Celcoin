# Rubiana (RUBIA) - notas do projeto

## Ideia
Moeda estilo Bitcoin (transparente, modelo UTXO), minerada com CPU e celular. Fork do Bitcoin Core.
Nome provisório: Rubiana, sigla RUBIA. Checagens feitas (CoinMarketCap, GitHub, INPI): sem conflito em cripto. Domínio livre (confirmar e registrar). Repetir a checagem antes do lançamento.

## Decisões
- Oferta total 86 milhões; recompensa inicial 86; halving a cada 500.000 blocos (~4,8 anos); bloco a cada 5 min.
- Transações públicas como o Bitcoin (sem privacidade tipo Monero por ora). Carteira usa endereço novo a cada recebimento.
- Prova de trabalho: RandomX (resistente a ASIC), com modo leve (256 MB) para celular.
- Pools com pagamento proporcional ao trabalho (shares); limite de tamanho por pool (a definir). NerdMiner/ESP32 não é compatível (só faz SHA-256).
- App Android: minerador + carteira open source + explorador de blocos (ideia tipo mempool.space).
- Mensagem do gênesis definitiva: "17/Oct/2026 Mineracao para todos, na palma da mao | BTC ~US$126 mil, 1 ano" (entra no gênesis da rede principal, ainda não feito).

## Estado do código (repositório worm186/Celcoin, branch master)
- Recompensa 86 (validation.cpp), teto de 86 milhões (amount.h), halving 500000 e bloco de 5 min (kernel/chainparams.cpp).
- Identidade própria: magic bytes e portas (main 8686, testnet 18686, regtest 18688); endereços rubia / trubia / rrubia.
- RandomX em src/randomx (versão fixa em COMMIT.txt), ligado à bitcoin_common; GetPoWHash() no pow.cpp com chave FIXA de teste; 5 checagens de PoW trocadas (blockstorage.cpp x2, validation.cpp x2, rpc/mining.cpp).
- Dificuldade: piso mais fácil (powLimit 00ffff...), janela de ajuste de 60 blocos, e correção do estouro de cálculo (dividir antes de multiplicar) em CalculateNextWorkRequired.
- Testnet: gênesis TEMPORÁRIO minerado ao iniciar (MineGenesis em kernel/chainparams.cpp), nonce 286, bits 2000ffff, data 1792195200.
- Testes feitos: regtest (saldo 86; halving no bloco 150), benchmark RandomX (modo leve ~41 H/s por núcleo; completo ~300 H/s por núcleo), testnet com 125 blocos (bits foi a 1f3fffbf), dois nós sincronizando (127 blocos).

## Como rodar (testnet)
- Compilar: cmake --build build -j $(nproc) --target bitcoind bitcoin-cli (build configurado com -DENABLE_IPC=OFF)
- Iniciar: ./build/bin/bitcoind -testnet -daemon -dnsseed=0 -fixedseeds=0
- Carteira: createwallet teste (1ª vez) ou loadwallet teste (após reiniciar)
- Minerar: bitcoin-cli -testnet generatetoaddress 25 $(bitcoin-cli -testnet getnewaddress)
- Segundo nó: -datadir=/tmp/noB -port=18687 -rpcport=18334 -connect=127.0.0.1:18686

## Pendências (ordem sugerida)
1. (FEITO) Tirar do código o trabalho mínimo, assumevalid e sementes do Bitcoin.
2. Chave do RandomX que muda com a cadeia (hoje fixa).
3. Ajuste de dificuldade bloco a bloco (tipo LWMA) com proteção contra manipulação de tempo.
4. Remover o MineGenesis temporário; gênesis definitivo da rede principal com a mensagem; renomear programas e pastas; nós de entrada.
5. Compilar RandomX portátil (sem -march=native) e adaptar os testes automáticos.
6. Servidor de pool (stratum), app Android, carteira, explorador.
7. Auditoria de segurança por especialistas; testnet pública; marca (INPI), domínio e parte legal.

## Observações
- O responsável pelo projeto é iniciante em programação: avançar em passos pequenos, um comando por vez, pedindo print do resultado.
- Terminal: copiar só os blocos de comando; "q" sai do visualizador; parar o Codespace pelo site github.com/codespaces.

## Registro
- 19/10/2026: dois nós sincronizando na testnet (127 blocos) sem opções extras; removidos do código o trabalho mínimo, assumevalid e sementes do Bitcoin. Próximo: benchmark do RandomX em celular real (Termux).
- 19/10/2026: celular de referência: Samsung Galaxy A06 (Helio G85, 2x A75 + 6x A55, 4 GB de RAM). Só roda RandomX no modo leve (256 MB). Estimativa, não medida: ~20-40 H/s no aparelho todo, contra ~5.000+ H/s de um PC de mesa (100 a 200 vezes menos). Sem JIT o RandomX fica inútil (~3-5 H/s). Celulares reduzem a velocidade sozinhos com o calor. Decisão: medir só depois, dentro do nosso app, com limite de temperatura e de CPU. Sem prometer ganhos: pagamento mínimo baixo nas pools.
- PRÓXIMA TAREFA: pendência 2 (chave do RandomX que muda). Atenção: a checagem de PoW do Bitcoin Core é sem contexto de cadeia (headers-first). Opções: (a) chave vinda de bloco ancestral, como o Monero, exigindo PoW contextual e mudanças na sincronização de cabeçalhos; (b) chave derivada da época do nTime do próprio cabeçalho, que permite checar sem contexto. Depois: dificuldade bloco a bloco (LWMA).
- 19/10/2026: pendência 2 FEITA: chave do RandomX derivada da época do nTime do cabeçalho (2 dias), em pow.cpp, com cache por época (máx. 2). Testada com dois nós em épocas diferentes. Fraqueza conhecida: perto da virada de época o minerador pode escolher entre duas chaves. Próximo: dificuldade bloco a bloco (LWMA).
- 19/10/2026: pendência 3 FEITA: dificuldade bloco a bloco (LWMA-1, janela de 60 blocos, salto máximo ~10x) em pow.cpp, usada em todas as redes menos o regtest. Testada com dois nós (70 blocos). ATENÇÃO antes da rede principal: adaptar PermittedDifficultyTransition (hoje só a testnet aceita qualquer mudança de dificuldade na sincronização de cabeçalhos). Próximo: gênesis definitivo, remover MineGenesis, renomear programas, RandomX portátil.
- 20/10/2026: pendência 3 confirmada. NOVA PENDÊNCIA (prioridade antes do gênesis definitivo): (a) ativar desde o início, em main e testnet, as regras BIP34/65/66, CSV, SegWit e Taproot (hoje usam as alturas do Bitcoin real); (b) testar de fato o envio de moedas entre duas carteiras, o que nunca foi feito.
- 20/10/2026: regras BIP34/65/66, CSV e SegWit ativas desde o bloco 1 em main e testnet (Taproot já ativo nesta versão). Regtest também usa MineGenesis temporário. Envio de moedas testado em regtest (Alice envia 10 a Bob). ATENÇÃO: numa cadeia nova a carteira não tem estimativa de taxa (fallbackfee desligado); usar fee_rate explícito ou -fallbackfee. O app/carteira da Rubiana precisa definir uma taxa padrão no começo da rede.
- 20/10/2026: mensagem do gênesis incluída (função padrão do chainparams.cpp): "17/Oct/2026 Mineracao para todos, na palma da mao | BTC ~US$126 mil, 1 ano". Main, testnet e regtest usam MineGenesis (provisório; nTime da main 1792195260, nBits 2000ffff). A testnet4 e a signet não são usadas e a signet pode falhar nas conferências de gênesis.
- NO LANÇAMENTO: remover o MineGenesis e fixar nonce, hash e merkle (reabilitar os asserts); escolher nTime real; desenhar a dificuldade inicial e a rampa dos primeiros blocos (lançamento justo: com dificuldade baixa, os primeiros 60 blocos saem em minutos e concentram moedas).
- Pendências restantes: renomear programas e pastas (bitcoind etc.), RandomX portátil (sem -march=native), adaptar PermittedDifficultyTransition e os testes automáticos, taxa padrão na carteira, pool, app Android, explorador, auditoria, marca/legal.
- 20/10/2026: RandomX compilado de forma portátil (ARCH default, sem -march=native) em src/CMakeLists.txt. Próximo: renomear programas e pastas; depois adaptar PermittedDifficultyTransition (rede principal) e começar as frentes de pool, app, carteira e explorador.
- 20/10/2026: PLANO DOS MINERADORES: núcleo compartilhado em C++ (RandomX) com duas frentes, programa de linha de comando para PC (modo completo, 2 GB) e app Android (NDK, modo leve). Ordem: (1) confirmar getblocktemplate/submitblock no nó; (2) minerador solo de PC; (3) servidor de pool (stratum próprio, pagamento por shares); (4) minerador ligado à pool; (5) app Android. XMRig não serve direto (formato de cabeçalho e chave por época do nTime). Cuidados: antivírus, código aberto, consentimento e limite de CPU (nunca minerador escondido).

## Princípios do projeto
- Honestidade e transparência: código aberto, sem mineração escondida, sem promessa de lucro.
- Lançamento justo: sem pré-mineração (a recompensa do gênesis não é gastável; toda moeda nasce por mineração) e sem taxa de desenvolvedor.
- Mineração é sorteio proporcional ao poder de hash: qualquer minerador, mesmo pequeno, pode achar um bloco. Não se promete igualdade de resultados entre aparelhos.
- Pools: pagamento proporcional ao trabalho, regras públicas, limite de tamanho por pool e, no futuro, opção descentralizada.
- 20/10/2026: protótipo de minerador solo em tools/: rubiana-search.cpp (RandomX, modo leve, 1 thread; compilar com g++ ligando librandomx.a) e rubiana-solo-miner.py (getblocktemplate, monta coinbase com SegWit e merkle, submitblock). Serve de base para o minerador de PC e para o servidor de pool.
- 20/10/2026: motor de mineração persistente tools/rubiana-miner.cpp (C++, várias threads, modo leve ou --full de 2 GB, protocolo por linhas JOB/FOUND/STATS/QUIT; recompila o conjunto de dados quando a época da chave muda) e tools/rubiana-solo-miner.py v2 (usa o motor). Base do minerador de PC, do app Android e do protocolo com a pool. Compilar: g++ -O2 -std=c++17 -o /tmp/rubiana-miner tools/rubiana-miner.cpp -I src/randomx/src $(find build -name librandomx.a | head -1) -lpthread

## STATUS EM 22/10/2026
- Pronto: moeda com regras e identidade próprias; RandomX com chave por época (2 dias) e build portátil; dificuldade LWMA-1 bloco a bloco; regras modernas ativas desde o bloco 1; gênesis com a mensagem do projeto (provisório, minerado ao iniciar); envio de moedas testado; dois nós sincronizando; minerador solo externo (tools/) e motor persistente rubiana-miner (leve ~70 H/s, completo ~500 H/s em 2 núcleos).
- Como rodar a testnet: ./build/bin/bitcoind -testnet -daemon -dnsseed=0 -fixedseeds=0 ; esperar ~40 s ; bitcoin-cli -testnet loadwallet teste (ou createwallet teste).
- Próximo: motor v2 com shares e comando HASH, depois servidor de pool (Python) e cliente; depois app Android (NDK), carteira, explorador; renomear programas e pastas; PermittedDifficultyTransition da main; fixar o gênesis no lançamento; auditoria.
- 23/10/2026: motor agora compilado em build/bin/rubiana-miner (a pasta /tmp é apagada quando o Codespace reinicia). Compilar: g++ -O2 -std=c++17 -o build/bin/rubiana-miner tools/rubiana-miner.cpp -I src/randomx/src $(find build -name librandomx.a | head -1) -lpthread
- 23/10/2026: pool v0 local (tools/rubiana-pool.py, asyncio, só em 127.0.0.1, 0% de taxa, contabilidade por trabalho em pool-data.json, conferência de shares pelo comando HASH do motor), tools/rubiana-pool-miner.py e tools/rubiana_common.py. Falta: pagamento real após maturidade (100 blocos), dificuldade de share por minerador (vardiff), extranonce por minerador, limite por pool.
- 24/10/2026: pagamento da pool (tools/rubiana-pool-pay.py): credita rodadas com 100 confirmações como saldo por endereço, paga em uma transação (sendmany, taxa de rede dividida entre quem recebe, pool sem taxa) quem tem saldo >= mínimo (0,001 por padrão). Testado na regtest com --data pool-regtest.json. Próximos refinamentos: PPLNS no lugar do proporcional por rodada (resiste a pool hopping e reduz a oscilação), dificuldade de share por minerador (vardiff), extranonce por minerador.
