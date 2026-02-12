@echo off
cd /d C:\Trading_Agent_System
git add .
set datetime=%date% %time%
git commit -m "Auto-update: %datetime%"
git push origin main