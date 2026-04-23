@echo off
chcp 65001 >nul
cd /d "%~dp0"
set START_STACK=1
python server.py
if errorlevel 1 pause
