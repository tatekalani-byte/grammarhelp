@echo off
rem Double-click to get a menu, or run "wiibridge.bat pair", "wiibridge.bat run" etc.
setlocal
cd /d "%~dp0"
title Wii to Clone Hero bridge

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo Python 3 is not installed.
    echo Get it from https://www.python.org/downloads/ and answer y to
    echo "Install CPython now?", then run this again.
    pause
    exit /b 1
)

if not exist ".venv\installed.ok" (
    echo First run: installing what this program needs. This takes a minute or two.
    echo If the ViGEmBus driver installer opens, accept the licence and click Install.
    echo.
    if exist ".venv" rmdir /s /q ".venv"
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
