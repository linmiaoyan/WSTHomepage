# WSTHompage

学校门户与**管理中心**（Flask）：钉钉登录、教师申请与审批队列、周期请假/车牌/校章等 API；静态页在 `public/`。

## 项目结构

| 路径 | 说明 |
| --- | --- |
| `server.py` | 唯一入口：开发服务器；可选一键拉起子系统（见下） |
| `public/` | 主站前端静态资源（`index.html`、`teacher.html` 等） |
| `keadmin_queue.db` | 审批队列（SQLite，本地文件） |
| `vendor/` | 原版 [QuickVote](vendor/README.md#原版子系统quickvote--teacherdatasystem) 与 [TeacherDataSystem](vendor/README.md#原版子系统quickvote--teacherdatasystem) 源码 |
| `docs/` | 钉钉与安全等补充说明 |

## 环境

- 在根目录按各功能需要配置 `.env`；可从 [`.env.example`](.env.example) 复制后修改。密钥与本地 `.db` 勿提交（见 `.gitignore`）。
- 大模型等密钥变量名以 `server.py` 中 `_env_get` 为准。

### 多管理组与口令（可选）

- 在 `.env` 设置 **`ADMIN_MASTER_CODE`**（主管理员口令）后，启用多管理组模式：各组口令与权限保存在 `keadmin_queue.db` 的 `admin_groups` 表；主管理员在「管理中心 → 管理组与口令」中配置。
- 未设置 `ADMIN_MASTER_CODE` 时，仍可使用单一 **`ADMIN_GATE_CODE`**（旧行为，等同全部权限）。

## 启动

### 开发模式

未设置 `PRODUCTION=1` 时保持开发友好行为：默认监听 `0.0.0.0`，可设置 `DEBUG=1` 开启调试。

### 仅主站

```bash
python server.py
```

默认端口 `8000`（`PORT`）。

### 主站 + QuickVote + TeacherDataSystem

子系统需在 `vendor/` 下或经 `QUICKVOTE_ROOT` / `TEACHERDATA_ROOT` 指到有效目录。依赖需单独安装，见 [vendor/README.md](vendor/README.md)。

```bash
# Linux / macOS
START_STACK=1 python server.py
# 或：
python run_stack.py
```

```bat
rem Windows
set START_STACK=1
python server.py
```

也可直接运行 [start_stack.bat](start_stack.bat)（已设置 `START_STACK=1`）。

默认端口：主站 `8000`（`PORT`），QuickVote `8001`（`QUICKVOTE_PORT`），TeacherDataSystem `8002`（`TEACHERDATA_PORT`）。

## 生产部署建议

公网部署建议使用 `PRODUCTION=1`：

- 主站与 START_STACK 子服务默认监听 `127.0.0.1`，避免 8000/8001/8002 直接暴露公网。
- Flask 主站与 QuickVote 使用 `waitress`，不再使用开发服务器；`DEBUG` 会被强制关闭。
- `werkzeug` / `uvicorn` 的畸形请求日志会降噪，减少扫描器产生的 Oracle TNS、MSSQL、TLS 握手等二进制垃圾日志。
- `SINGLE_PORT=1` 时，公网只需要 nginx 反代到 `127.0.0.1:8000`，QuickVote 和 TeacherDataSystem 通过 `/quickvote/`、`/teacher-data/` 子路径访问。

最小生产 `.env` 示例：

```env
PRODUCTION=1
START_STACK=1
SINGLE_PORT=1
HOST=127.0.0.1
PORT=8000
QUICKVOTE_HOST=127.0.0.1
QUICKVOTE_PORT=8001
TEACHERDATA_HOST=127.0.0.1
TEACHERDATA_PORT=8002
DEBUG=0
```

nginx 示例见 [docs/nginx-wsthomepage.conf](docs/nginx-wsthomepage.conf)。公网安全组 / Windows 防火墙应关闭 `8000-8002` 入站，仅开放 `80/443` 给 nginx；如需临时远程排查，请使用 SSH/RDP 隧道或仅对白名单 IP 临时开放。

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
