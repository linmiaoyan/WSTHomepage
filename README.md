# WSTHompage

学校管理中心与门户系统，主站基于 Flask。

## 目录说明

- `server.py`：主站后端，包含审批队列、钉钉登录、车牌、周期请假、网络密码、校章等能力
- `public/`：主站静态资源目录
- `keadmin_queue.db`：本地 SQLite 数据库，当前用于审批队列
- `run_stack.py`：一键拉起主站、原版 QuickVote、原版 TeacherDataSystem
- `vendor/`：原版子系统备份目录

## 启动方式

### 仅启动主站

```bash
python server.py
```

端口由环境变量 `PORT` 控制，默认 `8000`。

### 启动主站 + 原版 QuickVote + 原版 TeacherDataSystem

```bash
python run_stack.py
```

也可使用 `start_stack.bat`。默认端口：

- 主站：`8000`
- QuickVote：`8001`
- TeacherDataSystem：`8002`

可在 `.env` 中调整。

## 主站入口

- 统一主页（管理中心）：`http://127.0.0.1:8000/index.html`
- 教师申请：`http://127.0.0.1:8000/teacher.html`

`/home.html` 已保留为兼容跳转页，会自动跳到 `/index.html`。

教师申请页新增「问卷填写」标签：主站会以身份证号+手机号验证后，直接读取并提交 TeacherDataSystem 发起的问卷（主站入口统一，TeacherDataSystem 作为后端数据源）。

主站内不再提供简化版教师数据和简化版问卷页面；如需进入原版子系统，请先进入管理中心，再通过：

- `/go/quickvote`
- `/go/teacher-data-system`
- `/go/teacher-questionnaire`（教师问卷填写统一入口，默认跳转 TeacherDataSystem 的 `/teacher/dashboard`）

进行跳转。

## 原版子系统

原版 QuickVote 与原版 TeacherDataSystem 需独立运行，并通过主站聚合。请在 `.env` 中配置：

- `QUICKVOTE_PUBLIC_URL`
- `TEACHERDATA_PUBLIC_URL`

用于管理中心跳转到实际可访问地址。

## 说明

- `.env`、`*.db`、日志等已在 `.gitignore` 中忽略
- 执行强制拉取脚本前，请先确认本地改动已提交或备份
