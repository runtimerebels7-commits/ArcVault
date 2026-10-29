@echo off
cd /d "%~dp0\Frontend"
python -m http.server 5500
pause
