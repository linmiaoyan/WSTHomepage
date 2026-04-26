@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul

echo ============================================
echo Git 强制推送 - 覆盖远程提交
echo ============================================
echo.
echo [警告] 此操作将：
echo   1. 强制推送本地代码到远程仓库
echo   2. 覆盖远程仓库的提交历史
echo   3. 可能会覆盖其他人的提交（如果有）
echo.
set /p confirm="确认继续？(Y/N): "
if /i not "!confirm!"=="Y" (
    echo 操作已取消
    pause
    exit /b 0
)
echo.

cd /d "%~dp0"

REM 检查Git是否安装
git --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Git，请先安装 Git for Windows
    pause
    exit /b 1
)

REM 检查是否是Git仓库
if not exist ".git" (
    echo [错误] 当前目录不是Git仓库
    pause
    exit /b 1
)

REM 检查并配置远程仓库
git remote -v | findstr "origin" >nul 2>&1
if %errorlevel% neq 0 (
    echo [提示] 未检测到远程仓库，正在添加...
    git remote add origin https://github.com/linmiaoyan/DemoVote.git
    if %errorlevel% neq 0 (
        echo [错误] 添加远程仓库失败
        pause
        exit /b 1
    )
    echo [成功] 远程仓库已添加
    echo.
) else (
    REM 检查远程仓库URL是否正确
    git remote get-url origin | findstr "linmiaoyan/DemoVote" >nul 2>&1
    if %errorlevel% neq 0 (
        echo [提示] 远程仓库URL不正确，正在更新...
        git remote set-url origin https://github.com/linmiaoyan/DemoVote.git
        if %errorlevel% neq 0 (
            echo [错误] 更新远程仓库URL失败
            pause
            exit /b 1
        )
        echo [成功] 远程仓库URL已更新
        echo.
    )
)

REM 检测当前分支名称
for /f "tokens=*" %%i in ('git branch --show-current 2^>nul') do set CURRENT_BRANCH=%%i
if "!CURRENT_BRANCH!"=="" (
    REM 如果没有分支，尝试获取默认分支名
    for /f "tokens=*" %%i in ('git symbolic-ref --short HEAD 2^>nul') do set CURRENT_BRANCH=%%i
)
if "!CURRENT_BRANCH!"=="" (
    REM 如果还是获取不到，检查是否有master分支
    git branch | findstr "master" >nul 2>&1
    if %errorlevel% equ 0 (
        set CURRENT_BRANCH=master
    ) else (
        REM 默认使用main
        set CURRENT_BRANCH=main
    )
)

echo [提示] 当前分支: !CURRENT_BRANCH!
echo.

REM 获取远程最新状态
echo [步骤1] 获取远程最新状态...
git fetch origin
if %errorlevel% neq 0 (
    echo [警告] 获取远程状态失败，但将继续强制推送
    echo.
)

REM 显示本地和远程的差异
echo [步骤2] 检查本地和远程的差异...
git log --oneline origin/!CURRENT_BRANCH!..HEAD 2>nul | findstr /V "^$" >nul
if %errorlevel% equ 0 (
    echo [提示] 本地有以下提交将覆盖远程：
    git log --oneline origin/!CURRENT_BRANCH!..HEAD 2>nul
) else (
    echo [提示] 本地没有新的提交，将强制推送当前状态
)
echo.

REM 选择强制推送方式
echo 请选择强制推送方式：
echo   1. --force-with-lease (推荐，更安全，会检查远程是否有其他人的提交)
echo   2. --force (完全强制，直接覆盖)
echo.
set /p push_type="请选择 (1/2，默认1): "
if "!push_type!"=="" set push_type=1
if "!push_type!"=="2" (
    set FORCE_FLAG=--force
    echo [提示] 使用完全强制推送模式
) else (
    set FORCE_FLAG=--force-with-lease
    echo [提示] 使用安全强制推送模式（推荐）
)
echo.

REM 执行强制推送
echo [步骤3] 执行强制推送...
if "!push_type!"=="2" (
    git push --force origin !CURRENT_BRANCH!
) else (
    git push --force-with-lease origin !CURRENT_BRANCH!
)

if %errorlevel% equ 0 (
    echo.
    echo ============================================
    echo [成功] 代码已强制推送到远程仓库
    echo ============================================
    echo.
    echo 仓库地址：https://github.com/linmiaoyan/DemoVote
    echo 分支：!CURRENT_BRANCH!
    echo.
) else (
    echo.
    echo [错误] 强制推送失败
    echo.
    if "!push_type!"=="1" (
        echo 可能的原因：
        echo   1. 远程仓库有其他人的新提交（--force-with-lease 保护）
        echo   2. 网络连接问题
        echo   3. 认证失败（需要Personal Access Token）
        echo   4. 权限不足
        echo.
        echo [提示] 如果确定要覆盖远程提交，可以：
        echo   1. 重新运行此脚本，选择选项 2 (--force)
        echo   2. 或者先执行: git fetch origin
        echo      然后执行: git push --force origin !CURRENT_BRANCH!
    ) else (
        echo 可能的原因：
        echo   1. 网络连接问题
        echo   2. 认证失败（需要Personal Access Token）
        echo   3. 权限不足
        echo   4. 远程仓库配置错误
        echo.
    )
    echo [提示] 检查远程仓库配置：
    git remote -v
    echo.
)

pause
