@echo off
REM =====================================================================
REM  PhantomCore launcher shim
REM
REM  pcore            start the bot hidden in the background
REM  pcore start      same as above
REM  pcore stop       stop the bot (and the Lavalink server it spawned)
REM  pcore status     report whether the bot is running
REM  pcore logs       print the most recent bot output log
REM
REM  %~dp0 = drive+path of THIS script. Using it keeps this shim portable:
REM  it resolves the venv relative to the script's own location, so the
REM  project folder can live anywhere (or be moved) without editing this
REM  file. The bot is launched via PowerShell Start-Process so it runs
REM  detached (no console window, survives the terminal closing) with
REM  stdout/stderr redirected to timestamped files in data\.
REM =====================================================================
setlocal
set "PCORE=%~dp0.venv\Scripts\phantomcore.exe"
set "DATA=%~dp0data"
set "PCORE_NAME=phantomcore.exe"
set "ARG=%~1"

if "%ARG%"==""                 goto start
if /i "%ARG%"=="start"         goto start
if /i "%ARG%"=="stop"          goto stop
if /i "%ARG%"=="status"        goto status
if /i "%ARG%"=="logs"          goto logs

echo Unknown option: %ARG%
echo Usage: pcore [start^|stop^|status^|logs]
exit /b 1

:start
tasklist /FI "IMAGENAME eq %PCORE_NAME%" | find /i "%PCORE_NAME%" >nul
if not errorlevel 1 (
    echo PhantomCore is already running. Use "pcore stop" first.
    exit /b 1
)
if not exist "%PCORE%" (
    echo %PCORE% not found. Run "uv sync" first.
    exit /b 1
)

set "TS=%TIME:~0,2%%TIME:~3,2%%TIME:~6,2%"
set "TS=%TS: =%"
set "STDOUT=%DATA%\bot.stdout_%TS%.log"
set "STDERR=%DATA%\bot.stderr_%TS%.log"

powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command ^
  "$p='%PCORE%'; $wd='%~dp0'; $o='%STDOUT%'; $e='%STDERR%'; ^
   Start-Process -FilePath $p -WorkingDirectory $wd -WindowStyle Hidden ^
     -RedirectStandardOutput $o -RedirectStandardError $e"

if errorlevel 1 (
    echo Failed to start PhantomCore.
    exit /b 1
)
echo PhantomCore started in background.
echo   stdout: %STDOUT%
echo   stderr: %STDERR%
exit /b 0

:stop
echo Stopping PhantomCore...
taskkill /IM %PCORE_NAME% /F >nul 2>&1
if errorlevel 1 (
    echo   PhantomCore was not running.
)
echo Stopping Lavalink server...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Get-CimInstance Win32_Process ^| Where-Object { $_.Name -like 'java*' -and $_.CommandLine -like '*Lavalink.jar*' } ^| ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
echo Done.
exit /b 0

:status
tasklist /FI "IMAGENAME eq %PCORE_NAME%" 2>nul | find /i "%PCORE_NAME%" >nul
if errorlevel 1 (
    echo PhantomCore is not running.
    exit /b 1
)
echo PhantomCore is running.
exit /b 0

:logs
set "LATEST="
for /f %%f in ('dir /b /o-n "%DATA%\bot.stdout_*.log" 2^>nul') do if not defined LATEST set "LATEST=%DATA%\%%f"
if not defined LATEST (
    echo No bot logs found in %DATA%.
    exit /b 1
)
echo ---- %LATEST% ----
type "%LATEST%"
exit /b 0