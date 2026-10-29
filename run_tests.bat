@echo off
cd /d "%~dp0"
if not exist "Backend\.venv\Scripts\python.exe" call install_dependencies.bat
if errorlevel 1 (pause & exit /b 1)
"Backend\.venv\Scripts\python.exe" -m pytest -q
pause
