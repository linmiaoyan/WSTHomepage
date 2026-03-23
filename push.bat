@echo off
chcp 65001 >nul
cd /d "%~dp0"
REM 远程仓库: https://github.com/linmiaoyan/WSTHomepage
git remote set-url origin https://github.com/linmiaoyan/WSTHomepage.git
git push -u origin main
if errorlevel 1 pause
exit /b %errorlevel%
