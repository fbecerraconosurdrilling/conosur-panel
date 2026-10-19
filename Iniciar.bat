@echo off
title Lanzador Conosur Drilling - Monitoreo
color 0A

set "DIR_BASE=C:\conosur-panel\TABLERO UNIFICADO DE STALINK CON EZVIZ TODO JUNTO"

echo ========================================================
echo   INICIANDO SISTEMA DE MONITOREO CONOSUR DRILLING
echo ========================================================
echo.

if not exist "%DIR_BASE%" (
    echo [ERROR] No se encuentra la carpeta.
    pause
    exit
)

echo [1/2] Levantando servidor (Starlink + Camaras)...
start "Servidor Conosur - NO CERRAR" cmd /k "cd /d "%DIR_BASE%" && python app.py"

echo Esperando 4 segundos...
timeout /t 4 >nul

echo [2/2] Iniciando publicador a GitHub Pages...
start "Publicador a GitHub" cmd /k "cd /d "%DIR_BASE%" && python publish_tray.py"

echo.
echo ========================================================
echo   SISTEMA INICIADO
echo   Panel local: http://localhost:5000
echo ========================================================
timeout /t 5 >nul
exit