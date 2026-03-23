"use strict";
/**
 * 可选备用：教师数据 / 问卷 API 已合并进上级目录 server.py（Flask）。
 * 仅在不跑 Python、或需单独起 Node 时使用本文件。
 */

const path = require("path");
const express = require("express");
const { db, dbPath } = require("./db");

const app = express();
const PORT = Number(process.env.PORT || 8788);
const ROOT = path.join(__dirname, "..");

app.use(express.json({ limit: "2mb" }));

app.use((req, res, next) => {
  res.setHeader("X-Powered-By", "WSTHomepage-API");
  next();
});

function jsonOk(data) {
  return { ok: true, ...data };
}
function jsonErr(res, status, msg) {
  return res.status(status).json({ ok: false, msg: String(msg || "error") });
}

/* ---------- 与 Flask 管理中心兼容的占位（仅起 Node 时避免首页门禁报错；正式环境请运行 server.py） ----------
 *  审批队列、车牌/请假/网管等真实接口在根目录 server.py（Flask），数据库 keadmin_queue.db。
 *  若只启动本 Node 服务，下方桩可让 index.html 解锁；管理员审核列表仍须 Flask 提供 /api/admin/requests。
 * ---------- */

app.get("/api/admin-gate-status", (req, res) => {
  res.json({ gate_enabled: false });
});

app.post("/api/admin-gate-check", (req, res) => {
  res.json({ ok: true, skip: true });
});

/* ---------- 教师数据 ---------- */

const insTeacher = db.prepare(
  `INSERT INTO teacher_records (name, dept, mobile, email, subjects, remark, payload_json, created_at)
   VALUES (@name, @dept, @mobile, @email, @subjects, @remark, @payload_json, @created_at)`
);

app.post("/api/teacher-data/submit", (req, res) => {
  try {
    const b = req.body || {};
    const name = String(b.name || "").trim();
    if (!name) return jsonErr(res, 400, "缺少姓名");
    const row = {
      name,
      dept: String(b.dept || "").trim() || null,
      mobile: String(b.mobile || "").trim() || null,
      email: String(b.email || "").trim() || null,
      subjects: String(b.subjects || "").trim() || null,
      remark: String(b.remark || "").trim() || null,
      payload_json: JSON.stringify(b),
      created_at: b.submitted_at || new Date().toISOString(),
    };
    insTeacher.run(row);
    return res.json(jsonOk({}));
  } catch (e) {
    return jsonErr(res, 500, e.message);
  }
});

const selTeachers = db.prepare(
  `SELECT id, name, dept, mobile, email, subjects, remark, created_at, payload_json FROM teacher_records ORDER BY id DESC`
);

app.get("/api/teacher-data/list", (req, res) => {
  try {
    const rows = selTeachers.all().map((r) => {
      let submitted_at = r.created_at;
      try {
        if (r.payload_json) {
          const p = JSON.parse(r.payload_json);
          if (p.submitted_at) submitted_at = p.submitted_at;
        }
      } catch (e) {}
      return {
        id: r.id,
        name: r.name,
        dept: r.dept,
        mobile: r.mobile,
        email: r.email,
        subjects: r.subjects,
        remark: r.remark,
        submitted_at,
      };
    });
    return res.json(jsonOk({ data: rows }));
  } catch (e) {
    return jsonErr(res, 500, e.message);
  }
});

/* ---------- 问卷 ---------- */

const upsertSurvey = db.prepare(
  `INSERT INTO quickvote_surveys (id, title, definition_json, updated_at)
   VALUES (@id, @title, @definition_json, datetime('now'))
   ON CONFLICT(id) DO UPDATE SET
     title = excluded.title,
     definition_json = excluded.definition_json,
     updated_at = datetime('now')`
);

const selSurvey = db.prepare(`SELECT id, title, definition_json FROM quickvote_surveys WHERE id = ?`);
const selAllSurveys = db.prepare(`SELECT id, title, definition_json FROM quickvote_surveys ORDER BY updated_at DESC`);

