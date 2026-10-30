@echo off
setlocal
cd /d "%~dp0"
title Rubiana - minerador (REDE DE TESTE)
echo ================================================
echo   RUBIANA - minerador (REDE DE TESTE)
echo   As moedas desta rede de teste NAO tem valor.
echo ================================================
echo.
echo Para PARAR: aperte Ctrl+C nesta janela.
echo Para usar MENOS do computador: abra o arquivo configuracao.txt
echo.
python\python.exe tools\rubiana-mine.py --rede testnet --config configuracao.txt
echo.
echo O minerador parou.
echo Se voce fechou a janela pelo X, de dois cliques em parar.bat.
pause
