"use strict";

const fs = require("fs");
const path = require("path");
const Database = require("better-sqlite3");

// 与根目录 Flask server.py 共用 keadmin_queue.db（教师数据、问卷、审批队列同库）
const dbPath = process.env.WST_DB_PATH || path.join(__dirname, "..", "keadmin_queue.db");
const schemaPath = path.join(__dirname, "schema.sql");

const db = new Database(dbPath);
db.pragma("journal_mode = WAL");
db.pragma("foreign_keys = ON");

const schemaSql = fs.readFileSync(schemaPath, "utf8");
db.exec(schemaSql);

function close() {
  db.close();
}

module.exports = { db, dbPath, close };
