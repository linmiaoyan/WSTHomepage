# 系统架构设计文档

## 一、系统概述

教师数据自填系统是一个用于管理教师个人信息数据库的Web应用系统，支持从数据库自动提取信息并批量填充到不同格式的表格中。

## 二、技术架构

### 2.1 后端架构

```
FastAPI (Python Web框架)
├── SQLAlchemy (ORM数据库操作)
├── python-docx (Word文档处理)
├── openpyxl (Excel文档处理)
└── pandas (数据处理)
```

**核心模块：**
- `app/main.py`: FastAPI主应用，路由注册
- `app/models.py`: 数据库模型定义
- `app/database.py`: 数据库连接和初始化
- `app/routers/`: API路由模块
  - `teachers.py`: 教师信息管理
  - `templates.py`: 模板管理
  - `tasks.py`: 填报任务
  - `questionnaires.py`: 问卷系统
- `app/services/`: 业务逻辑服务
  - `template_processor.py`: 模板处理和填充
  - `file_handler.py`: 文件处理（占位符提取）
  - `export_service.py`: 批量导出服务
- `app/utils/`: 工具函数
  - `validators.py`: 数据验证和清洗

### 2.2 前端架构

```
HTML + JavaScript + Bootstrap
├── 单页应用（SPA）
├── RESTful API调用
└── 响应式设计
```

**核心文件：**
- `templates/index.html`: 主页面
- `static/js/main.js`: 前端逻辑

### 2.3 数据库设计

**表结构：**

1. **teachers** - 教师信息表
   - 基础字段：name, sex, id_number, phone, email, department, position, title
   - 扩展字段：extra_data (JSON格式，存储动态字段)

2. **templates** - 模板表
   - 存储模板文件路径、类型、占位符列表

3. **tasks** - 填报任务表
   - 关联模板和教师列表，记录任务状态和导出路径

4. **questionnaires** - 问卷表
   - 存储问卷定义（字段、填写人员范围）

5. **questionnaire_responses** - 问卷回答表
   - 存储回答内容和审核状态

## 三、核心功能流程

### 3.1 模板填报流程

```
1. 上传模板文件（Word/Excel）
   ↓
2. 系统自动提取占位符（或手动标注）
   ↓
3. 创建填报任务
   - 选择模板
   - 选择填表人员范围
   ↓
4. 后台批量处理
   - 为每个教师填充模板
   - 生成填好的表格
   ↓
5. 打包成ZIP文件
   ↓
6. 下载导出文件
```

### 3.2 问卷数据收集流程

```
1. 创建问卷
   - 定义字段（名称、类型、是否必填）
   - 选择填写人员范围
   ↓
2. 教师填写问卷
   - 提交回答数据
   ↓
3. 管理员审核
   - 查看提交的回答
   - 审核通过/拒绝
   ↓
4. 数据合并
   - 审核通过的数据自动合并到教师信息数据库
   - 存储到extra_data字段
```

## 四、大模型集成点（标记）

以下功能可以集成大模型来增强智能化：

### 4.1 自动占位符识别 ⭐ LLM

**位置**: `app/services/file_handler.py` - `llm_extract_placeholders()`

**功能**: 
- 自动识别Word/Excel中需要填充的位置
- 无需手动标注占位符
- 智能理解表格结构

**所需模型**: 视觉-语言模型（如GPT-4V、Claude Vision）

**实现方式**:
```python
# 1. 将文档转换为图片
# 2. 调用视觉-语言模型分析
# 3. 返回字段映射关系
```

### 4.2 智能表格结构提取 ⭐ LLM

**位置**: `app/services/file_handler.py` - `llm_extract_table_structure()`

**功能**:
- 自动识别复杂表格结构
- 提取字段映射关系
- 理解表格语义

**所需模型**: 多模态大模型

### 4.3 自动模板标注 ⭐ LLM

**位置**: `app/services/file_handler.py` - `llm_auto_annotate_template()`

**功能**:
- 自动识别需要填充的字段
- 自动添加占位符（如{{name}}）
- 减少人工标注工作量

### 4.4 数据验证和清洗 ⭐ LLM

**位置**: `app/utils/validators.py` - `llm_validate_and_correct()`

**功能**:
- 智能识别数据错误
- 自动修正格式问题
- 数据一致性检查

**所需模型**: 文本处理大模型（如GPT-4、Claude）

**实现方式**:
```python
# 调用大模型API进行数据验证和修正
# 返回清洗后的数据
```

## 五、文件结构

```
教师数据自填系统/
├── app/                      # 应用主目录
│   ├── __init__.py
│   ├── main.py              # FastAPI主应用
│   ├── models.py            # 数据库模型
│   ├── database.py          # 数据库连接
│   ├── routers/             # API路由
│   │   ├── __init__.py
│   │   ├── teachers.py
│   │   ├── templates.py
│   │   ├── tasks.py
│   │   └── questionnaires.py
│   ├── services/            # 业务逻辑
│   │   ├── __init__.py
│   │   ├── template_processor.py
│   │   ├── file_handler.py  # ⭐ LLM集成点
│   │   └── export_service.py
│   └── utils/               # 工具函数
│       ├── __init__.py
│       └── validators.py    # ⭐ LLM集成点
├── static/                  # 静态文件
│   ├── css/
│   ├── js/
│   │   └── main.js
│   └── uploads/             # 上传文件存储
│       ├── templates/       # 模板文件
│       └── exports/         # 导出文件
├── templates/               # 前端模板
│   └── index.html
├── config.py               # 配置文件
├── requirements.txt         # Python依赖
├── README.md               # 使用说明
└── ARCHITECTURE.md         # 架构文档（本文件）
```

## 六、部署说明

### 6.1 开发环境

```bash
# 安装依赖
pip install -r requirements.txt

# 初始化数据库
python -m app.database

# 运行服务
uvicorn app.main:app --reload
```

### 6.2 生产环境

- 使用Gunicorn + Uvicorn作为WSGI服务器
- 配置Nginx作为反向代理
- 使用PostgreSQL替代SQLite
- 配置环境变量（数据库连接、大模型API密钥等）

## 七、扩展建议

1. **用户认证系统**: 添加登录、权限管理
2. **数据导入**: 支持批量导入教师数据（Excel/CSV）
3. **数据导出**: 支持导出教师数据
4. **操作日志**: 记录所有操作历史
5. **通知系统**: 任务完成、问卷提交等通知
6. **数据统计**: 数据统计和报表功能

