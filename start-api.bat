@echo off
chcp 65001 >nul
cd /d "%~dp0server"
if not exist node_modules (
  echo 首次运行：正在 npm install ...
  call npm install
  if errorlevel 1 pause & exit /b 1
)
set PORT=8788
node index.js
pause
