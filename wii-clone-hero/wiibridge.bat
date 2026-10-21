@echo off
rem Double-click to get a menu, or run "wiibridge.bat pair", "wiibridge.bat run" etc.
setlocal
cd /d "%~dp0"
title Wii to Clone Hero bridge

rem hidapi only has ready-made packages for Python 3.9-3.14 on Intel/AMD
rem processors, so use one of those even when a newer Python is the default.
set "PY="
set "ARCH="
if /i "%PROCESSOR_ARCHITECTURE%"=="ARM64" set "ARCH=-64"
if /i "%PROCESSOR_ARCHITEW6432%"=="ARM64" set "ARCH=-64"
call :findpython
if not defined PY (
    where py >nul 2>nul && (
        echo Installing Python 3.14 for this program. Any other Python you have stays as it is.
        py install 3.14%ARCH%
        call :findpython
    )
)
if not defined PY (
    echo This program needs Python 3.10 to 3.14. Newer versions are not supported yet.
    echo Download Python 3.14 from https://www.python.org/downloads/
    echo then double-click wiibridge.bat again.
    pause
    exit /b 1
)

if not exist ".venv\installed.ok" (
    echo First run: installing what this program needs. This takes a minute or two.
    echo If the ViGEmBus driver installer opens, accept the licence and click Install.
    echo.
    if exist ".venv" rmdir /s /q ".venv"
    %PY% --version
    %PY% -m venv .venv || goto :failed
    ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt || goto :failed
    echo ok> ".venv\installed.ok"
)

if not "%~1"=="" (
    ".venv\Scripts\python.exe" -m wiibridge %*
    goto :done
)

echo.
echo   1. Pair controllers  (once per controller)
echo   2. Start the bridge  (leave it running while you play Clone Hero)
echo   3. Test controllers  (shows what each button does)
echo   4. Forget all paired Wii controllers
echo.
choice /c 1234 /n /m "Choose 1, 2, 3 or 4: "
if errorlevel 4 (set "CMD=forget") else if errorlevel 3 (set "CMD=monitor") else if errorlevel 2 (set "CMD=run") else (set "CMD=pair")
echo.
".venv\Scripts\python.exe" -m wiibridge %CMD%

:done
echo.
pause
exit /b 0

:failed
echo.
echo Setup failed; see the messages above.
if exist ".venv" rmdir /s /q ".venv"
pause
exit /b 1

:findpython
where py >nul 2>nul || goto :findpython_plain
for %%V in (3.14 3.13 3.12 3.11 3.10) do (
    if not defined PY (
        py -%%V%ARCH% -c "import sys" >nul 2>nul && set "PY=py -%%V%ARCH%"
    )
)
:findpython_plain
if not defined PY (
    python -c "import sys; sys.exit(not (3, 9) <= sys.version_info[:2] <= (3, 14))" >nul 2>nul && set "PY=python"
)
exit /b 0
