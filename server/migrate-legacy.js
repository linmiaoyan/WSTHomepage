/**
 * 从 D:\OneDrive\09教育技术处 下的 TeacherDataSystem / QuickVote 自动查找 *.db / *.sqlite 并导入到当前库。
 * 环境变量:
 *   MIGRATE_ROOT   默认 D:\OneDrive\09教育技术处
 *   MIGRATE_FORCE  设为 1 时忽略 migrate_log 跳过记录
 *
 * 用法: npm run migrate
 */
"use strict";

const fs = require("fs");
const path = require("path");
const Database = require("better-sqlite3");
const { db, dbPath } = require("./db");

const ROOT = process.env.MIGRATE_ROOT || "D:\\OneDrive\\09教育技术处";
const FORCE = String(process.env.MIGRATE_FORCE || "") === "1";

const logged = db.prepare(`SELECT 1 FROM migrate_log WHERE source_path = ? AND kind = ?`);
const logInsert = db.prepare(
  `INSERT INTO migrate_log (source_path, kind, rows_imported, note) VALUES (?,?,?,?)`
);

function normPath(p) {
  return path.normalize(path.resolve(p));
}

function safeReadDir(d) {
  try {
    return fs.readdirSync(d, { withFileTypes: true });
  } catch (e) {
    return [];
  }
}

function findProjectDirs(base) {
  const out = { teacher: null, quickvote: null };
  const entries = safeReadDir(base);
  for (const e of entries) {
    if (!e.isDirectory()) continue;
    const n = e.name;
    const full = path.join(base, n);
    if (/^TeacherDataSystem$/i.test(n)) out.teacher = full;
    if (/^QuickVote$/i.test(n)) out.quickvote = full;
  }
  return out;
}

function walkDbFiles(dir, depth, maxDepth, acc) {
  if (depth > maxDepth || !dir) return;
  for (const e of safeReadDir(dir)) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) {
      if (e.name === "node_modules" || e.name === ".git") continue;
      walkDbFiles(p, depth + 1, maxDepth, acc);
    } else if (/\.(db|sqlite|sqlite3)$/i.test(e.name)) {
      acc.push(p);
    }
  }
}

function tableList(src) {
  return src
    .prepare(`SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name`)
    .all()
    .map((r) => r.name);
}

function tableInfo(src, t) {
  return src.prepare(`PRAGMA table_info(${quoteIdent(t)})`).all();
}

