@echo off
cd /d "%~dp0"
where py >nul 2>nul && (py -3 patch.py & goto end)
where python >nul 2>nul && (python patch.py & goto end)
echo Python 3 is not installed. Get it here: https://www.python.org/downloads/
:end
echo.
pause
