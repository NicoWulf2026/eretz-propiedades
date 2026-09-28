@echo off
REM ERETZ AUTOMATION ON: cola de certificacion corriendo sola (max 2 workers),
REM relanzador cada 10 min y vigilante cada 5 min, sin consola ni popups.
REM Apagar: ERETZ_AUTOMATION_OFF.cmd. Detalle: docs\agent\ERETZ_AUTOMATION.md
cd /d "D:\INMO CAPITAL\eretz-unified"
"C:\Users\Nicolas Wulfsohn\AppData\Local\Programs\Python\Python314\python.exe" scripts\eretz_automatizacion.py on
set RC=%ERRORLEVEL%
"C:\Users\Nicolas Wulfsohn\AppData\Local\Programs\Python\Python314\python.exe" scripts\eretz_automatizacion.py estado
REM Para leer el resultado al abrirlo con doble clic; sin consola no espera.
timeout /t 20 >nul 2>&1
exit /b %RC%
