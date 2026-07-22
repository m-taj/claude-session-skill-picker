@echo off
REM Double-click launcher for skills-settings.py — opens the skill picker
REM straight to its Settings panel. No terminal knowledge required.
set SCRIPT=%USERPROFILE%\.claude\hooks\skills-settings.py
where pyw >nul 2>nul
if %ERRORLEVEL%==0 (
    start "" pyw "%SCRIPT%"
) else (
    start "" pythonw "%SCRIPT%"
)
