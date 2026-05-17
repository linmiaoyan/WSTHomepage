# WSTHompage

学校门户与**管理中心**（Flask）：钉钉登录、教师申请与审批队列、周期请假/车牌/校章等 API；静态页在 `public/`。

## 项目结构

| 路径 | 说明 |
| --- | --- |
| `server.py` | 唯一入口：开发服务器；可选一键拉起子系统（见下） |
| `public/` | 主站前端静态资源（`index.html`、`teacher.html` 等） |
| `keadmin_queue.db` | 审批队列（SQLite，本地文件） |
| `QuickVote/` | 原版 QuickVote 源码（投票系统） |
| `TeacherDataSystem/` | 原版 TeacherDataSystem 源码 |
| `vendor/` | 备份/脚本/补充文档（见 `vendor/README.md`） |
| `docs/` | 钉钉与安全等补充说明 |

## 环境

- 在根目录按各功能需要配置 `.env`；密钥与本地 `.db` 勿提交（见 `.gitignore`）。
- 大模型等密钥变量名以 `server.py` 中 `_env_get` 为准。

### 多管理组与口令（可选）

- 在 `.env` 设置 **`ADMIN_MASTER_CODE`**（主管理员口令）后，启用多管理组模式：各组口令与权限保存在 `keadmin_queue.db` 的 `admin_groups` 表；主管理员在「管理中心 → 管理组与口令」中配置。
- 未设置 `ADMIN_MASTER_CODE` 时，仍可使用单一 **`ADMIN_GATE_CODE`**（旧行为，等同全部权限）。

## 启动

### 仅主站

```bash
python server.py
```

默认端口 `8000`（`PORT`）。调试：`DEBUG=1`。

### 主站 + QuickVote + TeacherDataSystem

子系统默认在仓库根目录 `QuickVote/`、`TeacherDataSystem/`；也可用 `QUICKVOTE_ROOT` / `TEACHERDATA_ROOT` 指向其它路径。依赖需单独安装，见 [vendor/README.md](vendor/README.md)。

```bash
# Linux / macOS
START_STACK=1 python server.py
```

```bat
rem Windows
set START_STACK=1
python server.py
```

也可直接运行 [start_stack.bat](start_stack.bat)（已设置 `START_STACK=1`）。

默认端口：主站 `8000`（`PORT`），QuickVote `8001`（`QUICKVOTE_PORT`），TeacherDataSystem `8002`（`TEACHERDATA_PORT`）。生产环境请用进程管理 / 反向代理，勿依赖多进程子 shell 的调试模式。

## 常用入口（默认端口）

- 管理中心：`http://127.0.0.1:8000/index.html`
- 教师申请：`http://127.0.0.1:8000/teacher.html`

## 审批与导出流程

1. 教师进入「教师申请」，用一句话提交车牌、周期请假、网络密码重置，或在「校章申请」上传 PDF 并选择盖章点。
2. 申请统一进入审批队列，默认状态为「待审核」。管理员在「管理中心」选择对应审批队列，查看详情后通过或驳回。
3. 管理员通过后系统会调用对应外部接口并记录执行结果；校章申请会自动生成盖章后 PDF。
4. 教师在「我的申请与办结结果」查看进度。已通过或已驳回的申请可下载办结回执；校章申请通过后可额外下载盖章 PDF。
5. 管理端列表和详情页也提供回执导出，便于归档。

> 如需保留旧的「周期请假提交后立即自动通过」行为，可在 `.env` 设置 `QUEUE_AUTO_APPROVE_LEAVE=1`。默认建议保持人工审批。

子系统对外的跳转地址在 `.env` 中设置 `QUICKVOTE_PUBLIC_URL`、`TEACHERDATA_PUBLIC_URL`。管理中心内可使用 `/go/quickvote`、`/go/teacher-data-system` 等入口。

## 更多文档

- [vendor/README.md](vendor/README.md) — 子系统安装与说明
- [docs/DINGTALK-H5.md](docs/DINGTALK-H5.md) — 钉钉 H5
- [docs/SECURITY-NOTES.md](docs/SECURITY-NOTES.md) — 配置与安全提示
