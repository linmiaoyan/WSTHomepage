const API_LEAVE = "/api/leave-cycle";
const API_LEAVE_NLP = "/api/leave-nlp";

function setStatus(text, type) {
  const el = document.getElementById("statusMsg");
  if (!el) return;
  el.textContent = text || "";
  el.className = type ? type : "";
}

function getCycleReplace() {
  const nodes = document.querySelectorAll('input[name="cycleReplace"]');
  for (const n of nodes) {
    if (n.checked) return n.value;
  }
  return "0";
}

function localYMD(d) {
  const y = d.getFullYear();
  const m = d.getMonth() + 1;
  const day = d.getDate();
  return y + "-" + String(m).padStart(2, "0") + "-" + String(day).padStart(2, "0");
}

function addDaysLocal(d, n) {
  const x = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  x.setDate(x.getDate() + n);
  return x;
}

/** 默认周期：从「今天」起，便于覆盖周一到周五等多天（与后端 sanitize 的约 20 天一致） */
function guessDefaultCycleRange() {
  const now = new Date();
  now.setHours(0, 0, 0, 0);
  return { start: localYMD(now), end: localYMD(addDaysLocal(now, 20)) };
}

function guessWeekRange() {
  // 自然周 周一..周日（本地日期，避免 toISOString UTC 错位）
  const now = new Date();
  now.setHours(0, 0, 0, 0);
  const day = now.getDay();
  const mondayOffset = (day === 0 ? -6 : 1) - day;
  const monday = addDaysLocal(now, mondayOffset);
  const sunday = addDaysLocal(monday, 6);
  return { start: localYMD(monday), end: localYMD(sunday) };
}

function syncLcWeekHiddenFromChecks() {
  const parts = [];
  for (let i = 1; i <= 7; i++) {
    const c = document.getElementById("lc_w" + i);
    if (c && c.checked) parts.push(String(i));
  }
  const hid = document.getElementById("week");
  if (hid) hid.value = parts.length ? parts.join(",") : "3";
}

function applyLcWeekCsv(csv) {
  const set = {};
  String(csv || "")
    .split(/[,，]/)
    .forEach((x) => {
      const t = x.trim();
      if (/^\d+$/.test(t)) {
        const n = parseInt(t, 10);
        if (n >= 1 && n <= 7) set[String(n)] = true;
      }
    });
  for (let i = 1; i <= 7; i++) {
    const c = document.getElementById("lc_w" + i);
    if (c) c.checked = !!set[String(i)];
  }
  if (!Object.keys(set).length) {
    const w = document.getElementById("lc_w3");
    if (w) w.checked = true;
  }
  syncLcWeekHiddenFromChecks();
}

function setLlmOut(text, type) {
  const el = document.getElementById("llmOutput");
  if (!el) return;
  el.textContent = text || "";
  el.style.color = type === "err" ? "var(--danger-color)" : "var(--text-secondary)";
}

function normalizeStudents(arr) {
  if (!Array.isArray(arr)) return "";
  const cleaned = [];
  const seen = new Set();
  arr.forEach((x) => {
    const s = String(x || "").trim();
    if (!s) return;
    if (seen.has(s)) return;
    seen.add(s);
    cleaned.push(s);
  });
  return cleaned.join("\n");
}

function fillFromNlp(nlp) {
  if (!nlp || typeof nlp !== "object") return;
  if (nlp.students) {
    const ta = document.getElementById("students");
    if (ta) ta.value = normalizeStudents(nlp.students);
  }
  if (nlp.week != null && String(nlp.week).trim()) {
    applyLcWeekCsv(String(nlp.week).trim());
  } else if (nlp.weekday != null && String(nlp.weekday).trim()) {
    applyLcWeekCsv(String(nlp.weekday).trim());
  }
  const t = nlp.time || {};
  if (t.timestart) {
    const a = document.getElementById("timestart");
    if (a) a.value = t.timestart;
  }
  if (t.timeend) {
    const b = document.getElementById("timeend");
    if (b) b.value = t.timeend;
  }
  if (nlp.timestart) {
    const a = document.getElementById("timestart");
    if (a) a.value = String(nlp.timestart).trim();
  }
  if (nlp.timeend) {
    const b = document.getElementById("timeend");
    if (b) b.value = String(nlp.timeend).trim();
  }
  const ts = nlp.time_start || nlp.timeStart;
  const te = nlp.time_end || nlp.timeEnd;
  if (ts) {
    const el = document.getElementById("timeStart");
    if (el) el.value = String(ts).trim().slice(0, 10);
  }
  if (te) {
    const el = document.getElementById("timeEnd");
    if (el) el.value = String(te).trim().slice(0, 10);
  }
  if (typeof nlp.reason === "string" && nlp.reason.trim()) {
    const r = document.getElementById("reason");
    if (r) r.value = nlp.reason.trim();
  }
}

