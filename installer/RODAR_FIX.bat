@echo off
REM =============================================================================
REM Auto-eleva e executa fix_forcelist.ps1
REM De um duplo clique neste arquivo e aceite o UAC.
REM =============================================================================

REM Checa se ja esta rodando como admin
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Solicitando privilegios de administrador...
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

echo.
echo ============================================================
echo  Executando fix_forcelist.ps1 como administrador
echo ============================================================
echo.

cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -NoProfile -File ".\fix_forcelist.ps1"

echo.
echo ============================================================
echo  Processo terminado. Leia a mensagem acima.
echo ============================================================
echo.
pause
