@echo off
cd /d "D:\INMO CAPITAL\eretz-agency"
python -u scripts\run_agency_certification_queue.py --ready --workers 2 --worker 1 --limit 0 >> "D:\INMO CAPITAL\ERETZ_AGENCY_CERTIFICATION_20260827\cola_w1.log" 2>&1
