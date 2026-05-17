@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul

echo ============================================
echo 修复Git安全配置 - 教师数据自填系统
echo ============================================
echo.
echo [说明] 此脚本用于修复Git的"dubious ownership"错误
echo [说明] 会将当前项目目录添加到Git安全目录列表
echo.

cd /d "%~dp0"

REM 获取当前目录
set CURRENT_DIR=%~dp0
REM 移除末尾的反斜杠
set CURRENT_DIR=%CURRENT_DIR:~0,-1%

echo [当前目录] %CURRENT_DIR%
echo.

REM 配置Git安全目录
echo [步骤1] 添加当前目录到Git安全目录...
git config --global --add safe.directory "%CURRENT_DIR%" 2>nul
if %errorlevel% equ 0 (
    echo [成功] 已添加: %CURRENT_DIR%
) else (
    echo [提示] 可能已存在，继续...
)

REM 也添加带反斜杠的版本
git config --global --add safe.directory "%CURRENT_DIR%\" 2>nul

REM 添加父目录
for %%P in ("%CURRENT_DIR%") do (
    set PARENT_DIR=%%~dpP
    set PARENT_DIR=!PARENT_DIR:~0,-1!
    if not "!PARENT_DIR!"=="" (
        git config --global --add safe.directory "!PARENT_DIR!" 2>nul
        echo [成功] 已添加父目录: !PARENT_DIR!
    )
)

echo.
echo [步骤2] 查看当前Git安全目录配置...
git config --global --get-all safe.directory
echo.

echo ============================================
echo [完成] Git安全配置已更新
echo ============================================
echo.
echo [下一步] 现在可以运行 2pull_normal.bat 或 1push.bat
echo.

pause
