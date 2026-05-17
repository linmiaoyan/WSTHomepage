@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul

echo ============================================
echo 修复Git文件冲突 - 教师数据自填系统
echo ============================================
echo.
echo [说明] 此脚本用于修复拉取代码时的文件冲突问题
echo [说明] 会自动备份本地文件并删除冲突文件
echo.

cd /d "%~dp0"

REM 配置Git安全目录（解决所有权问题）
echo [配置] 设置Git安全目录...
set CURRENT_DIR=%~dp0
REM 移除末尾的反斜杠
set CURRENT_DIR=%CURRENT_DIR:~0,-1%
git config --global --add safe.directory "%CURRENT_DIR%" >nul 2>&1
REM 也添加带反斜杠的版本
git config --global --add safe.directory "%CURRENT_DIR%\" >nul 2>&1
REM 添加当前目录的父目录（如果需要）
for %%P in ("%CURRENT_DIR%") do git config --global --add safe.directory "%%~dpP" >nul 2>&1
echo [成功] Git安全目录已配置
echo.

REM 检查是否在Git仓库中
if not exist ".git" (
    echo [错误] 当前目录不是Git仓库
    pause
    exit /b 1
)

echo [步骤1] 检查冲突文件...
git fetch origin main >nul 2>&1

REM 获取远程文件列表
git ls-tree -r --name-only origin/main > temp_remote_files.txt 2>nul

if not exist temp_remote_files.txt (
    echo [错误] 无法获取远程文件列表
    pause
    exit /b 1
)

echo [步骤2] 处理冲突文件...
set CONFLICT_COUNT=0

for /f "tokens=*" %%f in (temp_remote_files.txt) do (
    if exist "%%f" (
        REM 检查是否是未跟踪的文件
        git status --porcelain "%%f" | findstr "^??" >nul 2>&1
        if !errorlevel! equ 0 (
            set /a CONFLICT_COUNT+=1
            echo [发现冲突] %%f
            echo [处理] 备份为 %%f.local...
            if not exist "%%f.local" (
                copy "%%f" "%%f.local" >nul 2>&1
                if !errorlevel! equ 0 (
                    echo [成功] 已备份到 %%f.local
                ) else (
                    echo [警告] 备份失败
                )
            ) else (
                echo [提示] 备份文件已存在，跳过备份
            )
            echo [处理] 删除本地文件...
            del "%%f" >nul 2>&1
            if !errorlevel! equ 0 (
                echo [成功] 已删除本地文件
            ) else (
                echo [错误] 删除失败
            )
            echo.
        )
    )
)

del temp_remote_files.txt >nul 2>&1

if %CONFLICT_COUNT% equ 0 (
    echo [提示] 未发现冲突文件
    echo.
    echo [下一步] 可以直接运行 2pull_normal.bat 拉取代码
) else (
    echo ============================================
    echo [完成] 已处理 %CONFLICT_COUNT% 个冲突文件
    echo ============================================
    echo.
    echo [下一步操作]
    echo 1. 运行 2pull_normal.bat 拉取最新代码
    echo 2. 如果需要恢复本地文件，查看 .local 备份文件
    echo.
    echo [提示] 备份文件命名格式：原文件名.local
    echo [示例] 2pull_normal.bat.local 是 2pull_normal.bat 的备份
    echo.
    set /p continue="是否现在运行 2pull_normal.bat？(Y/N): "
    if /i "!continue!"=="Y" (
        echo.
        echo [执行] 正在运行 2pull_normal.bat...
        call "%~dp0\2pull_normal.bat"
    )
)

echo.
pause
