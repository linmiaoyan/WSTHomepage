# 原版子系统（QuickVote + TeacherDataSystem）

WSTHompage 主站（`server.py`）里的 `/api/quickvote/*` 与 `/api/teacher-data/*` 仅为**轻量占位**，**不能**替代以下两个备份项目中的完整逻辑与界面。

## 你需要做什么

1. 将 `09教育技术处/【旧项目备份】/QuickVote` **整份复制**到本目录下，命名为 **`QuickVote`**（与 `vendor/QuickVote/app.py` 同级）。
2. 将 `09教育技术处/【旧项目备份】/TeacherDataSystem` **整份复制**到本目录下，命名为 **`TeacherDataSystem`**（与 `vendor/TeacherDataSystem/app/main.py` 同级）。

若希望不复制、直接使用备份路径，可在项目根目录 `.env` 中设置：

- `QUICKVOTE_ROOT=D:\...\【旧项目备份】\QuickVote`
- `TEACHERDATA_ROOT=D:\...\【旧项目备份】\TeacherDataSystem`

## 依赖安装

在**同一 Python 环境**中分别安装（版本以各项目 `requirement.txt` / `requirements.txt` 为准）：

```bash
pip install -r vendor/QuickVote/requirement.txt
pip install -r vendor/TeacherDataSystem/requirements.txt
```

## 启动方式

在项目根目录执行 **`python run_stack.py`**（或 `start_stack.bat`），会同时启动：

- 主站：`PORT`（默认 `8000`）
- QuickVote：`QUICKVOTE_PORT`（默认 `5005`）
- TeacherDataSystem：`TEACHERDATA_PORT`（默认 `8001`，避免与主站冲突）

门户与管理中心中的「原版」入口通过 `/go/quickvote`、`/go/teacher-data-system` 跳转；请在 `.env` 中配置 **`QUICKVOTE_PUBLIC_URL`**、**`TEACHERDATA_PUBLIC_URL`** 为实际访问地址（公网或反向代理后的 URL），以便 **QuickVote 生成二维码**时指向正确主机。

## TeacherDataSystem 说明

原项目 `config.py` 中的 `QUICKJUDGE_ROOT_DIR` 等路径与「兄弟目录 QuickJudge」有关；若仅迁移本目录，VL 辅助功能可能需单独配置或忽略。
