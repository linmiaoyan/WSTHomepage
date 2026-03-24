/**
 * 添加职工车牌 - 从部门/人员选择器选人，提交到后台 Flask 代理
 * 所有真实外部接口地址和 token 均在后端配置，这里只调用本地 /api。
 */
const API_VEHICLE = "/api/add-vehicle";
const API_DEPT = "/api/deptAuthChild";
const API_PLATFORM_LOGIN = "/api/platform-login";
const API_VEHICLE_NLP = "/api/vehicle-nlp";
const API_SCHOOLISOVER_TOKEN = "/api/schoolisover-token";
const API_CONTACTS_SEARCH = "/api/contacts-search";
const VEHICLE_PREFILL_STORAGE_KEY = "ke_vehicle_prefill_v1";
let activePrefill = null;

/**
 * 从审批页写入的 sessionStorage + URL 查询参数合并读取预填数据（URL 优先覆盖同名键）。
 */
function readVehiclePrefill() {
    let fromSession = null;
    try {
        const raw = sessionStorage.getItem(VEHICLE_PREFILL_STORAGE_KEY);
        if (raw) fromSession = JSON.parse(raw);
    } catch (e) {
        fromSession = null;
    }
    const merged = {};
    if (fromSession && typeof fromSession === "object") {
        Object.assign(merged, fromSession);
    }
    try {
        const usp = new URLSearchParams(window.location.search || "");
        ["plate_no", "plate_type", "remark", "name", "start_date", "end_date", "from_request", "team_uid"].forEach((k) => {
            const v = usp.get(k);
            if (v !== null && v !== "") merged[k] = v;
        });
    } catch (e) {}
    const has =
        (merged.plate_no && String(merged.plate_no).trim()) ||
        (merged.name && String(merged.name).trim()) ||
        (merged.remark && String(merged.remark).trim()) ||
        (merged.from_request && String(merged.from_request).trim()) ||
        (merged.team_uid && String(merged.team_uid).trim());
    if (!has) return null;
    return merged;
}

function applyVehiclePrefill(pre) {
    if (!pre || typeof pre !== "object") return;
    const plateNoEl = document.getElementById("plateNo");
    const plateTypeEl = document.getElementById("plateType");
    const remarkEl = document.getElementById("remark");
    const startDateEl = document.getElementById("startDate");
    const endDateEl = document.getElementById("endDate");
    const teamUidEl = document.getElementById("teamUid");
    const summary = document.getElementById("selectedSummary");
    const banner = document.getElementById("prefillBanner");
    const llmInput = document.getElementById("llmVehicleInput");

    const plate = String(pre.plate_no || "").trim();
    const plateType = String(pre.plate_type != null ? pre.plate_type : "0").trim();
    const remark = String(pre.remark || "").trim();
    const startDate = String(pre.start_date || "").trim();
    const endDate = String(pre.end_date || "").trim();
    const name = String(pre.name || "").trim();
    const teamUid = String(pre.team_uid || "").trim();
    const fromReq = String(pre.from_request || "").trim();

    if (plateNoEl && plate) plateNoEl.value = plate;
    if (plateTypeEl && (plateType === "0" || plateType === "1")) plateTypeEl.value = plateType;
    if (remarkEl && remark) remarkEl.value = remark;
    if (startDateEl && startDate) startDateEl.value = startDate;
    if (endDateEl && endDate) endDateEl.value = endDate;
    if (teamUidEl && teamUid) {
        teamUidEl.value = teamUid;
        if (summary) summary.innerHTML = "已预填职工 ID：<strong>" + teamUid + "</strong>（请确认或重新选择）";
    }
    if (llmInput && (name || plate)) {
        const bits = [];
        if (name) bits.push(name);
        if (plate) bits.push(plate);
        if (bits.length && !llmInput.value.trim()) llmInput.value = bits.join(" ") + " 车牌";
    }
    if (banner) {
        let msg = "已从审批申请预填车牌信息，请在本页选择职工后提交。";
        if (fromReq) msg = "已带入审批单 <strong>#" + fromReq + "</strong> 中的车牌等信息；请选择职工（可点「全局搜索」）后提交。";
        banner.innerHTML = msg;
        banner.style.display = "block";
    }
}