async function llmParse() {
  const btn = document.getElementById("llmParseBtn");
  const input = (document.getElementById("llmInput") || {}).value || "";
  if (!input.trim()) return setLlmOut("请输入要解析的口述内容。", "err");
  btn.disabled = true;
  setLlmOut("解析中…", "");
  try {
    const resp = await fetch(API_LEAVE_NLP, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ text: input }),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok || !data.ok) {
      setLlmOut("失败：" + (data.msg || resp.status), "err");
      return;
    }
    const parsed = data.data || {};
    fillFromNlp(parsed);
    const lines = [];
    if (parsed.students) lines.push("students: " + JSON.stringify(parsed.students, null, 0));
    if (parsed.week) lines.push("week: " + parsed.week);
    if (parsed.weekday != null) lines.push("weekday: " + parsed.weekday);
    if (parsed.time_start || parsed.time_end) {
      lines.push("周期: " + (parsed.time_start || "") + " ~ " + (parsed.time_end || ""));
    }
    if (parsed.lesson_hint) lines.push("lesson_hint: " + parsed.lesson_hint);
    if (parsed.time && (parsed.time.timestart || parsed.time.timeend)) {
      lines.push("time: " + (parsed.time.timestart || "") + " - " + (parsed.time.timeend || ""));
    }
    if (parsed.reason) lines.push("reason: " + parsed.reason);
    if (parsed.notes) lines.push("notes: " + parsed.notes);
    setLlmOut(lines.join("\n") || "已解析并回填。", "");
  } catch (e) {
    setLlmOut("请求失败：" + e.message, "err");
  } finally {
    btn.disabled = false;
  }
}

function llmFillWeek() {
  const r = guessWeekRange();
  const s = document.getElementById("timeStart");
  const e = document.getElementById("timeEnd");
  if (s) s.value = r.start;
  if (e) e.value = r.end;
  setLlmOut("已填入本自然周：" + r.start + " ~ " + r.end + "（与「周一到周五每天」建议用默认「今天起约20天」）", "");
}

async function submitLeave() {
  const btn = document.getElementById("submitBtn");
  const grade = String((document.getElementById("grade") || {}).value || "").trim();
  syncLcWeekHiddenFromChecks();
  const week = (document.getElementById("week").value || "3").trim();
  const timestart = (document.getElementById("timestart").value || "").trim();
  const timeend = (document.getElementById("timeend").value || "").trim();
  const timeStart = (document.getElementById("timeStart").value || "").trim();
  const timeEnd = (document.getElementById("timeEnd").value || "").trim();
  const reason = (document.getElementById("reason").value || "").trim();
  const students = (document.getElementById("students").value || "").trim();
  const vercode = (document.getElementById("vercode").value || "").trim();
  const cycleReplace = getCycleReplace();

  if (!students) return setStatus("请填写学生姓名（逗号或换行分隔）", "err");
  if (!timeStart || !timeEnd) return setStatus("请填写周期开始/结束日期（必须包含目标星期）", "err");
  if (!timestart || !timeend) return setStatus("请填写开始/结束时间", "err");
  if (!reason) return setStatus("请填写原因（50字内）", "err");

  btn.disabled = true;
  setStatus("提交中…", "");
  const resultCard = document.getElementById("resultCard");
  const resultText = document.getElementById("resultText");
  if (resultCard) resultCard.style.display = "none";

  try {
    const resp = await fetch(API_LEAVE, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        grade,
        students,
        time_start: timeStart,
        time_end: timeEnd,
        week,
        timestart,
        timeend,
        reason,
        cycle_replace: cycleReplace,
        mode: "times",
        vercode,
      }),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok || !data.ok) {
      if (data.need_captcha) {
        setStatus("需要验证码：请打开登录页查看验证码并填写后重试。", "err");
      } else {
        setStatus("失败：" + (data.msg || resp.status + " " + resp.statusText), "err");
      }
      if (resultCard && resultText) {
        resultCard.style.display = "";
        resultText.textContent = JSON.stringify(data, null, 2);
      }
      return;
    }

    setStatus("提交成功。请到平台“周期请假查询”核对名单（可能按班级拆分）。", "ok");
    if (resultCard && resultText) {
      resultCard.style.display = "";
      const lines = [];
      lines.push("cycle_stuids: " + (data.cycle_stuids || ""));
      if (Array.isArray(data.students)) {
        data.students.forEach((s, idx) => {
          lines.push(`${idx + 1}. ${s.name} -> user_id=${s.user_id}${s.system_name ? " (" + s.system_name + ")" : ""}`);
        });
      }
      if (data.submit_json) {
        lines.push("");
        lines.push("submit_json:");
        lines.push(JSON.stringify(data.submit_json, null, 2));
      }
      resultText.textContent = lines.join("\n");
    }
  } catch (e) {
    setStatus("请求失败：" + e.message, "err");
  } finally {
    btn.disabled = false;
  }
}

document.addEventListener("DOMContentLoaded", function () {
  const btn = document.getElementById("submitBtn");
  if (btn) btn.addEventListener("click", submitLeave);

  document.querySelectorAll(".lc-week-cb").forEach((c) => {
    c.addEventListener("change", syncLcWeekHiddenFromChecks);
  });
  syncLcWeekHiddenFromChecks();

  // 默认从「今天」起一段周期（本地日期），避免 UTC 导致的星期错位
  const r = guessDefaultCycleRange();
  const s = document.getElementById("timeStart");
  const e = document.getElementById("timeEnd");
  if (s && !s.value) s.value = r.start;
  if (e && !e.value) e.value = r.end;

  const llmBtn = document.getElementById("llmParseBtn");
  if (llmBtn) llmBtn.addEventListener("click", llmParse);
  const llmFillBtn = document.getElementById("llmFillWeekBtn");
  if (llmFillBtn) llmFillBtn.addEventListener("click", llmFillWeek);

  // prefill students from previous localStorage
  try {
    const key = "leaveStudentsDraft";
    const ta = document.getElementById("students");
    if (ta) {
      const old = localStorage.getItem(key);
      if (old && !ta.value.trim()) ta.value = old;
      ta.addEventListener("input", () => localStorage.setItem(key, ta.value));
    }
  } catch (e2) {}
});

