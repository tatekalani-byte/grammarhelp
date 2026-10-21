@echo off
rem Double-click to download the playlist's Clone Hero charts into your Songs folder.
setlocal
cd /d "%~dp0"
title Download Clone Hero songs

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo Python 3 is not installed. Get it from https://www.python.org/downloads/
    pause
    exit /b 1
)

echo.
echo   1. The rest of the list: songs 60 to 421, after "Scenes from an Italian Restaurant"
echo   2. All 421 songs
echo   3. Only official Guitar Hero / Rock Band charts, from song 60 on
echo.
echo Songs already in the download folder are always skipped.
choice /c 123 /n /m "Choose 1, 2 or 3: "
if errorlevel 3 (set "ARGS=--official-only --from 60") else if errorlevel 2 (set "ARGS=") else (set "ARGS=--from 60")
echo.
%PY% songs\download_songs.py %ARGS%
echo.
pause
