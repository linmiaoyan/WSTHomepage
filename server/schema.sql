-- 默认表结构（与当前 WSTHompage 前端约定一致）。
-- 若需「照搬」原 TeacherDataSystem / QuickVote：请把原项目里的 CREATE TABLE / 迁移 SQL
-- 合并进本文件（或拆成 migration-002.sql），并调整 server/index.js 中的 INSERT/SELECT 字段映射。

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS teacher_records (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  dept TEXT,
  mobile TEXT,
  email TEXT,
  subjects TEXT,
  remark TEXT,
  payload_json TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS quickvote_surveys (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  definition_json TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS quickvote_responses (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  survey_id TEXT NOT NULL,
  answers_json TEXT NOT NULL,
  submitted_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (survey_id) REFERENCES quickvote_surveys(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_qv_resp_survey ON quickvote_responses(survey_id);

CREATE TABLE IF NOT EXISTS migrate_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_path TEXT NOT NULL,
  kind TEXT NOT NULL,
  rows_imported INTEGER NOT NULL DEFAULT 0,
  note TEXT,
  imported_at TEXT NOT NULL DEFAULT (datetime('now'))
);
