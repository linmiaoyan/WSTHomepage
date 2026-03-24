# 教师数据自填系统

## 系统概述

这是一个用于管理教师个人信息数据库的系统，支持从数据库自动提取信息并批量填充到不同格式的表格中（Word、Excel等）。

## 核心功能

1. **教师信息数据库管理**
   - 集中存储所有教师个人信息
   - 支持增删改查操作

2. **模板填报系统**
   - 上传待填写文件（Word/Excel）
   - 手动标注占位符（如{{name}}、{{sex}}）
   - 选择填表人员范围
   - 批量导出填好的表格

3. **问卷数据收集**
   - 发起问卷收集新数据
   - 管理员审核问卷数据
   - 审核后自动合并到数据库

## 技术架构

### 后端
- **框架**: FastAPI
- **数据库**: SQLite（开发）/ PostgreSQL（生产）
- **文件处理**: python-docx, openpyxl, pandas

### 前端
- **技术**: HTML + JavaScript + Bootstrap
- **交互**: 单页应用（SPA）

### 目录结构
```
教师数据自填系统/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI主应用
│   ├── models.py            # 数据库模型
│   ├── database.py          # 数据库连接
│   ├── routers/             # API路由
│   │   ├── __init__.py
│   │   ├── teachers.py      # 教师信息管理
│   │   ├── templates.py     # 模板管理
│   │   ├── tasks.py         # 填报任务
│   │   ├── questionnaires.py # 问卷系统
│   │   └── export.py        # 批量导出
│   ├── services/            # 业务逻辑
│   │   ├── __init__.py
│   │   ├── template_processor.py  # 模板处理
│   │   ├── file_handler.py        # 文件处理
│   │   └── export_service.py      # 导出服务
│   └── utils/               # 工具函数
│       ├── __init__.py
│       └── validators.py    # 数据验证
├── static/                  # 静态文件
│   ├── css/
│   ├── js/
│   └── uploads/            # 上传文件存储
├── templates/              # 前端模板
│   ├── index.html
│   ├── teachers.html
│   ├── templates.html
│   ├── tasks.html
│   └── questionnaires.html
├── requirements.txt         # Python依赖
├── config.py               # 配置文件
└── README.md

```

## 使用大模型的部分（标记）

以下功能可以集成大模型来增强智能化：

1. **自动占位符识别**（可选）
   - 位置: `app/services/template_processor.py`
   - 功能: 自动识别Word/Excel中需要填充的位置，生成占位符
   - 模型: 视觉-语言模型（如GPT-4V、Claude Vision）

2. **智能表格结构提取**（可选）
   - 位置: `app/services/file_handler.py`
   - 功能: 自动识别复杂表格结构，提取字段映射关系
   - 模型: 多模态大模型

3. **数据验证和清洗**（可选）
   - 位置: `app/utils/validators.py`
   - 功能: 智能识别和修正数据错误
   - 模型: 文本处理大模型

## 安装和运行

1. 安装依赖：
```bash
pip install -r requirements.txt
```

2. 初始化数据库：
```bash
python -m app.database init
```

3. 运行服务：
```bash
uvicorn app.main:app --reload
```

4. 访问系统：
打开浏览器访问 `http://localhost:8000`

## 使用说明

### 1. 教师信息管理
- 添加/编辑/删除教师信息
- 支持批量导入

### 2. 创建填报任务
1. 上传模板文件（Word/Excel）
2. 在文件中标注占位符（如{{name}}、{{sex}}）
3. 选择需要填写的教师范围
4. 点击"批量导出"生成填好的表格

### 3. 问卷数据收集
1. 创建问卷，定义需要收集的字段
2. 选择填写人员范围
3. 填写人员提交数据
4. 管理员审核数据
5. 审核通过后自动合并到数据库