function quoteIdent(t) {
  return '"' + String(t).replace(/"/g, '""') + '"';
}

function lowerMap(row) {
  const m = {};
  for (const k of Object.keys(row)) m[String(k).toLowerCase()] = row[k];
  return m;
}

function pick(m, keys) {
  for (const k of keys) {
    if (m[k] !== undefined && m[k] !== null && String(m[k]).trim() !== "") return m[k];
  }
  return null;
}

function mergeJsonRow(row, m) {
  const jsonKeys = ["data", "json", "payload", "form_data", "content", "body", "record"];
  for (const jk of jsonKeys) {
    const raw = m[jk];
    if (typeof raw !== "string" || !raw.trim()) continue;
    try {
      const o = JSON.parse(raw);
      if (o && typeof o === "object" && !Array.isArray(o)) {
        for (const [k, v] of Object.entries(o)) {
          const lk = String(k).toLowerCase();
          if (m[lk] === undefined || m[lk] === null || String(m[lk]).trim() === "") m[lk] = v;
        }
      }
    } catch (e) {}
  }
}

const NAME_KEYS = ["name", "xm", "teacher_name", "teachername", "real_name", "username", "user_name", "姓名", "老师姓名", "教师姓名"];
const DEPT_KEYS = ["dept", "department", "org", "group", "部门", "学科组", "教研组"];
const MOBILE_KEYS = ["mobile", "phone", "tel", "telephone", "手机", "联系电话"];
const EMAIL_KEYS = ["email", "mail", "邮箱", "e_mail"];
const SUBJ_KEYS = ["subjects", "subject", "course", "courses", "科目", "任教科目", "教学科目"];
const REMARK_KEYS = ["remark", "note", "memo", "备注", "说明"];
const TIME_KEYS = ["submitted_at", "created_at", "create_time", "updated_at", "submit_time", "time", "创建时间", "提交时间"];

const insTeacher = db.prepare(
  `INSERT INTO teacher_records (name, dept, mobile, email, subjects, remark, payload_json, created_at)
   VALUES (@name, @dept, @mobile, @email, @subjects, @remark, @payload_json, @created_at)`
);

const upsertSurvey = db.prepare(
  `INSERT INTO quickvote_surveys (id, title, definition_json, updated_at)
   VALUES (@id, @title, @definition_json, datetime('now'))
   ON CONFLICT(id) DO UPDATE SET
     title = excluded.title,
     definition_json = excluded.definition_json,
     updated_at = datetime('now')`
);

const insResp = db.prepare(
  `INSERT INTO quickvote_responses (survey_id, answers_json, submitted_at) VALUES (?,?,?)`
);

function importTeachersFromDb(srcPath, src) {
  const tables = tableList(src);
  const prefer = ["teacher_records", "teachers", "teacher", "teacher_data", "t_teacher", "submissions", "records", "form_records", "data_records"];
  let imported = 0;
  const tried = new Set();

  function importTable(t) {
    if (tried.has(t)) return;
    if (/quickvote/i.test(t)) return;
    tried.add(t);
    let cols;
    try {
      cols = tableInfo(src, t);
    } catch (e) {
      return;
    }
    if (!cols.length) return;
    const colNames = cols.map((c) => c.name);
    let rows;
    try {
      rows = src.prepare(`SELECT * FROM ${quoteIdent(t)}`).all();
    } catch (e) {
      return;
    }
    for (const row of rows) {
      let m = lowerMap(row);
      mergeJsonRow(row, m);
      const name = pick(m, NAME_KEYS.map((k) => k.toLowerCase()));
      if (!name || !String(name).trim()) continue;
      const dept = pick(m, DEPT_KEYS.map((k) => k.toLowerCase()));
      const mobile = pick(m, MOBILE_KEYS.map((k) => k.toLowerCase()));
      const email = pick(m, EMAIL_KEYS.map((k) => k.toLowerCase()));
      const subjects = pick(m, SUBJ_KEYS.map((k) => k.toLowerCase()));
      const remark = pick(m, REMARK_KEYS.map((k) => k.toLowerCase()));
      let created = pick(m, TIME_KEYS.map((k) => k.toLowerCase()));
      if (!created) created = new Date().toISOString();
      const payload = { ...row, _migrated_from: srcPath, _migrated_table: t };
      insTeacher.run({
        name: String(name).trim(),
        dept: dept != null ? String(dept).trim() : null,
        mobile: mobile != null ? String(mobile).trim() : null,
        email: email != null ? String(email).trim() : null,
        subjects: subjects != null ? String(subjects).trim() : null,
        remark: remark != null ? String(remark).trim() : null,
        payload_json: JSON.stringify(payload),
        created_at: String(created),
      });
      imported++;
    }
  }

  for (const t of prefer) if (tables.includes(t)) importTable(t);
  for (const t of tables) importTable(t);

  return imported;
}

const SURVEY_TABLES = ["surveys", "survey", "questionnaires", "questionnaire", "votes", "vote", "polls"];
const RESP_TABLES = ["responses", "answers", "vote_records", "survey_responses", "submissions", "records"];

function surveyRowToDef(row) {
  const m = lowerMap(row);
  mergeJsonRow(row, m);
  const id = pick(m, ["id", "survey_id", "sid"]);
  const title = pick(m, ["title", "name", "主题", "标题"]) || "未命名问卷";
  let questions = [];
  const qraw = pick(m, ["questions", "items", "config", "definition", "schema"]);
  if (typeof qraw === "string") {
    try {
      const parsed = JSON.parse(qraw);
      if (Array.isArray(parsed)) questions = parsed;
      else if (parsed && Array.isArray(parsed.questions)) questions = parsed.questions;
    } catch (e) {}
  } else if (Array.isArray(qraw)) questions = qraw;
  const def = { title: String(title), questions };
  return { id: id != null ? String(id) : null, def };
}

function importQuickVoteFromDb(srcPath, src) {
  const tables = tableList(src);
  let importedS = 0;
  let importedR = 0;
  const surveyIds = new Set();

  for (const t of tables) {
    if (!SURVEY_TABLES.includes(t.toLowerCase())) continue;
    let rows;
    try {
      rows = src.prepare(`SELECT * FROM ${quoteIdent(t)}`).all();
    } catch (e) {
      continue;
    }
    for (const row of rows) {
      const { id, def } = surveyRowToDef(row);
      if (!id) continue;
      const fullDef = { ...def, _migrated_from: srcPath, _migrated_table: t };
      upsertSurvey.run({
        id,
        title: fullDef.title || "未命名",
        definition_json: JSON.stringify(fullDef),
      });
      surveyIds.add(id);
      importedS++;
    }
  }

  for (const t of tables) {
    if (!RESP_TABLES.includes(t.toLowerCase())) continue;
    let rows;
    try {
      rows = src.prepare(`SELECT * FROM ${quoteIdent(t)}`).all();
    } catch (e) {
      continue;
    }
    for (const row of rows) {
      const m = lowerMap(row);
      mergeJsonRow(row, m);
      const sid = pick(m, ["survey_id", "vote_id", "questionnaire_id", "qid", "sid", "poll_id"]);
      if (!sid) continue;
      const sidStr = String(sid);
      let answers = pick(m, ["answers", "data", "content", "result", "payload", "json"]);
      if (answers == null) answers = {};
      if (typeof answers === "string") {
        try {
          answers = JSON.parse(answers);
        } catch (e) {
          answers = { raw: answers };
        }
      }
      if (typeof answers !== "object" || answers === null) answers = { value: answers };
      const ts = pick(m, TIME_KEYS.map((k) => k.toLowerCase())) || new Date().toISOString();
      if (!surveyIds.has(sidStr)) {
        upsertSurvey.run({
          id: sidStr,
          title: "(迁移占位·仅有答卷)",
          definition_json: JSON.stringify({ title: "(迁移占位)", questions: [], _migrated_placeholder: true }),
        });
        surveyIds.add(sidStr);
        importedS++;
      }
      insResp.run(sidStr, JSON.stringify(answers), String(ts));
      importedR++;
    }
  }

  return { surveys: importedS, responses: importedR };
}

function shouldSkip(pathAbs, kind) {
  if (FORCE) return false;
  const r = logged.get(pathAbs, kind);
  return !!r;
}

function markDone(pathAbs, kind, n, note) {
  logInsert.run(pathAbs, kind, n, note || null);
}

function main() {
  console.log("MIGRATE_ROOT =", ROOT);
  console.log("目标库 =", dbPath);

  if (!fs.existsSync(ROOT)) {
    console.error("根目录不存在，请设置 MIGRATE_ROOT 或检查路径:", ROOT);
    process.exit(2);
  }

  const { teacher, quickvote } = findProjectDirs(ROOT);
  console.log("TeacherDataSystem =", teacher || "(未找到)");
  console.log("QuickVote =", quickvote || "(未找到)");

  const files = [];
  if (teacher) walkDbFiles(teacher, 0, 8, files);
  if (quickvote) walkDbFiles(quickvote, 0, 8, files);

  const uniq = [...new Set(files.map(normPath))].filter((p) => normPath(p) !== normPath(dbPath));

  if (!uniq.length) {
    console.log("未发现可导入的 .db/.sqlite 文件（在子项目目录内）。");
    return;
  }

  console.log("待扫描数据库文件数:", uniq.length);

  for (const fp of uniq) {
    const label = path.relative(ROOT, fp);
    let src;
    try {
      src = new Database(fp, { readonly: true, fileMustExist: true });
    } catch (e) {
      console.warn("跳过（无法打开）:", label, e.message);
      continue;
    }

    try {
      const kindTeacher = "teacher:" + label;
      if (!shouldSkip(fp, kindTeacher)) {
        const n = importTeachersFromDb(fp, src);
        if (n > 0) {
          markDone(fp, kindTeacher, n, "teacher rows");
          console.log("[教师]", label, "导入行数:", n);
        }
      }

      const kindQv = "quickvote:" + label;
      if (!shouldSkip(fp, kindQv)) {
        const r = importQuickVoteFromDb(fp, src);
        const n = r.surveys + r.responses;
        if (n > 0) {
          markDone(fp, kindQv, n, `surveys ${r.surveys}, responses ${r.responses}`);
          console.log("[问卷]", label, "问卷行:", r.surveys, "答卷行:", r.responses);
        }
      }
    } finally {
      src.close();
    }
  }

  console.log("迁移完成。");
}

main();
