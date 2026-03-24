@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul

echo ============================================
echo Git 提交并推送
echo ============================================
echo.

cd /d "%~dp0"

REM 检查Git是否安装
git --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Git，请先安装 Git for Windows
    pause
    exit /b 1
)

REM 检查是否是Git仓库，如果不是则初始化
if not exist ".git" (
    echo [提示] 当前目录不是Git仓库，正在初始化...
    git init
    if %errorlevel% neq 0 (
        echo [错误] Git仓库初始化失败
        pause
        exit /b 1
    )
    echo [成功] Git仓库初始化完成
    echo.
    
    REM 设置默认分支为main（如果Git版本支持）
    git branch -M main >nul 2>&1
)

REM 检查并配置远程仓库
git remote -v | findstr "origin" >nul 2>&1
if %errorlevel% neq 0 (
    echo [提示] 未检测到远程仓库，正在添加...
    git remote add origin https://github.com/linmiaoyan/DemoVote.git
    if %errorlevel% neq 0 (
        echo [警告] 添加远程仓库失败，尝试删除后重新添加...
        git remote remove origin >nul 2>&1
        git remote add origin https://github.com/linmiaoyan/DemoVote.git
        if %errorlevel% neq 0 (
            echo [错误] 添加远程仓库失败
            pause
            exit /b 1
        )
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

echo [步骤1] 添加所有文件
git add .
if %errorlevel% neq 0 (
    echo [错误] 添加文件失败
    pause
    exit /b 1
)
echo [成功] 文件已添加到暂存区
echo.

echo [步骤2] 提交更改
echo.
set /p commit_msg="请输入提交描述: "

if "!commit_msg!"=="" (
    echo [错误] 提交描述不能为空
    pause
    exit /b 1
)

git commit -m "!commit_msg!"
if %errorlevel% neq 0 (
    echo [错误] 提交失败
    pause
    exit /b 1
)
echo [成功] 代码已提交
echo.

echo [步骤3] 推送到GitHub
echo [提示] 当前分支: !CURRENT_BRANCH!
REM 检查是否有提交（如果是新仓库）
git rev-parse --verify HEAD >nul 2>&1
if %errorlevel% neq 0 (
    REM 新仓库，没有提交历史，需要设置上游分支
    echo [提示] 首次推送，设置上游分支...
    git push -u origin !CURRENT_BRANCH!
) else (
    REM 已有提交历史
    git push origin !CURRENT_BRANCH!
)
if %errorlevel% equ 0 (
    echo.
    echo ============================================
    echo [成功] 代码已推送到GitHub
    echo ============================================
    echo.
    echo 仓库地址：https://github.com/linmiaoyan/DemoVote
    echo.
) else (
    echo.
    echo [错误] 推送失败
    echo.
    echo 可能的原因：
    echo   1. 网络连接问题
    echo   2. 认证失败（需要Personal Access Token）
    echo   3. 权限不足
    echo   4. 分支名称不匹配（当前分支: !CURRENT_BRANCH!）
    echo   5. 远程仓库配置错误
    echo.
    echo [提示] 检查远程仓库配置：
    git remote -v
    echo.
)

pause
