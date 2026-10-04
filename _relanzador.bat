@echo off
REM Relanza la cola de certificacion si es seguro hacerlo.
REM La politica vive en relanzar_la_cola.py, no aca: un .bat no se puede testear.
REM Solo para correrlo a mano. Desde el 2026-09-24 la tarea ERETZ_relanzador NO
REM usa este .bat: corre pythonw.exe con --log, sin consola, porque con consola
REM tres o cuatro pasadas por hora morian con 0xC000013A sin dejar rastro.
cd /d "%~dp0"
"C:\Users\Nicolas Wulfsohn\AppData\Local\Programs\Python\Python314\python.exe" -u scripts\relanzar_la_cola.py --lanzar >> "%~dp0..\ERETZ_AGENCY_CERTIFICATION_20260827\relanzador.log" 2>&1
