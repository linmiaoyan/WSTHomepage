@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul

set GITHUB_URL=https://github.com/linmiaoyan/TeacherDataSystem.git

echo ============================================
echo 服务器代码更新 - 教师数据自填系统
echo ============================================
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
    
    REM 检查URL是否正确（忽略.git后缀的差异）
    set CURRENT_URL_CLEAN=!CURRENT_URL!
    set GITHUB_URL_CLEAN=!GITHUB_URL!
    if "!CURRENT_URL_CLEAN:~-4!"==".git" set CURRENT_URL_CLEAN=!CURRENT_URL_CLEAN:~0,-4!
    if "!GITHUB_URL_CLEAN:~-4!"==".git" set GITHUB_URL_CLEAN=!GITHUB_URL_CLEAN:~0,-4!
    
    if not "!CURRENT_URL_CLEAN!"=="!GITHUB_URL_CLEAN!" (
        echo [提示] 远程地址不匹配，正在更新...
        echo   当前: !CURRENT_URL!
        echo   目标: !GITHUB_URL!
        git remote set-url origin !GITHUB_URL!
        echo [成功] 远程地址已更新
        echo.
    )
    
    echo [步骤] 检查远程分支...
    git ls-remote --heads origin main >nul 2>&1
    if %errorlevel% equ 0 (
        echo [成功] 远程分支 main 存在
    ) else (
        echo [提示] 远程分支 main 不存在，检查 master 分支...
        git ls-remote --heads origin master >nul 2>&1
        if %errorlevel% equ 0 (
            echo [提示] 远程使用 master 分支，将使用 master 拉取
            set BRANCH_NAME=master
        ) else (
            echo [警告] 远程仓库可能为空，将尝试创建初始连接
            set BRANCH_NAME=main
        )
    )
    echo.
    
    echo [步骤] 检查并处理文件冲突...
    REM 先尝试fetch查看远程文件
    git fetch origin main >nul 2>&1
    
    REM 检查未跟踪的文件是否与远程冲突
    for /f "tokens=*" %%f in ('git ls-tree -r --name-only origin/main 2^>nul') do (
        if exist "%%f" (
            git status --porcelain "%%f" | findstr "^??" >nul 2>&1
            if !errorlevel! equ 0 (
                echo [警告] 本地未跟踪文件 %%f 与远程文件冲突
                echo [处理] 备份为 %%f.local 并删除原文件...
                if not exist "%%f.local" (
                    copy "%%f" "%%f.local" >nul 2>&1
                    echo [成功] 已备份到 %%f.local
                )
                del "%%f" >nul 2>&1
            )
        )
    )
    echo.
    
    echo [步骤] 正在拉取最新代码...
    
    REM 先尝试普通拉取
    git pull origin main
    
    if %errorlevel% neq 0 (
        REM 检查是否是文件覆盖错误
        git pull origin main 2>&1 | findstr /C:"would be overwritten" >nul 2>&1
        if %errorlevel% equ 0 (
            echo [提示] 检测到文件覆盖冲突，使用强制策略...
            REM 使用ours策略，优先使用远程版本
            git pull origin main -X theirs --allow-unrelated-histories
            if %errorlevel% equ 0 (
                echo [成功] 已使用远程版本覆盖本地文件
            )
        )
        
        if %errorlevel% neq 0 (
            echo [提示] 普通拉取失败，尝试合并不相关的历史...
            REM 如果普通拉取失败，尝试允许不相关的历史合并
            git pull origin main --allow-unrelated-histories
        )
        
        if %errorlevel% equ 0 (
            echo.
            echo [成功] 代码更新成功（已合并不相关的历史）
        ) else (
            echo.
            echo [错误] 代码更新失败
            echo.
            echo 可能的原因：
            echo 1. 远程仓库不存在或地址错误
            echo 2. 网络连接问题
            echo 3. GitHub认证失败（需要Personal Access Token）
            echo 4. 分支名称不匹配（远程可能是master而不是main）
            echo.
            echo [调试信息] 正在检查远程仓库...
            git ls-remote origin 2>nul
            if %errorlevel% neq 0 (
                echo [错误] 无法连接到远程仓库，请检查：
                echo   - 仓库地址是否正确: !GITHUB_URL!
                echo   - 网络连接是否正常
                echo   - GitHub认证是否配置
            )
            pause
            exit /b 1
        )
    ) else (
        echo.
        echo [成功] 代码更新成功
    )
) else (
    echo [提示] 远程仓库未配置，正在配置...
    git remote add origin !GITHUB_URL!
    echo [成功] 远程仓库已配置
    echo.
    
    echo [步骤] 检查远程分支...
    git ls-remote --heads origin main >nul 2>&1
    if %errorlevel% equ 0 (
        echo [成功] 远程分支 main 存在
    ) else (
        echo [提示] 远程分支 main 不存在，检查 master 分支...
        git ls-remote --heads origin master >nul 2>&1
        if %errorlevel% equ 0 (
            echo [提示] 远程使用 master 分支，将使用 master 拉取
            set BRANCH_NAME=master
        ) else (
            echo [警告] 远程仓库可能为空，将尝试创建初始连接
            set BRANCH_NAME=main
        )
    )
    echo.
    
    echo [步骤] 检查并处理文件冲突...
    REM 先尝试fetch查看远程文件
    git fetch origin main >nul 2>&1
    
    REM 检查未跟踪的文件是否与远程冲突
    for /f "tokens=*" %%f in ('git ls-tree -r --name-only origin/main 2^>nul') do (
        if exist "%%f" (
            git status --porcelain "%%f" | findstr "^??" >nul 2>&1
            if !errorlevel! equ 0 (
                echo [警告] 本地未跟踪文件 %%f 与远程文件冲突
                echo [处理] 备份为 %%f.local 并删除原文件...
                if not exist "%%f.local" (
                    copy "%%f" "%%f.local" >nul 2>&1
                    echo [成功] 已备份到 %%f.local
                )
                del "%%f" >nul 2>&1
            )
        )
    )
    echo.
    
    echo [步骤] 正在拉取最新代码...
    
    REM 先尝试普通拉取
    git pull origin main
    
    if %errorlevel% neq 0 (
        REM 检查是否是文件覆盖错误
        git pull origin main 2>&1 | findstr /C:"would be overwritten" >nul 2>&1
        if %errorlevel% equ 0 (
            echo [提示] 检测到文件覆盖冲突，使用强制策略...
            REM 使用ours策略，优先使用远程版本
            git pull origin main -X theirs --allow-unrelated-histories
            if %errorlevel% equ 0 (
                echo [成功] 已使用远程版本覆盖本地文件
            )
        )
        
        if %errorlevel% neq 0 (
            echo [提示] 普通拉取失败，尝试合并不相关的历史...
            REM 如果普通拉取失败，尝试允许不相关的历史合并
            git pull origin main --allow-unrelated-histories
        )
        
        if %errorlevel% equ 0 (
            echo.
            echo [成功] 代码更新成功（已合并不相关的历史）
        ) else (
            echo.
            echo [错误] 代码更新失败
            echo.
            echo 可能的原因：
            echo 1. 远程仓库不存在或地址错误
            echo 2. 网络连接问题
            echo 3. GitHub认证失败（需要Personal Access Token）
            echo 4. 分支名称不匹配（远程可能是master而不是main）
            echo.
            echo [提示] 如果这是首次配置，可能需要先推送代码到GitHub
            echo [提示] 请先运行 1push.bat 推送初始代码
            echo.
            echo [调试信息] 正在检查远程仓库...
            git ls-remote origin 2>nul
            if %errorlevel% neq 0 (
                echo [错误] 无法连接到远程仓库，请检查：
                echo   - 仓库地址是否正确: !GITHUB_URL!
                echo   - 网络连接是否正常
                echo   - GitHub认证是否配置
            )
            pause
            exit /b 1
        )
    ) else (
        echo.
        echo [成功] 代码更新成功
    )
)

echo.
echo ============================================
echo [提示] 请确保已配置正确的GitHub仓库地址
echo 当前配置的地址: !GITHUB_URL!
echo ============================================
pause
