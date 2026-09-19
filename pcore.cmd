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
REM  One file, two modes. If this script lives in "%USERPROFILE%\bin" it is
REM  the installed PATH copy and resolves the project from a hardcoded root
REM  (bin shims can't use %~dp0 meaningfully); anywhere else it uses %~dp0,
REM  so the repo can be moved without editing anything. This keeps a single
REM  file that can be copied into a user's bin folder unmodified.
REM
REM  The bot is launched via PowerShell Start-Process in ShellExecute
REM  mode (no -Redirect flags), so it gets a fully detached hidden console
REM  that never touches the caller's terminal; redirection to timestamped
REM  files in data\ is done by the wrapping cmd /c.
REM =====================================================================
setlocal
set "PCORE_NAME=phantomcore.exe"
set "ARG=%~1"

if /i "%~dp0"=="%USERPROFILE%\bin\" (set "ROOT=I:\opencode_projects\PhantomCore\") else set "ROOT=%~dp0"
set "PCORE=%ROOT%.venv\Scripts\phantomcore.exe"
set "DATA=%ROOT%data"

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

powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath cmd -ArgumentList '/c %PCORE% > %STDOUT% 2> %STDERR%' -WorkingDirectory '%ROOT%' -WindowStyle Hidden"

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
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'java*' -and $_.CommandLine -like '*Lavalink.jar*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
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