@echo off
cd /d "D:\INMO CAPITAL\eretz-agency"
python -u scripts\run_agency_certification_queue.py --ready --limit 0 >> "D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827\cola_task.log" 2>&1
