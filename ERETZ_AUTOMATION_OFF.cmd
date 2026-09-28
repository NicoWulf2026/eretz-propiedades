@echo off
REM ERETZ AUTOMATION OFF: nadie relanza la cola (interruptor ERETZ_AUTOMATION_OFF.json),
REM tareas deshabilitadas y los workers paran al terminar la agencia en curso.
REM Cortar los workers ya:  python scripts\eretz_automatizacion.py off --inmediato
REM Encender de nuevo: ERETZ_AUTOMATION_ON.cmd
cd /d "D:\INMO CAPITAL\eretz-unified"
"C:\Users\Nicolas Wulfsohn\AppData\Local\Programs\Python\Python314\python.exe" scripts\eretz_automatizacion.py off %*
timeout /t 20 >nul 2>&1
