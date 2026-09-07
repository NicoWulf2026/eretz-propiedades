@echo off
cd /d "D:\INMO CAPITAL\eretz-agency"
python -u scripts\run_agency_certification_queue.py --ready --workers 2 --worker 0 --limit 0 >> "D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827\cola_w0.log" 2>&1
