@echo off
rem El vigilante de paros. Solo mira: no relanza, no mata, no toca cerrojos.
rem Escribe un unico archivo, ERETZ_QUEUE_WATCH_STATUS.json, y lo hace con
rem escritura atomica -temporal + rename- para que nadie lea un JSON a medias.
rem
rem Existe porque el 2026-09-15 la cola estuvo OCHO HORAS parada en `fenix` y
rem nadie lo supo hasta que alguien fue a mirar los cerrojos a mano. El paro
rem estaba bien puesto; lo que faltaba era que se viera.
cd /d "D:\INMO CAPITAL\eretz-agency"
python -u scripts\vigilante_de_paros.py >> "D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827\vigilante.log" 2>&1