function setStatus(text, type) {
    const el = document.getElementById("statusMsg");
    if (!el) return;
    el.textContent = text || "";
    el.className = type ? type : "";
}

function setPlatStatus(text, ok) {
    const el = document.getElementById("platStatus");
    if (!el) return;
    el.textContent = text || "";
    el.style.color = ok ? "var(--success-color)" : "var(--danger-color)";
}

function setVehicleLlmOut(text, isErr) {
    const el = document.getElementById("llmVehicleOut");
    if (!el) return;
    el.textContent = text || "";
    el.style.color = isErr ? "var(--danger-color)" : "var(--text-secondary)";
}

function setGlobalSearchOut(text, isErr) {
    const el = document.getElementById("globalSearchOut");
    if (!el) return;
    el.textContent = text || "";
    el.style.color = isErr ? "var(--danger-color)" : "var(--text-secondary)";
}

function toggleTempDateVisibility() {
    const plateType = (document.getElementById("plateType") || {}).value;
    const row = document.getElementById("tempDateRow");
    const requiredSpan = document.getElementById("teamUidRequired");
    const hintEl = document.getElementById("teamUidHint");
    const isTemp = plateType === "1";
    if (row) row.style.display = isTemp ? "block" : "none";
    if (requiredSpan) requiredSpan.style.display = isTemp ? "none" : "inline";
    if (hintEl) hintEl.textContent = isTemp ? "临时车牌可不填职工；请填写下方授权日期" : "长期车牌必选职工；临时车牌可不填";
}

function renderGlobalUsers(users, keyword) {
    const deptEl = document.getElementById("deptList");
    const userEl = document.getElementById("userList");
    const bc = document.getElementById("breadcrumb");
    if (deptEl) deptEl.innerHTML = "";
    if (bc) bc.textContent = "全局搜索";
    if (!userEl) return;

    const rows = Array.isArray(users) ? users : [];
    userEl.innerHTML = "";
    if (rows.length === 0) {
        userEl.innerHTML = '<span class="loading">未找到匹配人员</span>';
        return;
    }
    rows.forEach(u => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "user-item";
        const name = u.name || ("ID " + u.id);
        const path = u.path ? ("（" + u.path + "）") : "";
        btn.textContent = name + path;
        btn.onclick = () => selectUser({ id: u.id, name: u.name || name });
        userEl.appendChild(btn);
    });
}

async function globalContactsSearch() {
    const keyword = (document.getElementById("nameSearch") || {}).value || "";
    const q = keyword.trim();
    if (!q) {
        setGlobalSearchOut("请输入姓名关键字。", true);
        return;
    }
    const btn = document.getElementById("globalSearchBtn");
    if (btn) btn.disabled = true;
    setGlobalSearchOut("搜索中…", false);
    try {
        const resp = await fetch(API_CONTACTS_SEARCH, {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ q: q, limit: 30 })
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok || !data.ok) {
            setGlobalSearchOut("失败：" + (data.msg || resp.status), true);
            if (data.need_platform_login) {
                setGlobalSearchOut("需要平台登录：请先登录后再搜索。", true);
            }
            return;
        }
        const users = data.users || [];
        setGlobalSearchOut(`找到 ${users.length} 人`, false);
        renderGlobalUsers(users, q);
    } catch (e) {
        setGlobalSearchOut("请求失败：" + e.message, true);
    } finally {
        if (btn) btn.disabled = false;
    }
}

