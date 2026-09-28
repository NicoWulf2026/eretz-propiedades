@echo off
REM ERETZ AUTOMATION OFF: nadie relanza la cola (interruptor ERETZ_AUTOMATION_OFF.json),
REM tareas deshabilitadas y los workers paran al terminar la agencia en curso.
REM Cortar los workers ya:  ERETZ_AUTOMATION_OFF.cmd --inmediato
REM Encender de nuevo: ERETZ_AUTOMATION_ON.cmd. Detalle: docs\agent\ERETZ_AUTOMATION.md
cd /d "D:\INMO CAPITAL\eretz-unified"
"C:\Users\Nicolas Wulfsohn\AppData\Local\Programs\Python\Python314\python.exe" scripts\eretz_automatizacion.py off %*
set RC=%ERRORLEVEL%
timeout /t 20 >nul 2>&1
exit /b %RC%
