# GitHub 重新认证指南

## 步骤 1：生成 Personal Access Token (PAT)

1. 登录 GitHub：https://github.com
2. 点击右上角头像 → **Settings（设置）**
3. 左侧菜单最下方，点击 **Developer settings（开发者设置）**
4. 点击 **Personal access tokens** → **Tokens (classic)**
5. 点击 **Generate new token** → **Generate new token (classic)**
6. 填写信息：
   - **Note（备注）**：DemoVote项目（可自定义）
   - **Expiration（过期时间）**：根据需要选择（建议选择90天或自定义）
   - **Select scopes（选择权限）**：勾选以下权限
     - ✅ `repo` （全部仓库权限）
     - ✅ `workflow` （如果需要GitHub Actions）
7. 点击 **Generate token（生成令牌）**
8. **重要**：立即复制生成的 token（只显示一次！格式类似：`ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`）

## 步骤 2：清除 Windows 凭据管理器中的旧凭据

### 方法一：使用 Windows 凭据管理器（图形界面）

1. 按 `Win + R`，输入 `control /name Microsoft.CredentialManager`，回车
2. 点击 **Windows 凭据**
3. 找到所有 `git:https://github.com` 相关的条目
4. 逐个点击 **删除** 或 **编辑**（建议删除后重新添加）

### 方法二：使用命令行清除（推荐）

打开 PowerShell 或 CMD，执行以下命令：

```powershell
# 查看现有凭据
cmdkey /list | Select-String "git:https://github.com"

# 删除 GitHub 凭据
cmdkey /delete:git:https://github.com

# 如果上面命令没有找到，尝试这些
cmdkey /delete:LegacyGeneric:target=git:https://github.com
cmdkey /delete:git:https://github.com/linmiaoyan/DemoVote.git
```

## 步骤 3：重新认证（推送时会要求输入）

### 方法一：使用 Git 推送时认证

在项目目录下执行：

```bash
git push origin master
```

当提示输入用户名和密码时：
- **Username（用户名）**：输入你的 GitHub 用户名 `linmiaoyan`
- **Password（密码）**：输入刚才生成的 **Personal Access Token**（不是GitHub密码！）

### 方法二：在 URL 中嵌入 token（临时方法）

```bash
git remote set-url origin https://你的用户名:你的token@github.com/linmiaoyan/DemoVote.git
```

示例：
```bash
git remote set-url origin https://linmiaoyan:ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx@github.com/linmiaoyan/DemoVote.git
```

**注意**：此方法会在 URL 中暴露 token，不建议长期使用。

## 步骤 4：测试认证

执行以下命令测试：

```bash
git push origin master
```

如果成功，说明认证已完成。

## 常见问题

### Q: 为什么不能用密码？
A: GitHub 从 2021年8月13日 起，不再支持密码认证，必须使用 Personal Access Token。

### Q: Token 丢失了怎么办？
A: 需要重新生成一个新的 Token，旧的 Token 即使还记得也不能重复使用。

### Q: 如何让 Git 记住凭据？
A: Windows 的 Git Credential Manager 会自动保存凭据到 Windows 凭据管理器，下次推送时不需要重新输入。

### Q: 每次都要输入 token 吗？
A: 第一次输入后，Windows 凭据管理器会保存，之后会自动使用。

## 快速认证脚本

你也可以创建一个批处理文件 `重新认证.bat`：

```batch
@echo off
chcp 65001 >nul
echo ============================================
echo GitHub 重新认证
echo ============================================
echo.
echo 步骤 1：清除旧凭据
cmdkey /delete:git:https://github.com 2>nul
cmdkey /delete:LegacyGeneric:target=git:https://github.com 2>nul
echo [完成] 已清除旧凭据
echo.
echo 步骤 2：请准备好你的 Personal Access Token
echo 如果还没有，请访问：https://github.com/settings/tokens
echo.
pause
echo.
echo 步骤 3：测试推送（会要求输入用户名和token）
echo.
git push origin master
echo.
pause
```

## SSL 证书错误修复

如果遇到以下错误：
```
fatal: unable to access 'https://github.com/...': schannel: next InitializeSecurityContext failed: Unknown error (0x80096004)
```

### 快速修复方法

**方法一：使用修复脚本（推荐）**
1. 运行 `修复SSL错误.bat`
2. 按照提示选择修复方案

**方法二：手动修复**

1. **切换到 OpenSSL 后端（如果可用）**：
   ```bash
   git config --global http.sslBackend openssl
   ```

2. **临时禁用 SSL 验证（不推荐，仅用于紧急情况）**：
   ```bash
   git config --global http.sslVerify false
   ```
   ⚠️ **警告**：这会降低安全性，问题解决后请重新启用：
   ```bash
   git config --global http.sslVerify true
   ```

3. **检查并更新远程 URL**：
   ```bash
   git remote set-url origin https://github.com/linmiaoyan/DemoVote.git
   ```

### SSL 错误的常见原因

1. Windows 证书存储问题
2. 企业防火墙/代理拦截
3. Git 的 Schannel 后端证书验证失败
4. 网络环境限制

### 其他解决方案

如果上述方法无效，可以尝试：
- 更新 Git 到最新版本
- 检查 Windows 证书存储
- 联系网络管理员检查企业证书配置
- 使用 VPN 或更换网络环境

## 重要提示

⚠️ **安全建议**：
- Token 请妥善保管，不要分享给他人
- 如果 token 泄露，立即在 GitHub 上删除它并重新生成
- 不要将 token 提交到代码仓库中
- 建议设置 token 的过期时间，定期更换
- 避免长期禁用 SSL 验证，存在安全风险