function tryAutoSelectByName(name) {
    if (!name) return;
    const search = document.getElementById("nameSearch");
    if (search) {
        search.value = name;
        try { search.dispatchEvent(new Event("input")); } catch (e) {}
    }
    // If only one visible user item, click it
    try {
        const users = Array.from(document.querySelectorAll("#userList .user-item")).filter(b => (b.offsetParent !== null));
        if (users.length === 1) users[0].click();
    } catch (e) {}
}

async function vehicleLlmParse() {
    const btn = document.getElementById("llmVehicleBtn");
    const input = (document.getElementById("llmVehicleInput") || {}).value || "";
    if (!input.trim()) return setVehicleLlmOut("请输入一句话描述。", true);
    btn.disabled = true;
    setVehicleLlmOut("解析中…", false);
    try {
        const resp = await fetch(API_VEHICLE_NLP, {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ text: input }),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok || !data.ok) {
            setVehicleLlmOut("失败：" + (data.msg || resp.status), true);
            return;
        }
        const p = data.data || {};
        const name = String(p.name || "").trim();
        const plate = String(p.plate_no || "").trim();
        const remark = String(p.remark || "").trim();
        const plateType = String(p.plate_type || "0").trim();
        const startDate = String(p.start_date || "").trim();
        const endDate = String(p.end_date || "").trim();

        if (plate) {
            const plateNoEl = document.getElementById("plateNo");
            if (plateNoEl) plateNoEl.value = plate;
        }
        if (remark) {
            const remarkEl = document.getElementById("remark");
            if (remarkEl && !remarkEl.value.trim()) remarkEl.value = remark;
        }
        const plateTypeEl = document.getElementById("plateType");
        if (plateTypeEl && (plateType === "0" || plateType === "1")) {
            plateTypeEl.value = plateType;
            toggleTempDateVisibility();
        }
        const startDateEl = document.getElementById("startDate");
        const endDateEl = document.getElementById("endDate");
        if (startDateEl && startDate) startDateEl.value = startDate;
        if (endDateEl && endDate) endDateEl.value = endDate;
        if (name) {
            tryAutoSelectByName(name);
        }

        const lines = [];
        if (name) lines.push("姓名：" + name);
        if (plate) lines.push("车牌：" + plate);
        if (plateType === "1") lines.push("临时");
        if (startDate && endDate) lines.push(startDate + "～" + endDate);
        if (p.notes) lines.push("提示：" + p.notes);
        setVehicleLlmOut(lines.join("  ") || "已解析并填充。", false);
    } catch (e) {
        setVehicleLlmOut("请求失败：" + e.message, true);
    } finally {
        btn.disabled = false;
    }
}

async function platformLogin() {
    const btn = document.getElementById("platLoginBtn");
    const usr = (document.getElementById("platUsr") || {}).value.trim();
    const pwd = (document.getElementById("platPwd") || {}).value;
    const ver = (document.getElementById("platVercode") || {}).value.trim();
    btn.disabled = true;
    setPlatStatus("登录中…", true);
    try {
        const resp = await fetch(API_PLATFORM_LOGIN, {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ usrname: usr, passwd: pwd, vercode: ver }),
        });
        const data = await resp.json().catch(() => ({}));
        if (resp.ok && data.ok) {
            setPlatStatus("登录成功（可开始添加车牌）", true);
        } else if (data.need_captcha) {
            setPlatStatus("需要验证码：请看平台登录页验证码后填写再试", false);
        } else {
            setPlatStatus("登录失败：" + (data.msg || resp.status), false);
        }
    } catch (e) {
        setPlatStatus("请求失败：" + e.message, false);
    } finally {
        btn.disabled = false;
    }
}

