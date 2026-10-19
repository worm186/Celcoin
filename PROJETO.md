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
