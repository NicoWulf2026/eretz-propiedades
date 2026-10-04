@echo off
rem El vigilante de paros. Solo mira: no relanza, no mata, no toca cerrojos.
rem Escribe ERETZ_QUEUE_WATCH_STATUS.json con escritura atomica.
rem Para correrlo a mano. La tarea ERETZ_vigilante_paros (ERETZ_AUTOMATION_ON.cmd)
rem lo corre con pythonw y --sin-alerta: sin toast, sin msg.exe, sin pitidos.
cd /d "%~dp0"
python -u scripts\vigilante_de_paros.py --sin-alerta >> "%~dp0..\ERETZ_AGENCY_CERTIFICATION_20260827\vigilante.log" 2>&1
