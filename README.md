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

### 仅主站（审批 / 门户）

```bash
python server.py
```

端口由环境变量 `PORT` 控制，默认 `8000`。

### 主站 + 原版 QuickVote + 原版 TeacherDataSystem

民主测评（二维码、原模板）与教师数据系统（PDF 模板、任务、教师库）来自备份项目，需**单独进程**运行，与主站合并见 `vendor/README.md`。

```bash
python run_stack.py
```

或使用 `start_stack.bat`。默认端口：主站 `8000`、QuickVote `5005`、TeacherDataSystem `8001`（可在 `.env` 修改）。

门户与管理中心通过 `/go/quickvote`、`/go/teacher-data-system` 跳转；请在 `.env` 设置 `QUICKVOTE_PUBLIC_URL`、`TEACHERDATA_PUBLIC_URL` 为实际访问地址（公网或反代后的 URL），以便 QuickVote 生成二维码正确。

常用入口：

- 门户首页：`http://127.0.0.1:8000/home.html`（或根路径静态入口）
- 管理中心：`http://127.0.0.1:8000/index.html`
- 原版 QuickVote：`http://127.0.0.1:5005/`（未改端口时）
- 原版教师数据：`http://127.0.0.1:8001/query`（未改端口时）

## 静态目录规则

`server.py` 默认优先使用 `public/` 作为静态根目录。

- 若 `public/index.html` 存在：使用 `public/`
- 否则自动回退到项目根目录（兼容模式）

你也可以在 `.env` 中通过 `WEB_ROOT_DIR` 指定其他静态目录。

## 说明

- `.env`、`*.db`、日志等已在 `.gitignore` 中忽略，避免误提交。
- 若执行 `3pull_force.bat`，请先确认本地改动已提交或备份。
