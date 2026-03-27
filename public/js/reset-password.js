/**
 * 重置网络密码 - 调用本地 Flask 代理：
 *   POST /api/search-users
 *   POST /api/reset-net-password
 * 真实网管地址和 CSRF 均在后端配置。
 */

function setStatus(text, type) {
    const el = document.getElementById("statusMsg");
    if (!el) return;
    el.textContent = text || "";
    el.className = type ? type : "";
}

function getCampusConfigPayload() {
    const baseUrl = ((document.getElementById("baseUrl") || {}).value || "").trim();
    const csrfToken = ((document.getElementById("csrfToken") || {}).value || "").trim();
    return {
        baseUrl: baseUrl,
        csrfToken: csrfToken,
    };
}

// 搜索用户：POST /controller/campus/v1/usermgr/users
async function searchUsers() {
    const userGroupId = (document.getElementById("userGroupId") || {}).value.trim();
    const userName = (document.getElementById("searchUserName") || {}).value.trim();
    const listEl = document.getElementById("userListResult");
    const btn = document.getElementById("searchUserBtn");

    if (!userName) {
        setStatus("请填写要搜索的用户名", "err");
        return;
    }

    btn.disabled = true;
    listEl.innerHTML = "<span class=\"text-muted small\">搜索中…</span>";
    setStatus("", "");

    const body = {
        ...getCampusConfigPayload(),
        userGroupId: userGroupId || undefined,
        quickQuery: false,
        queryAll: false,
        pageIndex: 1,
        pageSize: 20,
        userName: userName,
        flag: false
    };

    try {
        const resp = await fetch("/api/search-users", {
            method: "POST",
            headers: {
                "content-type": "application/json"
            },
            body: JSON.stringify(body),
        });
        const data = await resp.json().catch(() => ({}));

        if (!resp.ok) {
            listEl.innerHTML = "";
            setStatus("搜索失败：" + (data.message || data.msg || resp.status), "err");
            return;
        }

        const list = data.data?.list ?? data.list ?? data ?? [];
        const arr = Array.isArray(list) ? list : [];
        listEl.innerHTML = "";
        if (arr.length === 0) {
            listEl.innerHTML = "<span class=\"text-muted small\">未找到用户</span>";
        } else {
            arr.forEach(function (u) {
                const id = u.id || u.userId || u.uuid;
                const name = u.userName || u.name || id;
                if (!id) return;
                const btn = document.createElement("button");
                btn.type = "button";
                btn.className = "user-item";
                btn.textContent = name + " (" + id + ")";
                btn.onclick = function () {
                    document.getElementById("userId").value = id;
                    document.getElementById("userName").value = name;
                    setStatus("已选择：" + name, "ok");
                };
                listEl.appendChild(btn);
            });
        }
    } catch (e) {
        listEl.innerHTML = "";
        setStatus("请求失败：" + e.message, "err");
    } finally {
        btn.disabled = false;
    }
}

// 重置密码：PUT /controller/campus/v1/usermgr/userpwd/{userId}
async function resetPassword() {
    const userId = (document.getElementById("userId") || {}).value.trim();
    const userName = (document.getElementById("userName") || {}).value.trim();
    const password = (document.getElementById("newPassword") || {}).value;
    const passwordConfirm = (document.getElementById("passwordConfirm") || {}).value;
    const btn = document.getElementById("resetBtn");

    if (!userId) {
        setStatus("请填写用户 ID（或通过搜索选择用户）", "err");
        return;
    }
    if (!password) {
        setStatus("请填写新密码", "err");
        return;
    }
    if (password !== passwordConfirm) {
        setStatus("两次输入的密码不一致", "err");
        return;
    }

    btn.disabled = true;
    setStatus("提交中…", "");

    const body = {
        ...getCampusConfigPayload(),
        userName: userName || userId,
        userId: userId,
        password: password,
        passwordConfirm: passwordConfirm
    };

    try {
        const resp = await fetch("/api/reset-net-password", {
            method: "POST",
            headers: {
                "content-type": "application/json"
            },
            body: JSON.stringify(body),
        });
        const data = await resp.json().catch(function () { return {}; });

        if (resp.ok && (data.code === 0 || data.code === 200 || data.success === true || !data.code)) {
            setStatus("密码重置成功", "ok");
        } else {
            setStatus("失败：" + (data.message || data.msg || resp.status + " " + resp.statusText), "err");
        }
    } catch (e) {
        setStatus("请求失败：" + e.message, "err");
    } finally {
        btn.disabled = false;
    }
}

document.addEventListener("DOMContentLoaded", function () {
    document.getElementById("searchUserBtn").addEventListener("click", searchUsers);
    document.getElementById("resetBtn").addEventListener("click", resetPassword);
});