async function platformLoginAuto() {
    // Auto-login using backend defaults in .env when usr/pass are empty.
    const ver = (document.getElementById("platVercode") || {}).value.trim();
    setPlatStatus("检测到未登录，自动登录中…", true);
    const resp = await fetch(API_PLATFORM_LOGIN, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ usrname: "", passwd: "", vercode: ver }),
    });
    const data = await resp.json().catch(() => ({}));
    if (resp.ok && data.ok) {
        setPlatStatus("自动登录成功，继续提交…", true);
        return { ok: true };
    }
    if (data.need_captcha) {
        setPlatStatus("自动登录需要验证码：请填写验证码后再点提交/登录", false);
        return { ok: false, need_captcha: true, msg: data.msg || "需要验证码" };
    }
    setPlatStatus("自动登录失败：" + (data.msg || resp.status), false);
    return { ok: false, msg: data.msg || ("HTTP " + resp.status) };
}

// ---------- 部门/人员选择器 ----------
let currentDeptId = 1;
let currentPath = [];
let currentDeptList = [];
let currentUserList = [];
let selectedUser = null;

async function loadDeptChildren(id) {
    const resp = await fetch(API_DEPT, {
        method: "POST",
        headers: {
            "content-type": "application/json"
        },
        body: JSON.stringify({ id: String(id) })
    });
    const data = await resp.json().catch(() => ({}));
    const debugText = data && data._debug ? (data._debug.cloud_text_head || data._debug._raw_text_head || '') : '';
    if (resp.status === 403 && data && data.msg === "need_platform_login") {
        const hint = data.hint || "请先完成平台管理员登录";
        throw new Error(debugText ? (hint + "\n" + "云端返回：" + debugText) : hint);
    }
    if (data.code !== 200 || !data.data) {
        const msg = (data && data.msg) || "加载失败";
        throw new Error(debugText ? (msg + "\n" + "云端返回：" + debugText) : msg);
    }
    return data.data;
}

function renderBreadcrumb() {
    const el = document.getElementById("breadcrumb");
    if (!el) return;
    const parts = ["通讯录", ...(currentPath.map(p => p.name))];
    el.textContent = parts.join(" > ");
}

function applyNameFilter(list, query) {
    const q = (query || "").trim().toLowerCase();
    if (!q) return list;
    return list.filter(u => (u.name || "").toLowerCase().includes(q));
}

function renderDeptAndUserList() {
    const deptEl = document.getElementById("deptList");
    const userEl = document.getElementById("userList");
    const searchQuery = (document.getElementById("nameSearch") || {}).value || "";
    if (!deptEl || !userEl) return;

    const filteredUsers = applyNameFilter(currentUserList, searchQuery);

    deptEl.innerHTML = "";
    currentDeptList.forEach(d => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "dept-item";
        btn.textContent = d.name || ("部门 " + d.id);
        btn.onclick = () => openDept(d.id, d.name);
        deptEl.appendChild(btn);
    });

    userEl.innerHTML = "";
    if (filteredUsers.length === 0 && currentUserList.length > 0) {
        userEl.innerHTML = '<span class="loading">无匹配人员</span>';
    } else if (filteredUsers.length === 0) {
        userEl.innerHTML = '<span class="loading">该层级暂无人员，请进入子部门</span>';
    } else {
        filteredUsers.forEach(u => {
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "user-item" + (selectedUser && selectedUser.id === u.id ? " selected" : "");
            btn.textContent = u.name || ("ID " + u.id);
            btn.onclick = () => selectUser(u);
            userEl.appendChild(btn);
        });
    }
}

async function openDept(id, name) {
    const deptEl = document.getElementById("deptList");
    const userEl = document.getElementById("userList");
    if (deptEl) deptEl.innerHTML = '<span class="loading">加载中…</span>';
    if (userEl) userEl.innerHTML = "";
    try {
        const data = await loadDeptChildren(id);
        currentDeptId = id;
        currentPath = data.path || [];
        currentDeptList = data.deptlist || [];
        currentUserList = data.userlist || [];
        renderBreadcrumb();
        renderDeptAndUserList();
    } catch (e) {
        if (deptEl) deptEl.innerHTML = "";
        if (userEl) userEl.innerHTML = '<span class="loading" style="color:var(--danger-color)">' + e.message + "</span>";
    }
}

