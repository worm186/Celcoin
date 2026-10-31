@echo off
setlocal
cd /d "%~dp0"
title Rubiana - minerador (REDE DE TESTE)
echo ================================================
echo   RUBIANA - minerador (REDE DE TESTE)
echo   As moedas desta rede de teste NAO tem valor.
echo ================================================
echo.
echo Para PARAR: aperte Ctrl+C. Se perguntar "S/N", digite N e Enter.
echo Para usar MENOS do computador: use o arquivo minerar-leve.bat
echo.
python\python.exe tools\rubiana-mine.py --rede testnet --config configuracao.txt
echo.
echo O minerador parou.
echo Se voce fechou a janela pelo X, de dois cliques em parar.bat.
pause
