# 钉钉：H5 微应用 vs 浏览器扫码登录

## 从钉钉「工作台」打开本站时

工作台是在 **钉钉 App 内置浏览器** 里打开 H5，应使用 **JSAPI 免登**（`requestAuthCode` → 后端 `/api/dingtalk/h5-auth`），**不要**点「扫码登录」去走 `login.dingtalk.com/oauth2`（微应用的 ClientId 常会报 **应用不存在**）。

**必配**：`.env` 中 `DINGTALK_USE_H5_JSAPI=1`，并填写企业 `DINGTALK_CORP_ID`，与当前 H5 微应用同一套 `DINGTALK_CLIENT_ID` / `DINGTALK_CLIENT_SECRET`。改完后**重启** Flask 进程并刷新页面。

## 为什么 H5 微应用会提示「应用不存在」？

当前仓库里的 **「钉钉登录」** 链接走的是：

`https://login.dingtalk.com/oauth2/auth?...`

这是 **在外部浏览器里扫码 / 跳转** 的 **「登录第三方网站」** 流程，对应开放平台里另一类应用能力。

你在钉钉后台创建的是 **「H5 微应用」** 时，拿到的 **Client ID / Secret** 主要给：

- 在 **钉钉客户端内** 打开的页面使用 **JSAPI**（如 `dd.runtime.permission.requestAuthCode`）获取临时 `authCode`
- 再由 **你自己的服务端** 用同一套 Client ID / Secret 去换用户票据

**这两套入口在钉钉侧登记方式不同**。把「仅作为 H5 微应用」的 Client ID 填到浏览器 OAuth 里，就容易出现 **`应用不存在`** —— 不是代码写错，而是 **应用场景不匹配**。

## 你可以怎么做？

### 方案 A：继续用浏览器扫码（适合微信/系统浏览器打开 `wzkjgz.site`）

在 [钉钉开放平台](https://open-dev.dingtalk.com/) **另外创建一个** 支持 **「网页方式登录第三方网站 / OAuth2 登录网站」** 的应用，把它的 Client ID / Secret 配到 `.env` 的 `DINGTALK_CLIENT_ID` / `DINGTALK_CLIENT_SECRET`，并配置回调 `DINGTALK_REDIRECT_URI`。

H5 微应用可以保留给工作台里打开使用（方案 B）。

### 方案 B：在钉钉里打开本站时用 H5 免登（本仓库已接好接口）

1. 在 `.env` 中配置（与 H5 微应用同一套凭证即可）：
   - `DINGTALK_CLIENT_ID` / `DINGTALK_CLIENT_SECRET`（已有）
   - `DINGTALK_CORP_ID`：企业 **CorpId**（钉钉管理后台 / 开放平台可见）
   - `DINGTALK_USE_H5_JSAPI=1`：开启前端「钉钉内登录」按钮逻辑

2. 把微应用 **首页 URL** 配成你的站点（如 `https://wzkjgz.site/teacher.html`），在 **钉钉客户端内** 打开。

3. 页面上会多出 **「钉钉内登录」**：调用 JSAPI 取 `authCode`，请求后端 `POST /api/dingtalk/h5-auth` 写入会话（与扫码登录后的 `session` 一致）。

若换票失败，请对照开放平台文档核对：应用是否已开通通讯录相关权限（如获取个人信息），以及 Client ID 是否与当前 H5 应用一致。

## 小结

| 场景 | 推荐方式 |
|------|----------|
| 手机系统浏览器 / 微信 打开网站 | 方案 A：单独「第三方网站登录」应用 + `/auth/dingtalk/login` |
| 钉钉 App 内打开微应用首页 | 方案 B：`DINGTALK_USE_H5_JSAPI=1` + `DINGTALK_CORP_ID` + 「钉钉内登录」 |

两者可以 **同时存在**：浏览器用户扫码，钉钉内用户一键登录。
