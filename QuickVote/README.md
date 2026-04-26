# QuickVote 投票系统

一个基于 Flask 的独立投票/问卷系统，支持二维码登录、单选题和表格题两种问卷类型。

## 功能特性

- ✅ 二维码登录系统
- ✅ 单选题问卷（支持选项限制）
- ✅ 表格题问卷（支持多人评价）
- ✅ 主观题回答
- ✅ 二维码批量生成（PDF格式）
- ✅ 投票结果导出（Excel格式）
- ✅ 管理员后台管理

## 快速开始

### 1. 环境要求

- Python 3.7 或更高版本
- Windows / Linux / macOS

### 2. 安装依赖

```bash
pip install -r requirement.txt
```

### 3. 运行程序

#### Windows 用户（推荐）

双击运行 `run.bat` 文件，或在命令行中执行：

```bash
run.bat
```

#### Linux/macOS 用户

```bash
python run.py
```

或使用 Python 模块方式：

```bash
python -m app
```

### 4. 访问系统

启动成功后，在浏览器中访问：

- **首页**: http://localhost:5000
- **管理员登录**: 在首页使用账号密码登录（默认账号：`admin`，密码：`admin123`）

## 配置说明

### 环境变量配置（推荐使用 .env 文件）

**推荐方式：使用 .env 文件**

1. 复制 `env.example` 文件为 `.env`：
   ```bash
   cp env.example .env
   ```

2. 编辑 `.env` 文件，修改配置值：
   ```env
   HOST=0.0.0.0
   PORT=5005
   DEBUG=False
   SECRET_KEY=your-secret-key-here-change-this-in-production
   PUBLIC_HOST=
   ```

3. `.env` 文件不会被提交到 git，可以安全地存储敏感信息。

**或者使用环境变量（不推荐用于生产环境）**

```bash
# Windows PowerShell
$env:HOST="0.0.0.0"
$env:PORT="5005"
$env:DEBUG="False"
$env:PUBLIC_HOST="http://your-domain.com/"
$env:SECRET_KEY="your_secret_key"

# Linux/macOS
export HOST=0.0.0.0
export PORT=5005
export DEBUG=False
export PUBLIC_HOST=http://your-domain.com/
export SECRET_KEY=your_secret_key
```

### 配置项说明

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `HOST` | `0.0.0.0` | 服务器监听地址 |
| `PORT` | `5005` | 服务器端口 |
| `DEBUG` | `False` | 调试模式（True/False） |
| `PUBLIC_HOST` | 自动获取 | 二维码中的公网地址（留空则自动获取） |
| `SECRET_KEY` | 自动生成 | Flask 会话密钥 |

## 使用说明

### 1. 创建问卷

1. 在首页使用管理员账号密码登录
2. 点击"创建新问卷"
3. 选择问卷类型：
   - **单选题**：每个问题有多个选项（A、B、C、D等）
   - **表格题**：多个问题 × 多个人名的评价表格
4. 填写问卷名称和简介
5. 添加问题

### 2. 生成二维码

1. 在问卷管理页面，输入需要生成的二维码数量
2. 点击"生成二维码"
3. 下载 PDF 文件并打印

### 3. 投票

1. 扫描二维码或访问二维码中的链接
2. 自动登录并进入投票页面
3. 完成所有问题后提交

### 4. 查看结果

1. 在管理员页面，点击"查看结果"
2. 下载 Excel 文件，包含：
   - 原始数据
   - 按问题排列的数据
   - 统计结果

## 目录结构

```
QuickVote/
├── app.py                 # 主应用文件（独立运行版本）
├── blueprint.py           # Blueprint版本（用于集成到其他应用）
├── run.py                 # 启动脚本
├── run.bat                # Windows启动脚本
├── requirement.txt        # Python依赖列表
├── README.md             # 本文件
├── instance/             # 数据目录
│   └── votes.db         # SQLite数据库
├── templates/            # HTML模板
│   ├── admin.html
│   ├── index.html
│   ├── vote.html
│   └── ...
└── static/               # 静态资源
    ├── css/
    ├── js/
    └── images/
```

## 数据库

系统使用 SQLite 数据库，数据库文件位于 `instance/votes.db`。

首次运行时会自动创建数据库表和默认管理员账号：
- 用户名：`admin`
- 密码：`admin123`（用于管理员登录后台）

## 常见问题

### Q: 端口被占用怎么办？

A: 修改 `PORT` 环境变量或直接编辑 `run.py` 中的端口号。

### Q: 二维码中的链接不正确？

A: 设置 `PUBLIC_HOST` 环境变量为你的公网地址，例如：`http://your-domain.com/`

### Q: 如何备份数据？

A: 直接复制 `instance/votes.db` 文件即可。

### Q: 如何重置管理员账号？

A: 删除 `instance/votes.db` 文件，重新运行程序会自动创建。

## 技术栈

- Flask - Web框架
- SQLAlchemy - ORM数据库操作
- Flask-Login - 用户认证
- QRCode - 二维码生成
- ReportLab - PDF生成
- Pandas + OpenPyXL - Excel导出
- Pillow - 图像处理

## 许可证

本项目仅供内部使用。

## 更新日志

### v1.0.0
- 初始版本
- 支持单选题和表格题
- 二维码登录系统
- 管理员后台
- 结果导出功能