function selectUser(user) {
    selectedUser = user;
    const teamUid = document.getElementById("teamUid");
    const summary = document.getElementById("selectedSummary");
    if (teamUid) teamUid.value = String(user.id);
    if (summary) summary.innerHTML = '已选：<strong>' + (user.name || user.id) + '</strong>（ID: ' + user.id + '）';
    renderDeptAndUserList();
}

// 面包屑点击回根（在 DOMContentLoaded 里绑定）

// ---------- 提交表单 ----------
async function submitForm() {
    const btn = document.getElementById("submitBtn");
    const eduAuthTokenEl = document.getElementById("eduAuthToken");
    const teamUid = (document.getElementById("teamUid") || {}).value.trim();
    const plateNo = (document.getElementById("plateNo") || {}).value.trim();
    const plateType = (document.getElementById("plateType") || {}).value;
    const remark = (document.getElementById("remark") || {}).value.trim();
    const startDate = (document.getElementById("startDate") || {}).value.trim();
    const endDate = (document.getElementById("endDate") || {}).value.trim();
    const eduAuthToken = (eduAuthTokenEl ? eduAuthTokenEl.value : "").trim();

    if (!plateNo) {
        setStatus("请填写车牌号码", "err");
        return;
    }
    if (plateType !== "1" && !teamUid) {
        setStatus("长期车牌请先选择职工", "err");
        return;
    }
    if (plateType === "1") {
        if (!startDate || !endDate) {
            setStatus("临时车牌请填写授权开始、结束日期", "err");
            return;
        }
    }

    const body = {
        plate_no: plateNo,
        plate_type: plateType,
        remark: remark,
        edu_auth_token: eduAuthToken
    };
    if (teamUid) body.team_uid = teamUid;
    if (plateType === "1") {
        body.start_date = startDate;
        body.end_date = endDate;
    }

    btn.disabled = true;
    setStatus("提交中…", "");

    try {
        const doSubmit = async () => {
            const resp = await fetch(API_VEHICLE, {
                method: "POST",
                headers: { "content-type": "application/json" },
                body: JSON.stringify(body)
            });
            const data = await resp.json().catch(() => ({}));
            return { resp, data };
        };

        // first attempt
        let { resp, data } = await doSubmit();

        // If backend says need platform login, auto-login then retry once.
        const needPlatformLogin = resp.status === 403 && data && (data.data === "need_platform_login" || data.msg === "need_platform_login");
        if (needPlatformLogin) {
            const loginRes = await platformLoginAuto();
            if (loginRes.ok) {
                ({ resp, data } = await doSubmit());
            } else {
                setStatus("失败：" + (data.msg || "需要平台登录"), "err");
                return;
            }
        }

        const codeStr = (data && data.code !== undefined && data.code !== null) ? String(data.code) : "";
        const isOkCode = (codeStr === "" || codeStr === "200" || codeStr === "1");
        if (resp.ok && isOkCode) {
            // 若来自审批单预填，提交成功后将 team_uid 等参数回写到该审批单，避免审批执行时缺参
            let extra = "";
            const rid = activePrefill && String(activePrefill.from_request || "").trim();
            if (rid) {
                try {
                    const patchResp = await fetch("/api/admin/requests/" + encodeURIComponent(rid) + "/patch-add-vehicle", {
                        method: "POST",
                        headers: { "content-type": "application/json" },
                        credentials: "same-origin",
                        body: JSON.stringify({
                            team_uid: teamUid,
                            plate_no: plateNo,
                            plate_type: plateType,
                            remark: remark,
                            start_date: startDate,
                            end_date: endDate,
                            reset_to_pending: true
                        })
                    });
                    const patchData = await patchResp.json().catch(() => ({}));
                    if (patchResp.ok && patchData && patchData.ok) {
                        extra = "；并已同步回审批单#" + rid + "（重置为待审核）";
                    } else {
                        extra = "；但回写审批单失败，请回审核页重试（" + (patchData.msg || patchResp.status) + "）";
                    }
                } catch (e) {
                    extra = "；但回写审批单失败：" + e.message;
                }
            }
            setStatus("成功：" + (data.msg || "已添加车牌") + extra, "ok");
        } else {
            const debugText = data && data._debug ? (data._debug.cloud_text_head || data._debug._raw_text_head || '') : '';
            const baseMsg = data.msg || (resp.status + " " + resp.statusText);
            setStatus("失败：" + baseMsg + (debugText ? ("\n云端返回：" + debugText) : ""), "err");
        }
    } catch (e) {
        setStatus("请求失败：" + e.message, "err");
    } finally {
        btn.disabled = false;
    }
}

