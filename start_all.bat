@echo off
cd /d "%~dp0"
call install_dependencies.bat
if errorlevel 1 (pause & exit /b 1)
set "ARCVault_SKIP_INSTALL=1"
start "ArcVault Backend" cmd /k start_backend.bat
start "ArcVault Publisher API" cmd /k start_publisher_api.bat
start "ArcVault Frontend" cmd /k start_frontend.bat
echo.
echo ArcVault startup commands launched.
echo Frontend: http://127.0.0.1:5500
echo Main API: http://127.0.0.1:5000/api/health
echo Publisher API: http://127.0.0.1:5001/api/health
