@echo off
cd /d "%~dp0"
call npm run dev -- --host 0.0.0.0 --port 3000