document.addEventListener("DOMContentLoaded", async function () {
    document.getElementById("submitBtn").addEventListener("click", submitForm);
    const platBtn = document.getElementById("platLoginBtn");
    if (platBtn) platBtn.addEventListener("click", platformLogin);
    const llmBtn = document.getElementById("llmVehicleBtn");
    if (llmBtn) llmBtn.addEventListener("click", vehicleLlmParse);
    const plateTypeEl = document.getElementById("plateType");
    if (plateTypeEl) plateTypeEl.addEventListener("change", toggleTempDateVisibility);
    const br = document.getElementById("breadcrumb");
    if (br) br.addEventListener("click", function () { openDept(1, "根"); });
    const nameSearch = document.getElementById("nameSearch");
    if (nameSearch) {
        nameSearch.addEventListener("input", renderDeptAndUserList);
        nameSearch.addEventListener("keyup", renderDeptAndUserList);
    }
    const gbtn = document.getElementById("globalSearchBtn");
    if (gbtn) gbtn.addEventListener("click", globalContactsSearch);
    toggleTempDateVisibility();

    const pre = readVehiclePrefill();
    activePrefill = pre;
    if (pre) {
        applyVehiclePrefill(pre);
        try {
            sessionStorage.removeItem(VEHICLE_PREFILL_STORAGE_KEY);
        } catch (e) {}
    }
    toggleTempDateVisibility();

    await openDept(1, "根");

    // 长期车牌：带入姓名后自动全局搜索，便于直接选职工填 team_uid
    if (pre && String(pre.plate_type || "0") !== "1" && (pre.name || "").trim() && !(pre.team_uid || "").trim()) {
        const ns = document.getElementById("nameSearch");
        if (ns) {
            ns.value = String(pre.name).trim();
            renderDeptAndUserList();
        }
        await globalContactsSearch();
    }

    const fetchTokenBtn = document.getElementById("fetchTokenBtn");
    if (fetchTokenBtn) {
        fetchTokenBtn.addEventListener("click", async function () {
            this.disabled = true;
            this.textContent = "获取中…";
            try {
                const r = await fetch(API_SCHOOLISOVER_TOKEN);
                const d = await r.json().catch(() => ({}));
                const el = document.getElementById("eduAuthToken");
                if (r.ok && d.ok && d.token && el) {
                    el.value = d.token;
                    setPlatStatus("已填入云平台 Token，可再试提交", true);
                } else {
                    setPlatStatus(d.msg || "获取失败，请先完成平台管理员登录", false);
                }
            } catch (e) {
                setPlatStatus("请求失败：" + e.message, false);
            } finally {
                fetchTokenBtn.disabled = false;
                fetchTokenBtn.innerHTML = '<i class="bi bi-arrow-repeat"></i> 获取当前 Token';
            }
        });
    }

    // persist optional token locally
    try {
        const key = "keadminEduAuthToken";
        const el = document.getElementById("eduAuthToken");
        if (el) {
            const old = localStorage.getItem(key);
            if (old && !el.value) el.value = old;
            el.addEventListener("input", () => localStorage.setItem(key, el.value));
        }
    } catch (e) {}
});
