@echo off
setlocal
title Reel Studio
cd /d "%~dp0"

set PYTHONIOENCODING=utf-8
set OPEN_BROWSER=1

rem Build the interface the first time, or after you change the frontend.
powershell -NoProfile -Command "$out = Get-Item -LiteralPath 'frontend/out/index.html' -ErrorAction SilentlyContinue; if (!$out) { exit 1 }; $inputs = @(Get-ChildItem 'frontend/app' -Recurse -File) + @(Get-Item 'frontend/package.json','frontend/package-lock.json','frontend/next.config.mjs'); if ($inputs | Where-Object LastWriteTimeUtc -gt $out.LastWriteTimeUtc | Select-Object -First 1) { exit 1 }; exit 0"
if errorlevel 1 (
  echo.
  echo   Building updated interface...
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
