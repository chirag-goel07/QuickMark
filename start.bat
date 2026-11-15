@echo off
rem QuickMark launcher for Windows: double-click this file.
cd /d "%~dp0"
title QuickMark
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 start.py %*
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        python start.py %*
    ) else (
        echo.
        echo Python was not found on this computer.
        echo Install it from https://www.python.org/downloads/  and TICK "Add python.exe to PATH" in the installer,
        echo then double-click start.bat again.
    )
)
echo.
echo ---- QuickMark has stopped. Read the messages above if something went wrong. ----
pause
