# Security notes (KeApprove)

## Git

- `.env` is listed in `.gitignore` — **do not** `git add -f .env`.
- 新环境：从已部署机器复制一份 `.env` 再改（仓库内不提供示例文件，避免与真实配置混淆）。

## 钉钉：H5 微应用

若开放平台里创建的是 **H5 微应用**，其 Client ID **不能**直接用于外部浏览器跳转 `login.dingtalk.com/oauth2/auth`（会提示「应用不存在」）。说明与两种并存方案见 **`DINGTALK-H5.md`**。

## Audited hardcoded values (removed or moved)

| Item | Location (before) | Action |
|------|-------------------|--------|
| Campus API token | `server.py` `CAMPUS_TOKEN` | Use `CAMPUS_TOKEN` in `.env` |
| Leave platform user/password | `server.py` `LEAVE_USER` / `LEAVE_PASS` | Use `LEAVE_USER` / `LEAVE_PASS` in `.env` |
| Leave / campus base URLs | `server.py` | Use `LEAVE_BASE` / `CAMPUS_BASE` in `.env` |
| Eduyun `eduyun.php` path | `server.py` | Use `EDU_CFG_PHP` in `.env` |
| QuickForm path for LLM token | `server.py` | Optional `QUICKFORM_ENV_PATH` in `.env` |
| Admin page passphrase | `index.html` `ACCESS_CODE` | Use `ADMIN_GATE_CODE` in `.env` + `/api/admin-gate-check` |
| 校园网管代理 SSRF | `/api/search-users`、`/api/reset-net-password` 曾接受任意 `baseUrl` | 默认仅用 `.env`；仅当 `CAMPUS_ALLOW_CLIENT_OVERRIDE=1` 时才接受请求体覆盖；上述接口需通过 `_admin_api_authorized()`（与管理中心口令一致） |
| Flask `debug=True` | `server.py` 直接运行时 | 默认关闭；需要时在 `.env` 设 `DEBUG=1` |
| TeacherDataSystem 默认管理员口令 | `config.py` | 必须设置环境变量 `ADMIN_PASSWORD`（可与主站 `.env` 同源，由 `START_STACK=1 python server.py` 子进程继承） |

## If you already committed secrets

1. Rotate passwords/tokens on the real systems.
2. Remove secrets from Git history (`git filter-repo` / BFG) or treat the repo as compromised.
