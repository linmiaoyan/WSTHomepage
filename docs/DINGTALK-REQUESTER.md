# 钉钉登录后能拿到哪些信息？（写入审批队列给管理员看）

教师/提交人在 **钉钉登录成功** 后，后端会调用开放平台接口 **`GET /v1.0/contact/users/me`**，把返回里**允许读取的字段**规范化后写入会话；**每次入队**时再附加 **提交时间、IP、浏览器 UA**，一并存入 `requester_json`，管理员在「管理员审核」详情里可见。

## 常见字段（是否出现取决于权限与 scope）

| 字段 | 说明 |
|------|------|
| `userId` | 企业内用户 ID，可追溯 |
| `unionId` | 跨应用稳定标识（若有） |
| `openId` | 应用内 openId（若有） |
| `name` / `nick` | 姓名、昵称 |
| `mobile` / `telephone` | 手机号（需敏感权限） |
| `email` / `orgEmail` | 邮箱 |
| `title` | 职位 |
| `jobNumber` | 工号 |
| `deptIdList` | 部门 ID 列表（若有） |
| `avatarUrl` | 头像 URL |
| `corpId` | 企业 corpId |
| `login_via` | `browser_oauth`（扫码）或 `h5_jsapi`（钉钉内） |
| `login_at` | 本次钉钉登录时间 |
| `display_name` / `summary` | 便于列表展示的摘要 |
| **入队时追加** | |
| `submitted_at` | 点击提交/入队的时间 |
| `client_ip` | 客户端 IP（若经反向代理，依赖 `X-Forwarded-For`） |
| `user_agent` | 浏览器 UA 摘要 |

## 如何尽量拿到手机号、邮箱等？

1. 在钉钉开放平台为该应用申请 **通讯录 / 个人信息** 等相关权限（如 `Contact.User.Read` 等，以控制台为准）。  
2. 浏览器扫码场景下，可在 `.env` 增加（空格分隔多个 scope，勿加引号）：

   `DINGTALK_OAUTH_SCOPE=openid Contact.User.Read`

   保存后重启服务，让用户**重新走一遍钉钉授权**（同意新权限）。

> 若只保留 `openid`，接口可能只返回较少字段，列表里会主要看到 `userId` / `unionId` 等。

## 管理员在哪里看？

**管理中心 → 管理员审核 → 查看**：弹窗顶部有 **「发起人（钉钉 + 提交环境）」** 表格；下方完整 JSON 里 `requester` 对象与数据库 `requester_json` 一致。
