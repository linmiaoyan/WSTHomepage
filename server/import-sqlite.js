/**
 * 从「外部 SQLite」导入到当前库（请按原表结构修改 SQL）。
 * 用法: set SOURCE_DB=D:\path\to\old.db  &&  node import-sqlite.js
 */
"use strict";

const fs = require("fs");
const Database = require("better-sqlite3");
const { db } = require("./db");

const source = process.env.SOURCE_DB;
if (!source || !fs.existsSync(source)) {
  console.error("请设置环境变量 SOURCE_DB 为原项目 .db 的完整路径");
  process.exit(1);
}

const src = new Database(source, { readonly: true });

try {
  // 示例（请按原库修改表名与字段）：
  // const rows = src.prepare("SELECT * FROM your_old_table").all();
  // const ins = db.prepare(
  //   `INSERT INTO teacher_records (name, dept, mobile, email, subjects, remark, payload_json, created_at)
  //    VALUES (@name, @dept, @mobile, @email, @subjects, @remark, @payload_json, @created_at)`
  // );
  // const tx = db.transaction((list) => { for (const r of list) ins.run(r); });
  // tx(rows);

  console.log("未执行任何导入：请编辑 import-sqlite.js，编写与原库对应的 SELECT/INSERT。");
} finally {
  src.close();
}
