@echo off
cd /d "%~dp0"
build\bin\rubiana-cli.exe -testnet stop
echo.
pause
