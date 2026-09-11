@echo off
REM starts phantomcore discord bot
REM %~dp0 = drive+path of THIS script (no trailing-dir search). Using it keeps
REM this shim portable: it resolves relative to the script's own location, so
REM the project folder can live anywhere (or be moved) without editing this file.
setlocal
set "PCORE=%~dp0.venv\Scripts\phantomcore.exe"
start %PCORE%