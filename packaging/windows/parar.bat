@echo off
cd /d "%~dp0"
build\bin\rubiana-cli.exe -testnet stop >nul 2>&1
if errorlevel 1 (
  echo O minerador ja estava parado. Tudo certo.
) else (
  echo Minerador parado.
)
echo.
pause
