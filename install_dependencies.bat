@echo off
setlocal
cd /d "%~dp0"
if not exist "Backend\.venv\Scripts\python.exe" (
  python -m venv "Backend\.venv"
  if errorlevel 1 (echo ERROR: Could not create virtual environment. Install Python 3.10+ and retry.& exit /b 1)
)
"Backend\.venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 exit /b 1
"Backend\.venv\Scripts\python.exe" -m pip install -r requirements.txt -r Backend\requirements.txt
if errorlevel 1 (echo ERROR: Dependency installation failed.& exit /b 1)
echo Dependencies installed successfully.
exit /b 0
