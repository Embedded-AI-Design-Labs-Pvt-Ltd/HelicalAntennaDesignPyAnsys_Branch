@echo off
setlocal EnableExtensions
title Helical Antenna — AEDT Student
cd /d "%~dp0"

echo Opening Ansys Electronics Desktop Student...
echo Loading project and applying HFSS setup.
echo After the GUI opens: right-click Analysis - Analyze All to generate plots.
echo.

python run_hfss.py %*
set EXITCODE=%ERRORLEVEL%
if not %EXITCODE%==0 (
    echo.
    echo Run failed with exit code %EXITCODE%.
    pause
)
endlocal
exit /b %EXITCODE%
