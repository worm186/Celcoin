@echo off
setlocal
cd /d "%~dp0"
title Rubiana - minerador LEVE (REDE DE TESTE)
echo ================================================
echo   RUBIANA - minerador LEVE (usa so 1 nucleo)
echo   REDE DE TESTE: as moedas NAO tem valor.
echo ================================================
echo.
echo Para PARAR: aperte Ctrl+C. Se perguntar "S/N", digite N e Enter.
echo.
python\python.exe tools\rubiana-mine.py --rede testnet --threads 1
echo.
echo O minerador parou.
echo Se voce fechou a janela pelo X, de dois cliques em parar.bat.
pause
