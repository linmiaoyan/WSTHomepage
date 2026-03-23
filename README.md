# WSTHompage

学校管理中心与门户系统（Flask 单进程）。

## 目录说明

- `server.py`：后端主程序（Flask），包含管理中心审批、教师数据、问卷 API。
- `public/`：前端静态资源根目录（入口页、样式、脚本、子页面）。
- `keadmin_queue.db`：本地 SQLite 数据库（审批队列 + 教师数据 + 问卷）。
- `1push.bat`：提交并推送到 GitHub（交互版）。
- `2pull_normal.bat`：常规拉取更新。
- `3pull_force.bat`：强制与远端同步（会丢弃本地未提交改动）。
- `docs/shortcuts/`：本地快捷方式收纳目录（不影响程序运行）。

## 启动方式

在项目根目录执行：

```bash
python server.py
```

默认端口：`8000`

常用入口：

- 管理中心：`http://127.0.0.1:8000/admin`
- 门户首页：`http://127.0.0.1:8000/portal`
- 教师入口：`http://127.0.0.1:8000/teacher`

## 静态目录规则

`server.py` 默认优先使用 `public/` 作为静态根目录。

- 若 `public/index.html` 存在：使用 `public/`
- 否则自动回退到项目根目录（兼容模式）

你也可以在 `.env` 中通过 `WEB_ROOT_DIR` 指定其他静态目录。

## 说明

- `.env`、`*.db`、日志等已在 `.gitignore` 中忽略，避免误提交。
- 若执行 `3pull_force.bat`，请先确认本地改动已提交或备份。
