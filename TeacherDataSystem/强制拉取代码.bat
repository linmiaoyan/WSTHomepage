@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul

echo ============================================
echo 强制拉取代码 - 教师数据自填系统
echo ============================================
echo.
echo [说明] 此脚本会强制从GitHub拉取所有文件
echo [说明] 会覆盖本地未提交的更改
echo.

cd /d "%~dp0"

REM 配置Git安全目录
echo [配置] 设置Git安全目录...
set CURRENT_DIR=%~dp0
set CURRENT_DIR=%CURRENT_DIR:~0,-1%
git config --global --add safe.directory "%CURRENT_DIR%" >nul 2>&1
git config --global --add safe.directory "%CURRENT_DIR%\" >nul 2>&1
echo [成功] Git安全目录已配置
echo.

REM 检查是否在Git仓库中
if not exist ".git" (
    echo [错误] 当前目录不是Git仓库
    echo [提示] 请先运行 2pull_normal.bat 初始化仓库
    pause
    exit /b 1
)

echo [步骤1] 获取远程更新...
git fetch origin main
if %errorlevel% neq 0 (
    echo [错误] 获取远程更新失败
    pause
    exit /b 1
)
echo [成功] 已获取远程更新
echo.

echo [步骤2] 检查远程文件...
git ls-tree -r --name-only origin/main > temp_remote_list.txt 2>nul
if exist temp_remote_list.txt (
    echo [远程文件列表]
    type temp_remote_list.txt | more
    echo.
    set /p confirm="确认要强制拉取这些文件吗？(Y/N): "
    if /i not "!confirm!"=="Y" (
        echo [取消] 操作已取消
        del temp_remote_list.txt >nul 2>&1
        pause
        exit /b 0
    )
    del temp_remote_list.txt >nul 2>&1
) else (
    echo [警告] 无法获取远程文件列表
    set /p confirm="是否继续强制拉取？(Y/N): "
    if /i not "!confirm!"=="Y" (
        echo [取消] 操作已取消
        pause
        exit /b 0
    )
)
echo.

echo [步骤3] 强制重置到远程main分支...
echo [警告] 这将覆盖所有本地未提交的更改！
git reset --hard origin/main
if %errorlevel% equ 0 (
    echo [成功] 已强制重置到远程版本
) else (
    echo [错误] 重置失败
    pause
    exit /b 1
)
echo.

echo [步骤4] 清理未跟踪的文件...
git clean -fd
echo [完成] 已清理未跟踪的文件
echo.

echo [步骤5] 验证文件...
dir /b /a-d 2>nul | find /C /V "" > temp_file_count.txt
set /p file_count=<temp_file_count.txt
del temp_file_count.txt >nul 2>&1
echo [信息] 当前目录文件数量: %file_count%
echo.

echo ============================================
echo [完成] 强制拉取完成
echo ============================================
echo.
echo [提示] 如果文件仍然为空，请检查：
echo   1. GitHub仓库是否有文件
echo   2. 远程仓库地址是否正确
echo   3. 是否有访问权限
echo.

pause
