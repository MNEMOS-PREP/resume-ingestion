@echo off
setlocal
cd /d "%~dp0"

REM ============================================================
REM  Dispatcher. The launchers are start_all.bat and
REM  start_resume.bat; this file stays because README.md,
REM  PORTS.txt and dependencies.txt all tell you to type
REM  `start.bat`. Renaming an entry point to tidy a directory
REM  is a bad trade.
REM
REM    start.bat            everything          -> start_all.bat
REM    start.bat resume    this module only    -> start_resume.bat
REM    start.bat m01          same thing
REM    start.bat check      prerequisites, launch nothing
REM
REM  What actually runs the services: scripts\launch.ps1
REM  What you add a service to:       scripts\services.txt
REM  What closes them again:          scripts\control.ps1
REM ============================================================

if /i "%~1"=="check"  goto CHECK
if /i "%~1"=="resume" goto ONLY
if /i "%~1"=="m01"    goto ONLY
if /i "%~1"=="all"    goto ALL
if "%~1"==""          goto ALL
goto USAGE

:ALL
call "%~dp0start_all.bat"
exit /b %errorlevel%

:ONLY
call "%~dp0start_resume.bat"
exit /b %errorlevel%

:CHECK
call "%~dp0start_all.bat" -Check
exit /b %errorlevel%

:USAGE
echo.
echo   Unknown option "%~1".
echo.
echo     start.bat            everything
echo     start.bat resume    M01 only  ^(same as start_resume.bat^)
echo     start.bat check      verify prerequisites, launch nothing
echo.
exit /b 1
