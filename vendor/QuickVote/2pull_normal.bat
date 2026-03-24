@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul

set GITHUB_URL=https://github.com/linmiaoyan/DemoVote.git

echo ============================================
echo 服务器代码更新
echo ============================================
echo.

REM 检查是否在Git仓库中
if not exist ".git" (
    echo [提示] 当前目录不是Git仓库，正在初始化...
    git init
    git branch -M main
    echo [成功] Git仓库已初始化
    echo.
)

REM 检查远程仓库是否已配置
git remote | findstr /C:"origin" >nul 2>&1
if %errorlevel% equ 0 (
    echo [成功] 远程仓库已配置
    for /f "tokens=*" %%a in ('git remote get-url origin 2^>nul') do set CURRENT_URL=%%a
    echo 当前远程地址: !CURRENT_URL!
    echo.
    
    REM 检查URL是否正确
    if not "!CURRENT_URL!"=="!GITHUB_URL!" (
        echo [提示] 远程地址不匹配，正在更新...
        git remote set-url origin !GITHUB_URL!
        echo [成功] 远程地址已更新
        echo.
    )
    
    echo [步骤] 正在获取远程分支信息...
    git fetch origin
    
    REM 检查远程分支是否存在 - 先检查master，再检查main
    set REMOTE_BRANCH=
    git show-ref --verify --quiet refs/remotes/origin/master
    if %errorlevel% equ 0 (
        set REMOTE_BRANCH=master
    ) else (
        git show-ref --verify --quiet refs/remotes/origin/main
        if %errorlevel% equ 0 (
            set REMOTE_BRANCH=main
        )
    )
    
    REM 如果上面方法失败，尝试使用branch命令
    if "!REMOTE_BRANCH!"=="" (
        git branch -r 2>nul | findstr "origin/master" >nul 2>&1
        if %errorlevel% equ 0 (
            set REMOTE_BRANCH=master
        ) else (
            git branch -r 2>nul | findstr "origin/main" >nul 2>&1
            if %errorlevel% equ 0 (
                set REMOTE_BRANCH=main
            )
        )
    )
    
    if "!REMOTE_BRANCH!"=="" (
        echo.
        echo [错误] 远程仓库中没有找到 main 或 master 分支
        echo [提示] 如果这是首次配置，可能需要先推送代码到GitHub
        pause
        exit /b 1
    )
    
    echo [提示] 检测到远程分支: !REMOTE_BRANCH!
    echo.
    
    REM 检查本地是否有提交
    git rev-parse --verify HEAD >nul 2>&1
    if %errorlevel% equ 0 (
        REM 本地已有提交，直接拉取
        echo [步骤] 正在拉取最新代码...
        git pull origin "!REMOTE_BRANCH!"
    ) else (
        REM 本地没有提交，设置上游分支并拉取
        echo [步骤] 首次拉取，正在设置上游分支...
        git pull origin "!REMOTE_BRANCH!" --allow-unrelated-histories
        if %errorlevel% equ 0 (
            git branch -M "!REMOTE_BRANCH!" >nul 2>&1
            git branch --set-upstream-to=origin/"!REMOTE_BRANCH!" "!REMOTE_BRANCH!" >nul 2>&1
        )
    )
    
    if %errorlevel% equ 0 (
        echo.
        echo [成功] 代码更新成功
    ) else (
        echo.
        echo [错误] 代码更新失败
        pause
        exit /b 1
    )
) else (
    echo [提示] 远程仓库未配置，正在配置...
    git remote add origin !GITHUB_URL!
    echo [成功] 远程仓库已配置
    echo.
    
    echo [步骤] 正在获取远程分支信息...
    git fetch origin
    
    REM 检查远程分支是否存在 - 先检查master，再检查main
    set REMOTE_BRANCH=
    git show-ref --verify --quiet refs/remotes/origin/master
    if %errorlevel% equ 0 (
        set REMOTE_BRANCH=master
    ) else (
        git show-ref --verify --quiet refs/remotes/origin/main
        if %errorlevel% equ 0 (
            set REMOTE_BRANCH=main
        )
    )
    
    REM 如果上面方法失败，尝试使用branch命令
    if "!REMOTE_BRANCH!"=="" (
        git branch -r 2>nul | findstr "origin/master" >nul 2>&1
        if %errorlevel% equ 0 (
            set REMOTE_BRANCH=master
        ) else (
            git branch -r 2>nul | findstr "origin/main" >nul 2>&1
            if %errorlevel% equ 0 (
                set REMOTE_BRANCH=main
            )
        )
    )
    
    if "!REMOTE_BRANCH!"=="" (
        echo.
        echo [错误] 远程仓库中没有找到 main 或 master 分支
        echo [提示] 如果这是首次配置，可能需要先推送代码到GitHub
        pause
        exit /b 1
    )
    
    echo [提示] 检测到远程分支: !REMOTE_BRANCH!
    echo.
    
    REM 检查本地是否有提交
    git rev-parse --verify HEAD >nul 2>&1
    if %errorlevel% equ 0 (
        REM 本地已有提交，直接拉取
        echo [步骤] 正在拉取最新代码...
        git pull origin "!REMOTE_BRANCH!"
    ) else (
        REM 本地没有提交，设置上游分支并拉取
        echo [步骤] 首次拉取，正在设置上游分支...
        git pull origin "!REMOTE_BRANCH!" --allow-unrelated-histories
        if %errorlevel% equ 0 (
            git branch -M "!REMOTE_BRANCH!" >nul 2>&1
            git branch --set-upstream-to=origin/"!REMOTE_BRANCH!" "!REMOTE_BRANCH!" >nul 2>&1
        )
    )
    
    if %errorlevel% equ 0 (
        echo.
        echo [成功] 代码更新成功
    ) else (
        echo.
        echo [错误] 代码更新失败
        echo.
        echo [提示] 如果这是首次配置，可能需要先推送代码到GitHub
        pause
        exit /b 1
    )
)

echo.
echo ============================================
pause