app.get("/api/quickvote/surveys", (req, res) => {
  try {
    const rows = selAllSurveys.all();
    const data = {};
    for (const r of rows) {
      try {
        const def = JSON.parse(r.definition_json);
        data[r.id] = def;
      } catch (e) {
        data[r.id] = { title: r.title, questions: [] };
      }
    }
    return res.json(jsonOk({ data }));
  } catch (e) {
    return jsonErr(res, 500, e.message);
  }
});

app.get("/api/quickvote/survey/:id", (req, res) => {
  try {
    const id = String(req.params.id || "").trim();
    if (!id) return jsonErr(res, 400, "缺少 id");
    const r = selSurvey.get(id);
    if (!r) return jsonErr(res, 404, "问卷不存在");
    let def;
    try {
      def = JSON.parse(r.definition_json);
    } catch (e) {
      def = { title: r.title, questions: [] };
    }
    return res.json(jsonOk({ data: def }));
  } catch (e) {
    return jsonErr(res, 500, e.message);
  }
});

app.post("/api/quickvote/survey", (req, res) => {
  try {
    const b = req.body || {};
    const title = String(b.title || "").trim();
    if (!title) return jsonErr(res, 400, "缺少标题");
    const id =
      String(b.id || "").trim() ||
      "sv_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 8);
    const def = { title, questions: Array.isArray(b.questions) ? b.questions : [] };
    upsertSurvey.run({ id, title, definition_json: JSON.stringify(def) });
    return res.json(jsonOk({ id }));
  } catch (e) {
    return jsonErr(res, 500, e.message);
  }
});

app.put("/api/quickvote/survey/:id", (req, res) => {
  try {
    const id = String(req.params.id || "").trim();
    if (!id) return jsonErr(res, 400, "缺少 id");
    const b = req.body || {};
    const title = String(b.title || "").trim() || "未命名";
    const def = { title, questions: Array.isArray(b.questions) ? b.questions : [] };
    upsertSurvey.run({ id, title, definition_json: JSON.stringify(def) });
    return res.json(jsonOk({}));
  } catch (e) {
    return jsonErr(res, 500, e.message);
  }
});

const insResp = db.prepare(
  `INSERT INTO quickvote_responses (survey_id, answers_json, submitted_at) VALUES (?, ?, ?)`
);

app.post("/api/quickvote/submit", (req, res) => {
  try {
    const b = req.body || {};
    const survey_id = String(b.survey_id || "").trim();
    if (!survey_id) return jsonErr(res, 400, "缺少 survey_id");
    const answers = b.answers != null ? b.answers : {};
    const submitted_at = b.submitted_at || new Date().toISOString();
    insResp.run(survey_id, JSON.stringify(answers), submitted_at);
    return res.json(jsonOk({}));
  } catch (e) {
    return jsonErr(res, 500, e.message);
  }
});

const selResp = db.prepare(
  `SELECT id, answers_json, submitted_at FROM quickvote_responses WHERE survey_id = ? ORDER BY id DESC`
);

app.get("/api/quickvote/responses/:id", (req, res) => {
  try {
    const id = String(req.params.id || "").trim();
    if (!id) return jsonErr(res, 400, "缺少 id");
    const rows = selResp.all(id).map((r) => ({
      id: r.id,
      submitted_at: r.submitted_at,
      answers: JSON.parse(r.answers_json || "{}"),
    }));
    return res.json(jsonOk({ data: rows }));
  } catch (e) {
    return jsonErr(res, 500, e.message);
  }
});

/* ---------- 静态站点（根目录） ---------- */

app.use(express.static(ROOT, { extensions: ["html"] }));

app.use((req, res) => {
  res.status(404).send("Not found");
});

app.listen(PORT, () => {
  console.log("WSTHomepage API + static  http://127.0.0.1:" + PORT);
  console.log("数据库: " + dbPath);
});
