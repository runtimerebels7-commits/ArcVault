@echo off
cd /d "%~dp0"
if not "%ARCVault_SKIP_INSTALL%"=="1" call install_dependencies.bat
if errorlevel 1 (pause & exit /b 1)
set "PYTHONPATH=%CD%;%CD%\Backend"
"Backend\.venv\Scripts\python.exe" publisher_api.py
pause
