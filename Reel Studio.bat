@echo off
setlocal
title Reel Studio
cd /d "%~dp0"

set PYTHONIOENCODING=utf-8
set OPEN_BROWSER=1

rem Build the interface the first time, or after you change the frontend.
if not exist "frontend\out\index.html" (
  echo.
  echo   Building the interface for the first time. This takes about a minute...
  echo.
  pushd frontend
  call npm run build
  if errorlevel 1 (
    echo.
    echo   Interface build FAILED. Is Node.js installed?
    popd
    pause
    exit /b 1
  )
  popd
)

python app.py
if errorlevel 1 (
  echo.
  echo   Reel Studio exited with an error. Is Python installed and are the
  echo   requirements installed?  pip install -r requirements.txt
  echo.
  pause
)
endlocal
