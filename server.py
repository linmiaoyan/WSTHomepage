import os
import json
from datetime import datetime

from flask import Flask, request, jsonify, send_from_directory, redirect, session as web_session
import requests
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5
import base64
import hashlib
import re
import time
import sqlite3
import uuid
from urllib.parse import urlencode, urljoin


def _env_here() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


def _read_env_file(path: str) -> dict:
    env = {}
    if not path or not os.path.exists(path):
        return env
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            s = (line or "").strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def _env_get(key: str, default: str = "") -> str:
    v = (os.environ.get(key) or "").strip()
    if v:
        return v
    return (_read_env_file(_env_here()).get(key) or default).strip()


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_web_root_env = _env_get("WEB_ROOT_DIR", "").strip()
if _web_root_env:
    WEB_ROOT = _web_root_env if os.path.isabs(_web_root_env) else os.path.join(BASE_DIR, _web_root_env)
else:
    default_public = os.path.join(BASE_DIR, "public")
    if os.path.isdir(default_public) and os.path.isfile(os.path.join(default_public, "index.html")):
        WEB_ROOT = default_public
    else:
        WEB_ROOT = BASE_DIR
if not os.path.isdir(WEB_ROOT):
    WEB_ROOT = BASE_DIR

app = Flask(__name__, static_folder=WEB_ROOT, static_url_path='')

# ---- 敏感配置仅从环境变量或 .env 读取（勿写死在代码里）----
EDU_CFG_PHP = _env_get("EDU_CFG_PHP", "")
LEAVE_BASE = _env_get("LEAVE_BASE", "")
LEAVE_USER = _env_get("LEAVE_USER", "")
LEAVE_PASS = _env_get("LEAVE_PASS", "")
CAMPUS_BASE = _env_get("CAMPUS_BASE", "")
CAMPUS_TOKEN = _env_get("CAMPUS_TOKEN", "")

_EDU_CFG = None
_EDU_TOKEN_CACHE = {"token": "", "expires_at": 0}

# 智慧校园登录 RSA 公钥（非密钥，可保留在代码中）
LEAVE_PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDVJ9RF0KKJJhpareYt7amtuQz67ASF9BUrN1Ebnm9RInsXQUVm3nbU8MM/1nnZ4kR6bN0Mc8AgrOhem58XUEamyWYZZoVWMfMiP2bP0/WSMeyqQ5CdnSiYwIxS/gW/DVB0xTjGPb0HAIAP1hxxM3aVbv2dT4LHRDn9/Xxh1griowIDAQAB
-----END PUBLIC KEY-----"""

session = requests.Session()
platform_session = requests.Session()

# ---- Approval queue storage (local sqlite) ----
APP_DB = os.path.join(os.path.dirname(__file__), 'keadmin_queue.db')

def _db():
    conn = sqlite3.connect(APP_DB)
    conn.row_factory = sqlite3.Row
    return conn

def _init_queue_db():
    conn = _db()
    try:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS requests (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          type TEXT NOT NULL,
          params_json TEXT NOT NULL,
          requester_json TEXT,
          status TEXT NOT NULL DEFAULT 'pending',
          created_at TEXT NOT NULL,
          reviewed_at TEXT,
          review_comment TEXT
        )
        """)
        # Best-effort migrate old DBs (add requester_json).
        cols = [r[1] for r in conn.execute("PRAGMA table_info(requests)").fetchall()]
        if "requester_json" not in cols:
            conn.execute("ALTER TABLE requests ADD COLUMN requester_json TEXT")
        if "execute_result" not in cols:
            conn.execute("ALTER TABLE requests ADD COLUMN execute_result TEXT")
        if "executed_at" not in cols:
            conn.execute("ALTER TABLE requests ADD COLUMN executed_at TEXT")
        conn.commit()
    finally:
        conn.close()

_init_queue_db()




def _now_iso():
    return datetime.utcnow().isoformat() + 'Z'


def _dingtalk_identity_bucket(d: dict) -> dict:
    """从钉钉用户/快照中抽取用于「我的申请」比对的标识（任一匹配即视为同一人）。"""
    if not isinstance(d, dict):
        return {"user_id": "", "open_id": "", "union_id": ""}
    uid = str(d.get("userId") or d.get("userid") or "").strip()
    oid = str(d.get("openId") or d.get("open_id") or "").strip()
    uni = str(d.get("unionId") or d.get("unionid") or "").strip()
    return {"user_id": uid, "open_id": oid, "union_id": uni}


def _same_dingtalk_identity(me: dict, requester: dict) -> bool:
    a = _dingtalk_identity_bucket(me)
    b = _dingtalk_identity_bucket(requester)
    if a["user_id"] and b["user_id"] and a["user_id"] == b["user_id"]:
        return True
    if a["open_id"] and b["open_id"] and a["open_id"] == b["open_id"]:
        return True
    if a["union_id"] and b["union_id"] and a["union_id"] == b["union_id"]:
        return True
    return False


def _me_has_dingtalk_identity(me: dict) -> bool:
    b = _dingtalk_identity_bucket(me)
    return bool(b["user_id"] or b["open_id"] or b["union_id"])


def _admin_gate_expected() -> str:
    return (_env_get("ADMIN_GATE_CODE", "") or "").strip()


def _admin_api_authorized() -> bool:
    """未配置 ADMIN_GATE_CODE 时保持兼容（与旧行为一致）；配置后须先通过口令校验写入 session。"""
    exp = _admin_gate_expected()
    if not exp:
        return True
    return bool(web_session.get("ke_admin_gate_ok"))


def _admin_api_denied_response():
    return jsonify({
        "ok": False,
        "need_admin_gate": True,
        "msg": "需要先在「管理中心」父页面输入正确访问口令，或刷新后重新进入管理中心。",
    }), 401


def _campus_verify_tls() -> bool:
    """
    校园网管接口证书校验开关：
    - CAMPUS_VERIFY_TLS=1/true/on/yes -> 校验证书
    - 其他（默认）-> 不校验（适配内网自签证书）
    """
    return str(_env_get("CAMPUS_VERIFY_TLS", "0")).strip().lower() in ("1", "true", "yes", "on")


def _campus_allow_client_override() -> bool:
    """仅在为真时允许请求体覆盖 CAMPUS_BASE/CAMPUS_TOKEN（本地调试）；默认禁止以防 SSRF/开放代理。"""
    return str(_env_get("CAMPUS_ALLOW_CLIENT_OVERRIDE", "0")).strip().lower() in ("1", "true", "yes", "on")


def _campus_cfg_from_request(data: dict) -> tuple:
    """校园网管 base/token：默认仅用 .env；CAMPUS_ALLOW_CLIENT_OVERRIDE=1 时才接受请求体覆盖。"""
    if not isinstance(data, dict):
        data = {}
    if _campus_allow_client_override():
        base = str(data.get("baseUrl") or data.get("base_url") or "").strip() or CAMPUS_BASE
        token = str(data.get("csrfToken") or data.get("csrf_token") or "").strip() or CAMPUS_TOKEN
    else:
        base = CAMPUS_BASE
        token = CAMPUS_TOKEN
    return base.rstrip("/"), token


def _row_to_req(row):
    try:
        params = json.loads(row["params_json"] or "{}")
    except Exception:
        params = {}
    try:
        requester = json.loads(row["requester_json"] or "null")
    except Exception:
        requester = None
    keys = list(row.keys())
    exec_raw = row["execute_result"] if "execute_result" in keys else None
    executed_at = row["executed_at"] if "executed_at" in keys else None
    exec_obj = None
    if exec_raw:
        try:
            exec_obj = json.loads(exec_raw)
        except Exception:
            exec_obj = {"raw": str(exec_raw)[:500]}
    return {
        "id": row["id"],
        "type": row["type"],
        "params": params,
        "requester": requester,
        "status": row["status"],
        "created_at": row["created_at"],
        "reviewed_at": row["reviewed_at"],
        "review_comment": row["review_comment"],
        "execute_result": exec_obj,
        "executed_at": executed_at,
    }


def _parse_leave_week_slots(week_str) -> list:
    """从 week 参数解析出 1-7 的列表，支持 3、'3'、'1,2,3,4,5'。"""
    if week_str is None:
        return [3]
    if isinstance(week_str, int):
        return [week_str] if 1 <= week_str <= 7 else [3]
    ws = str(week_str).strip().replace("，", ",")
    if not ws:
        return [3]
    out = []
    for part in ws.split(","):
        part = part.strip()
        if not part:
            continue
        if part.isdigit():
            n = int(part)
            if 1 <= n <= 7:
                out.append(n)
    return out if out else [3]


def _infer_weekday_numbers_from_leave_text(text: str):
    """
    从自然语言推断「涉及星期几」列表（1=周一…7=周日）。
    命中则返回列表；否则 None（不覆盖模型结果）。
    """
    if not text:
        return None
    compact = re.sub(r"\s+", "", text)
    if re.search(
        r"周一到周五|周一至周五|星期一到星期五|周一到周五每天|每个工作日|工作日每天|每周一至周五|星期一到五",
        compact,
    ):
        return [1, 2, 3, 4, 5]
    if re.search(r"周一到周日|周一至周日|星期一到星期日|一周七天|全周|每天都有", compact):
        return [1, 2, 3, 4, 5, 6, 7]
    if re.search(r"周二到周四", compact):
        return [2, 3, 4]
    if re.search(r"周六周日|周六日|双休日", compact):
        return [6, 7]
    return None


def _sanitize_leave_cycle_dates(params: dict, text: str) -> None:
    """纠正明显错误的 time_start/time_end；默认从「今天」起算，避免模型胡编旧日期。"""
    from datetime import date, timedelta

    today = date.today()
    ts = str(params.get("time_start") or params.get("timeStart") or "").strip()
    te = str(params.get("time_end") or params.get("timeEnd") or "").strip()

    def ok_iso(s: str) -> bool:
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", s):
            return False
        y = int(s[:4])
        try:
            date.fromisoformat(s)
        except ValueError:
            return False
        return 2024 <= y <= 2036

    if not ok_iso(ts):
        params["time_start"] = today.isoformat()
        ts = params["time_start"]
    ds = date.fromisoformat(ts)
    multi_week = "," in str(params.get("week") or "")
    if not ok_iso(te) or te < ts:
        if multi_week or re.search(r"周一到周五|周一至周五|星期一到星期五|工作日", text.replace(" ", "")):
            params["time_end"] = (ds + timedelta(days=20)).isoformat()
        else:
            params["time_end"] = (ds + timedelta(days=13)).isoformat()
    elif not ok_iso(te):
        params["time_end"] = (ds + timedelta(days=13)).isoformat()


def _map_leave_params_to_cycle_body(p: dict) -> dict:
    """将队列/NLP 中的周期请假字段映射为 _leave_cycle_submit_core 所需 body。"""
    from datetime import date, timedelta

    today = date.today().isoformat()
    end7 = (date.today() + timedelta(days=7)).isoformat()
    # grade：平台「关联年级」ID，与 …/add/grade/{grade}/ 一致，勿臆测为 1/2/3。
    grade = str(p.get("grade") if p.get("grade") is not None else p.get("gids") or "1").strip()
    week_raw = p.get("week") if p.get("week") is not None else p.get("weekday")
    ws_single = str(week_raw).strip() if week_raw is not None else ""
    if ws_single and "," not in ws_single.replace("，", ",") and not ws_single.isdigit():
        try:
            wr_int = int(float(ws_single))
            if 1 <= wr_int <= 7:
                week_raw = wr_int
        except (TypeError, ValueError):
            for z, d in [
                ("一", "1"), ("二", "2"), ("三", "3"), ("四", "4"),
                ("五", "5"), ("六", "6"), ("日", "7"), ("天", "7"),
            ]:
                if z in ws_single:
                    week_raw = int(d)
                    break
    week_slots = _parse_leave_week_slots(week_raw)
    week_csv = ",".join(str(x) for x in week_slots)
    students = p.get("students")
    if isinstance(students, list):
        students_raw = "，".join(str(s).strip() for s in students if str(s).strip())
    else:
        students_raw = (students or p.get("students_raw") or "").strip()
    timestart = str(p.get("timestart") or "").strip()
    timeend = str(p.get("timeend") or "").strip()
    t_obj = p.get("time")
    if isinstance(t_obj, dict):
        timestart = timestart or str(t_obj.get("timestart") or "").strip()
        timeend = timeend or str(t_obj.get("timeend") or "").strip()
    blob = " ".join([
        str(p.get("timestart") or ""),
        str(p.get("timeend") or ""),
        str(p.get("reason") or ""),
        str(p.get("notes") or ""),
        str(p.get("lesson_hint") or ""),
    ])
    wd_for_table = week_slots[0] if week_slots else None
    hit = _wzkgz_2025s1_resolve_leave_times(wd_for_table, blob, str(p.get("lesson_hint") or ""))
    if hit:
        timestart, timeend = hit[0], hit[1]
    blob_compact = blob.replace(" ", "")
    if "晚三" in blob_compact or "晚3" in blob_compact:
        timestart, timeend = "20:50", "21:40"
    if not timestart or ":" not in timestart:
        timestart = "15:15"
    if not timeend or ":" not in timeend:
        timeend = "15:55"
    reason = (p.get("reason") or "").strip() or "周期请假"
    ts = str(p.get("time_start") or p.get("timeStart") or today).strip()
    te = str(p.get("time_end") or p.get("timeEnd") or end7).strip()
    return {
        "grade": grade,
        "students": students_raw,
        "time_start": ts,
        "time_end": te,
        "week": week_csv,
        "timestart": timestart,
        "timeend": timeend,
        "reason": reason,
        "cycle_replace": str(p.get("cycle_replace") or "0"),
        "mode": (str(p.get("mode") or "times").strip().lower() or "times"),
        "vercode": str(p.get("vercode") or "").strip(),
    }


def _execute_approved_queue_item(req: dict) -> dict:
    """管理员通过后：按类型调用与管理中心一致的云联/网管接口，返回可 JSON 序列化的结果摘要。"""
    t = (req.get("type") or "").strip()
    p = req.get("params") or {}
    if not isinstance(p, dict):
        p = {}
    rid = req.get("id")
    try:
        if t == "add_vehicle":
            data = {
                "plate_no": (p.get("plate_no") or "").strip(),
                "plate_type": str(p.get("plate_type") or "0"),
                "team_uid": str(p.get("team_uid") or "").strip(),
                "remark": (p.get("remark") or "").strip(),
                "start_date": (p.get("start_date") or "").strip(),
                "end_date": (p.get("end_date") or "").strip(),
                "edu_auth_token": "",
            }
            if not data["plate_no"]:
                return {"ok": False, "type": t, "id": rid, "message": "缺少车牌号，无法自动提交"}
            if data["plate_type"] != "1" and not data["team_uid"]:
                return {
                    "ok": False,
                    "type": t,
                    "id": rid,
                    "message": "长期车牌需在参数中填写云平台职工的 team_uid；请在管理中心「添加职工车牌」选好职工后重新入队，或驳回让教师补充。",
                }
            if data["plate_type"] == "1" and (not data["start_date"] or not data["end_date"]):
                return {"ok": False, "type": t, "id": rid, "message": "临时车牌缺少开始/结束日期，无法自动提交"}
            cloud_j, sc, need_login = _cloud_post_add_vehicle(data)
            if need_login is not None:
                return {
                    "ok": False,
                    "type": t,
                    "id": rid,
                    "message": "云平台需重新登录。请管理员先在管理中心完成「平台管理员登录」后再审批。",
                    "detail": need_login,
                }
            ok = sc < 400 and isinstance(cloud_j, dict) and str(cloud_j.get("code")) == "200"
            msg = (cloud_j or {}).get("msg") if isinstance(cloud_j, dict) else ""
            return {
                "ok": ok,
                "type": t,
                "id": rid,
                "message": msg or ("云平台已受理" if ok else "云平台返回失败"),
                "http_status": sc,
                "cloud": cloud_j,
            }

        if t == "leave_cycle":
            body = _map_leave_params_to_cycle_body(p)
            out, code = _leave_cycle_submit_core(body)
            ok = bool(out.get("ok")) and code < 400
            return {
                "ok": ok,
                "type": t,
                "id": rid,
                "message": out.get("msg") or ("周期请假已提交" if ok else "周期请假提交失败"),
                "http_status": code,
                "detail": out,
            }

        if t == "reset_net_password":
            if not CAMPUS_BASE or not CAMPUS_TOKEN:
                return {
                    "ok": False,
                    "type": t,
                    "id": rid,
                    "message": "未配置校园网管接口（.env 中 CAMPUS_BASE / CAMPUS_TOKEN），无法自动重置密码",
                }
            user_id = (p.get("userId") or p.get("user_id") or "").strip()
            password = p.get("password") or ""
            user_name = (p.get("userName") or p.get("user_name") or user_id).strip()
            if not user_id or not password:
                return {"ok": False, "type": t, "id": rid, "message": "缺少用户ID或新密码，无法自动提交"}
            url = f'{CAMPUS_BASE}/controller/campus/v1/usermgr/userpwd/{user_id}'
            body = {
                "userName": user_name,
                "userId": user_id,
                "password": password,
                "passwordConfirm": password,
            }
            headers = {
                "accept": "application/json",
                "content-type": "application/json",
                "x-requested-with": "XMLHttpRequest",
                "http_x_requested_with": "XMLHttpRequest",
                "x-uni-crsf-token": CAMPUS_TOKEN,
                "roarand": CAMPUS_TOKEN,
            }
            resp = session.put(url, json=body, headers=headers, timeout=15)
            try:
                j = resp.json()
            except Exception:
                j = {"text": (resp.text or "")[:400]}
            ok = resp.status_code < 400
            return {
                "ok": ok,
                "type": t,
                "id": rid,
                "message": "网管接口已调用",
                "http_status": resp.status_code,
                "detail": j,
            }

        if t == "seal":
            return _auto_generate_seal_result_pdf(req)

        return {"ok": False, "type": t, "id": rid, "message": f"未知申请类型：{t}"}
    except Exception as e:
        return {"ok": False, "type": t, "id": rid, "message": str(e)}


UPLOADS_DIR = os.path.join(os.path.dirname(__file__), 'uploads')
os.makedirs(UPLOADS_DIR, exist_ok=True)

SEAL_STAMP_NAMES = ("seal_stamp.png", "seal_stamp.jpg", "seal_stamp.jpeg", "seal_stamp.webp", "seal_stamp.gif")


def _write_white_png(path: str, w: int, h: int) -> None:
    """生成 RGB 纯白 PNG（无第三方依赖），用于校章占位图。"""
    import struct
    import zlib as _zlib

    raw = b"".join([b"\x00" + bytes([255] * (w * 3)) for _ in range(h)])
    comp = _zlib.compress(raw, 9)

    def _chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", _zlib.crc32(tag + data) & 0xFFFFFFFF)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    body = sig + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", comp) + _chunk(b"IEND", b"")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as f:
        f.write(body)


def _ensure_seal_placeholder_png() -> None:
    """首次运行时写入 public/images/seal-placeholder.png（纯白占位）。"""
    rel = os.path.join("images", "seal-placeholder.png")
    path = os.path.join(WEB_ROOT, rel)
    if os.path.isfile(path):
        return
    try:
        _write_white_png(path, 160, 160)
    except OSError:
        pass


_ensure_seal_placeholder_png()


def _seal_stamp_upload_path_and_url():
    """若管理员已上传校章图则返回本地路径与 /uploads/ URL，否则占位图 URL。"""
    for name in SEAL_STAMP_NAMES:
        p = os.path.join(UPLOADS_DIR, name)
        if os.path.isfile(p):
            return p, f"/uploads/{name}"
    return None, "/images/seal-placeholder.png"


def _remove_seal_stamp_uploads():
    for name in SEAL_STAMP_NAMES:
        p = os.path.join(UPLOADS_DIR, name)
        if os.path.isfile(p):
            try:
                os.remove(p)
            except OSError:
                pass


@app.route('/uploads/<path:filename>')
def uploads(filename):
    return send_from_directory(UPLOADS_DIR, filename, as_attachment=False)


@app.route("/api/seal-stamp", methods=["GET"])
def api_seal_stamp():
    """教师选点预览 / 管理端展示：当前校章图 URL（未上传则为纯白占位）。"""
    _p, url = _seal_stamp_upload_path_and_url()
    from_upload = bool(_p)
    return jsonify({"ok": True, "url": url, "from_upload": from_upload})


@app.route("/api/admin/seal-stamp", methods=["POST"])
def api_admin_seal_stamp():
    """管理员上传校章图，固定覆盖保存；之后教师端与占位逻辑均读同一文件。"""
    if not _admin_api_authorized():
        return _admin_api_denied_response()
    f = request.files.get("image") or request.files.get("file")
    if not f or not f.filename:
        return jsonify({"ok": False, "msg": "缺少图片文件"}), 400
    name = str(f.filename).lower()
    ext = os.path.splitext(name)[1].lstrip(".")
    if ext not in ("png", "jpg", "jpeg", "webp", "gif"):
        return jsonify({"ok": False, "msg": "仅支持 png / jpg / jpeg / webp / gif"}), 400
    save_name = "seal_stamp." + ext
    _remove_seal_stamp_uploads()
    save_path = os.path.join(UPLOADS_DIR, save_name)
    try:
        f.save(save_path)
    except OSError as e:
        return jsonify({"ok": False, "msg": str(e)}), 500
    _u = f"/uploads/{save_name}"
    return jsonify({"ok": True, "url": _u})


def _safe_upload_path_from_url(u: str) -> str:
    s = str(u or "").strip()
    if not s.startswith("/uploads/"):
        return ""
    name = s[len("/uploads/") :].strip().replace("\\", "/")
    if not name or "/" in name:
        return ""
    p = os.path.join(UPLOADS_DIR, name)
    if not os.path.isfile(p):
        return ""
    return p


def _auto_generate_seal_result_pdf(req: dict) -> dict:
    """
    按申请中 positions 与当前校章图自动生成盖章后 PDF。
    依赖 PyMuPDF(fitz)；成功后返回 stamped_pdf_url。
    """
    rid = req.get("id")
    p = req.get("params") or {}
    if not isinstance(p, dict):
        p = {}
    src_path = _safe_upload_path_from_url(p.get("pdf_url"))
    if not src_path:
        return {"ok": False, "type": "seal", "id": rid, "message": "原始 PDF 不存在或路径无效"}
    positions = p.get("positions")
    if not isinstance(positions, list) or not positions:
        return {"ok": False, "type": "seal", "id": rid, "message": "缺少盖章位置（positions）"}
    stamp_path, _stamp_url = _seal_stamp_upload_path_and_url()
    if not stamp_path:
        return {"ok": False, "type": "seal", "id": rid, "message": "尚未上传校章图片，请管理员先在校章审核页上传校章图"}

    try:
        import fitz  # PyMuPDF（pip 包名 pymupdf）
    except ImportError as e:
        return {
            "ok": False,
            "type": "seal",
            "id": rid,
            "message": (
                "当前运行服务的 Python 未安装 PyMuPDF。请用「与启动本服务相同的」解释器执行："
                "python -m pip install pymupdf（勿混用系统 python 与 venv）。"
                f" 导入错误: {e}"
            ),
        }
    except Exception as e:
        return {
            "ok": False,
            "type": "seal",
            "id": rid,
            "message": (
                "PyMuPDF 已安装但加载失败（常见于 DLL/运行库缺失、32/64 位与 Python 不一致）。"
                f" 详情: {e}"
            ),
        }

    out_name = _seal_result_filename(int(rid or 0))
    out_path = os.path.join(UPLOADS_DIR, out_name)
    doc = None
    try:
        doc = fitz.open(src_path)
        if doc.page_count < 1:
            return {"ok": False, "type": "seal", "id": rid, "message": "原始 PDF 页数异常"}
        page = doc.load_page(0)
        page_h = float(page.rect.height)

        # 以 72pt 为基准边长，按图片长宽比缩放
        pix = fitz.Pixmap(stamp_path)
        iw = float(max(1, pix.width))
        ih = float(max(1, pix.height))
        pix = None
        base = 72.0
        if iw >= ih:
            sw = base
            sh = base * (ih / iw)
        else:
            sh = base
            sw = base * (iw / ih)

        placed = 0
        for it in positions:
            if not isinstance(it, dict):
                continue
            try:
                x = float(it.get("x"))
                y = float(it.get("y"))
            except (TypeError, ValueError):
                continue
            # 前端 y 为 PDF 底部坐标系；fitz 以左上为原点
            left = x
            top = page_h - y - sh
            rect = fitz.Rect(left, top, left + sw, top + sh)
            page.insert_image(rect, filename=stamp_path, keep_proportion=True, overlay=True)
            placed += 1

        if placed < 1:
            return {"ok": False, "type": "seal", "id": rid, "message": "positions 无有效坐标，未生成结果文件"}

        doc.save(out_path, garbage=4, deflate=True)
        return {
            "ok": True,
            "type": "seal",
            "id": rid,
            "stamped_pdf_url": f"/uploads/{out_name}",
            "message": f"已自动生成盖章 PDF（共 {placed} 处）",
        }
    except Exception as e:
        return {"ok": False, "type": "seal", "id": rid, "message": f"自动盖章失败：{e}"}
    finally:
        if doc is not None:
            try:
                doc.close()
            except Exception:
                pass


@app.route('/api/admin-gate-status', methods=['GET'])
def api_admin_gate_status():
    """是否启用管理中心口令（由 .env 的 ADMIN_GATE_CODE 是否非空决定）。"""
    return jsonify({'gate_enabled': bool(_env_get("ADMIN_GATE_CODE", ""))})


@app.route('/api/admin-gate-check', methods=['POST'])
def api_admin_gate_check():
    """
    管理中心 index.html 口令：期望值来自 .env 的 ADMIN_GATE_CODE。
    若未配置 ADMIN_GATE_CODE（空），则返回 skip=true，前端可不拦截（公网请务必配置）。
    """
    data = request.get_json(force=True, silent=True) or {}
    code = (data.get('code') or '').strip()
    expected = _env_get("ADMIN_GATE_CODE", "")
    if not expected:
        web_session.pop("ke_admin_gate_ok", None)
        return jsonify({'ok': True, 'skip': True})
    ok = code == expected
    if ok:
        web_session["ke_admin_gate_ok"] = True
    return jsonify({'ok': ok})


@app.route("/go/quickvote")
def go_quickvote():
    """跳转至原版 QuickVote（民主测评、二维码等）。URL 由 .env 的 QUICKVOTE_PUBLIC_URL 配置。"""
    if not _admin_api_authorized():
        return redirect("/index.html", code=302)
    u = (_env_get("QUICKVOTE_PUBLIC_URL", "http://127.0.0.1:8001").strip() or "http://127.0.0.1:8001")
    return redirect(u, code=302)


@app.route("/go/teacher-data-system")
def go_teacher_data_system():
    """跳转至原版 TeacherDataSystem（教师库、PDF 模板与任务等）。URL 由 .env 的 TEACHERDATA_PUBLIC_URL 配置。"""
    if not _admin_api_authorized():
        return redirect("/index.html", code=302)
    u = (_env_get("TEACHERDATA_PUBLIC_URL", "http://127.0.0.1:8002").strip() or "http://127.0.0.1:8002")
    return redirect(u, code=302)


@app.route("/go/teacher-questionnaire")
def go_teacher_questionnaire():
    """
    教师问卷入口（主站统一入口）。
    默认跳到 TeacherDataSystem 的教师看板；可在 .env 配置 TEACHERDATA_QUESTIONNAIRE_PATH 覆盖路径。
    """
    base = (_env_get("TEACHERDATA_PUBLIC_URL", "http://127.0.0.1:8002").strip() or "http://127.0.0.1:8002").rstrip("/") + "/"
    p = (_env_get("TEACHERDATA_QUESTIONNAIRE_PATH", "/teacher/dashboard").strip() or "/teacher/dashboard")
    if not p.startswith("/"):
        p = "/" + p
    u = urljoin(base, p.lstrip("/"))
    return redirect(u, code=302)


def _teacherdata_base_url() -> str:
    return ((_env_get("TEACHERDATA_PUBLIC_URL", "http://127.0.0.1:8002").strip() or "http://127.0.0.1:8002")).rstrip("/")


def _teacherdata_root_dir() -> str:
    r = (_env_get("TEACHERDATA_ROOT", "").strip())
    if r:
        if os.path.isabs(r):
            return r
        return os.path.join(BASE_DIR, r)
    return os.path.join(BASE_DIR, "vendor", "TeacherDataSystem")


def _teacherdata_db_path() -> str:
    return os.path.join(_teacherdata_root_dir(), "teacher_data.db")


def _teacherdata_login(id_number: str, phone: str) -> dict:
    if not id_number or not phone:
        return {"ok": False, "msg": "id_number 或 phone 为空"}
    u = _teacherdata_base_url() + "/api/teacher/login"
    try:
        r = requests.post(
            u,
            json={"id_number": id_number, "phone": phone},
            timeout=15,
        )
    except requests.RequestException as e:
        return {"ok": False, "msg": f"TeacherDataSystem 连接失败：{e}"}
    try:
        d = r.json()
    except Exception:
        d = {"detail": (r.text or "")[:300]}
    if r.status_code >= 400:
        return {"ok": False, "msg": str(d.get("detail") or d.get("msg") or r.status_code)}
    token = str(d.get("token") or "").strip()
    tid = d.get("teacher_id")
    if not token or tid is None:
        return {"ok": False, "msg": "TeacherDataSystem 登录返回不完整"}
    return {
        "ok": True,
        "token": token,
        "teacher_id": int(tid),
        "teacher_name": str(d.get("teacher_name") or ""),
    }


def _teacherdata_questionnaires_for_teacher(teacher_id: int) -> list:
    dbp = _teacherdata_db_path()
    if not os.path.isfile(dbp):
        raise FileNotFoundError(f"未找到 TeacherDataSystem 数据库：{dbp}")
    tid = int(teacher_id)
    out = []
    conn = sqlite3.connect(dbp)
    conn.row_factory = sqlite3.Row
    try:
        q_rows = conn.execute("SELECT id, title, description, fields, teacher_ids, status, deadline FROM questionnaires ORDER BY id DESC").fetchall()
        r_rows = conn.execute(
            "SELECT questionnaire_id, answers, status, submitted_at FROM questionnaire_responses WHERE teacher_id=?",
            (tid,),
        ).fetchall()
    finally:
        conn.close()

    resp_map = {}
    for rr in r_rows:
        try:
            ans = json.loads(rr["answers"] or "{}")
        except Exception:
            ans = {}
        resp_map[int(rr["questionnaire_id"])] = {
            "answers": ans if isinstance(ans, dict) else {},
            "status": str(rr["status"] or "pending"),
            "submitted_at": rr["submitted_at"],
        }

    for q in q_rows:
        if str(q["status"] or "") not in ("active", "pending", "open"):
            continue
        try:
            tids = json.loads(q["teacher_ids"] or "[]")
        except Exception:
            tids = []
        ids = []
        if isinstance(tids, list):
            for x in tids:
                try:
                    ids.append(int(x))
                except (TypeError, ValueError):
                    continue
        if tid not in ids:
            continue
        try:
            fields = json.loads(q["fields"] or "[]")
        except Exception:
            fields = []
        out.append({
            "id": int(q["id"]),
            "title": str(q["title"] or ""),
            "description": str(q["description"] or ""),
            "fields": fields if isinstance(fields, list) else [],
            "status": str(q["status"] or ""),
            "deadline": q["deadline"],
            "response": resp_map.get(int(q["id"]), {"answers": {}, "status": "pending", "submitted_at": None}),
        })
    return out


def _norm_phone_tail11(s: str) -> str:
    t = "".join(ch for ch in str(s or "") if ch.isdigit())
    if len(t) >= 11:
        return t[-11:]
    return t


def _teacherdata_resolve_teacher_by_dingtalk_user(me: dict) -> dict:
    """
    从主站钉钉登录信息自动匹配 TeacherDataSystem 教师（优先手机号，其次姓名）。
    成功返回 {id, name, id_number, phone}。
    """
    if not isinstance(me, dict):
        return {"ok": False, "reason": "no_dingtalk_profile", "msg": "缺少钉钉用户资料"}
    mobile_candidates = []
    for k in ("mobile", "telephone", "phone"):
        v = str(me.get(k) or "").strip()
        if v:
            mobile_candidates.append(v)
    mobile_norm_set = {x for x in (_norm_phone_tail11(v) for v in mobile_candidates) if x}

    name_candidates = []
    for k in ("name", "display_name", "nick", "summary"):
        v = str(me.get(k) or "").strip()
        if v:
            name_candidates.append(v)
    if name_candidates and "·" in name_candidates[-1]:
        # summary 形如 “张三 · 13xxxx · 钉钉userId:xxx”
        name_candidates.append(name_candidates[-1].split("·", 1)[0].strip())
    name_set = {n for n in name_candidates if n and not n.startswith("钉钉userId:")}

    dbp = _teacherdata_db_path()
    if not os.path.isfile(dbp):
        return {"ok": False, "reason": "teacher_db_missing", "msg": f"未找到教师库：{dbp}"}
    conn = sqlite3.connect(dbp)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT id, name, id_number, phone FROM teachers").fetchall()
    finally:
        conn.close()
    cand = []
    for r in rows:
        phone = str(r["phone"] or "").strip()
        idn = str(r["id_number"] or "").strip()
        if not phone or not idn:
            continue
        p11 = _norm_phone_tail11(phone)
        by_mobile = bool(p11 and p11 in mobile_norm_set)
        by_name = bool(str(r["name"] or "").strip() in name_set)
        if by_mobile or by_name:
            cand.append({
                "id": int(r["id"]),
                "name": str(r["name"] or ""),
                "id_number": idn,
                "phone": phone,
                "_by_mobile": by_mobile,
                "_by_name": by_name,
            })
    if not cand:
        return {"ok": False, "reason": "no_match", "msg": "未在教师库匹配到该钉钉用户"}
    by_mobile = [x for x in cand if x.get("_by_mobile")]
    if len(by_mobile) == 1:
        r = dict(by_mobile[0])
        r["ok"] = True
        return r
    if len(by_mobile) > 1:
        both = [x for x in by_mobile if x.get("_by_name")]
        if len(both) == 1:
            r = dict(both[0])
            r["ok"] = True
            return r
        return {
            "ok": False,
            "reason": "mobile_multi_match",
            "msg": "手机号在教师库匹配到多条记录，无法自动确定",
            "candidates": [{"id": x.get("id"), "name": x.get("name")} for x in by_mobile[:8]],
        }
    # 无手机号命中时，仅姓名唯一才接受
    by_name = [x for x in cand if x.get("_by_name")]
    if len(by_name) == 1:
        r = dict(by_name[0])
        r["ok"] = True
        return r
    if len(by_name) > 1:
        return {
            "ok": False,
            "reason": "name_multi_match",
            "msg": "姓名在教师库匹配到多条记录，无法自动确定",
            "candidates": [{"id": x.get("id"), "name": x.get("name")} for x in by_name[:8]],
        }
    return {"ok": False, "reason": "no_match", "msg": "未在教师库匹配到该钉钉用户"}


@app.route("/api/teacher-questionnaires/auth", methods=["POST"])
def api_teacher_questionnaires_auth():
    """
    主站问卷入口：教师用身份证+手机号验证后，返回其待填问卷（来自 TeacherDataSystem）。
    """
    data = request.get_json(force=True, silent=True) or {}
    id_number = str(data.get("id_number") or data.get("idNumber") or "").strip()
    phone = str(data.get("phone") or "").strip()
    lg = _teacherdata_login(id_number, phone)
    if not lg.get("ok"):
        return jsonify({"ok": False, "msg": lg.get("msg") or "身份验证失败"}), 401

    try:
        out = _teacherdata_questionnaires_for_teacher(int(lg["teacher_id"]))
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500

    return jsonify({
        "ok": True,
        "teacher_id": int(lg["teacher_id"]),
        "teacher_name": lg.get("teacher_name") or "",
        "questionnaires": out,
    })


@app.route("/api/teacher-questionnaires/auto-auth", methods=["GET"])
def api_teacher_questionnaires_auto_auth():
    """
    主站登录态自动匹配教师问卷身份：优先按钉钉手机号，辅以姓名；匹配成功则直接返回问卷列表。
    """
    me = web_session.get("dt_user")
    if not me:
        return jsonify({"ok": False, "need_login": True, "msg": "need_dingtalk_login"}), 401
    t = _teacherdata_resolve_teacher_by_dingtalk_user(me)
    if not t.get("ok"):
        return jsonify({
            "ok": False,
            "need_manual_auth": True,
            "reason": t.get("reason") or "no_match",
            "msg": t.get("msg") or "未能自动匹配教师，请手动填写身份证号和手机号",
            "candidates": t.get("candidates") or [],
        }), 404
    lg = _teacherdata_login(str(t.get("id_number") or ""), str(t.get("phone") or ""))
    if not lg.get("ok"):
        return jsonify({"ok": False, "need_manual_auth": True, "msg": lg.get("msg") or "自动登录失败"}), 401
    try:
        out = _teacherdata_questionnaires_for_teacher(int(lg["teacher_id"]))
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500
    return jsonify({
        "ok": True,
        "auto": True,
        "teacher_id": int(lg["teacher_id"]),
        "teacher_name": lg.get("teacher_name") or t.get("name") or "",
        "auth_prefill": {"id_number": str(t.get("id_number") or ""), "phone": str(t.get("phone") or "")},
        "questionnaires": out,
    })


@app.route("/api/teacher-questionnaires/submit", methods=["POST"])
def api_teacher_questionnaires_submit():
    """
    主站代 TeacherDataSystem 提交问卷：身份证+手机号校验后提交 answers。
    """
    data = request.get_json(force=True, silent=True) or {}
    id_number = str(data.get("id_number") or data.get("idNumber") or "").strip()
    phone = str(data.get("phone") or "").strip()
    qid_raw = data.get("questionnaire_id") or data.get("questionnaireId")
    answers = data.get("answers") if isinstance(data.get("answers"), dict) else {}
    try:
        qid = int(qid_raw)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "msg": "questionnaire_id 非法"}), 400
    lg = _teacherdata_login(id_number, phone)
    if not lg.get("ok"):
        return jsonify({"ok": False, "msg": lg.get("msg") or "身份验证失败"}), 401

    u = _teacherdata_base_url() + "/api/questionnaires/responses"
    payload = {
        "questionnaire_id": qid,
        "teacher_id": int(lg["teacher_id"]),
        "answers": answers,
    }
    headers = {
        "content-type": "application/json",
        "X-Teacher-Token": str(lg["token"]),
    }
    try:
        r = requests.post(u, json=payload, headers=headers, timeout=20)
    except requests.RequestException as e:
        return jsonify({"ok": False, "msg": f"提交失败：{e}"}), 502
    try:
        d = r.json()
    except Exception:
        d = {"detail": (r.text or "")[:400]}
    if r.status_code >= 400:
        return jsonify({"ok": False, "msg": str(d.get("detail") or d.get("msg") or r.status_code), "raw": d}), r.status_code
    return jsonify({"ok": True, "data": d})


@app.route('/api/request-parse', methods=['POST'])
def api_request_parse():
    """Parse teacher natural language into {type, params} for approval queue."""
    data = request.get_json(force=True, silent=True) or {}
    text = (data.get('text') or '').strip()
    if not text:
        return jsonify({'ok': False, 'msg': 'text 为空'}), 400

    from datetime import date, timedelta

    _ex_today = date.today()
    _ex_end20 = (_ex_today + timedelta(days=20)).isoformat()
    _ex_today_s = _ex_today.isoformat()
    schema_hint = {
        "type": "add_vehicle",
        "params": {
            "name": "张三",
            "plate_no": "浙A9X000",
            "plate_type": "1",
            "start_date": _ex_today_s,
            "end_date": (_ex_today + timedelta(days=365)).isoformat(),
            "remark": ""
        },
        "notes": ""
    }
    leave_cycle_hint = {
        "type": "leave_cycle",
        "params": {
            "grade": "1",
            "students": ["李四", "王五"],
            "weekday": 1,
            "week": "1,2,3,4,5",
            "lesson_hint": "晚三",
            "timestart": "20:50",
            "timeend": "21:40",
            "time_start": _ex_today_s,
            "time_end": _ex_end20,
            "reason": ""
        },
        "notes": ""
    }
    sys = (
        "你是学校信息化助手。任务：把教师的一句话需求解析成“申请类型 + 参数”，用于进入审批队列。\n"
        "只输出 JSON，不要额外文字。字段固定：\n"
        "- type: 申请类型，枚举：add_vehicle（添加车牌）、leave_cycle（周期请假）、reset_net_password（重置网络密码）\n"
        "- params: 对应类型的参数对象\n"
        "- notes: 不确定/缺失信息提示（可空字符串）\n"
        "\n"
        "规则：\n"
        "1) 车牌：识别姓名、车牌号、长期/临时；若“开一年/半年/几个月”等 → plate_type=1 并推算 start_date/end_date（YYYY-MM-DD），否则 plate_type=0。\n"
        "2) 周期请假：students 为学生姓名数组；"
        "grade 为智慧校园「关联年级」在页面地址中的数字（…/add/grade/【此处】/…），与下拉所选年级一致，"
        "各校编码不同，切勿默认 高一=1、高二=2、高三=3；无法从原文确定时可省略，由用户在确认表单填写。\n"
        "weekday 为 1-7（周一=1…周日=7）。若涉及多个固定星期（如「周一到周五每天」），"
        "务必增加字段 week，值为英文逗号分隔数字，如 \"1,2,3,4,5\"（与平台一致），weekday 可填其中第一天；"
        "time_start、time_end 为请假日期范围 YYYY-MM-DD（“今天”请用当天日期，不要写汉字）；若写“每天/天天”且未给结束日，time_end 宜设为起算日起约 30 天，并在 notes 提醒教师在确认界面可改日期；"
        "timestart、timeend 必须为当天作息时段的 24小时制 HH:MM（例如晚三=20:50-21:40、下午第三节=15:15-15:55），"
        "严禁把“今天/明天”等日期词填入 timestart/timeend；课节口语放入 lesson_hint（如 晚三、下午第2节）。\n"
        "3) 重置网络密码：识别 userName/userId 以及新密码。\n"
        f"参考结构（车牌）：{json.dumps(schema_hint, ensure_ascii=False)}\n"
        f"参考结构（周期请假）：{json.dumps(leave_cycle_hint, ensure_ascii=False)}"
    )
    user = f"请解析：{text}"
    try:
        content = _call_siliconflow_chat(
            messages=[{"role": "system", "content": sys}, {"role": "user", "content": user}],
            max_tokens=600,
            temperature=0
        )
        parsed = json.loads(content)
        t = str(parsed.get("type") or "").strip()
        if t not in ("add_vehicle", "leave_cycle", "reset_net_password", "seal"):
            return jsonify({'ok': False, 'msg': f'type 非法: {t}', 'raw': content}), 400
        params = parsed.get("params") or {}
        if not isinstance(params, dict):
            return jsonify({'ok': False, 'msg': 'params 必须是对象', 'raw': content}), 400
        notes = str(parsed.get("notes") or "")
        if t == "leave_cycle":
            params = _enrich_leave_cycle_params_from_original_text(text, params)
            bits = [notes] if notes else []
            if params.get("timestart") and params.get("timeend"):
                bits.append(
                    f"时段已按温科高作息表校对为 {params['timestart']}–{params['timeend']}（可在表单中修改）。"
                )
            elif re.search(r"晚|自修|自习|第\s*[一二三四五六七八九十\d]\s*节|下午|上午|早读", text):
                bits.append("未能根据原文自动匹配到标准作息时段，请手工填写开始/结束时刻（HH:MM）。")
            notes = " ".join(x for x in bits if x).strip()
        out = {"type": t, "params": params, "notes": notes}
        return jsonify({'ok': True, 'data': out, 'raw': content})
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)}), 500


def _requester_snapshot_for_queue():
    """入队时写入库的发起人快照（钉钉资料 + 提交时刻 + 客户端信息，供管理员核对）。"""
    base = web_session.get("dt_user")
    if not isinstance(base, dict):
        base = {}
    snap = dict(base)
    snap["submitted_at"] = _now_iso()
    xff = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    snap["client_ip"] = xff or (request.remote_addr or "")
    snap["user_agent"] = (request.headers.get("User-Agent") or "")[:400]
    return snap


@app.route('/api/requests', methods=['POST'])
def api_create_request():
    me = web_session.get("dt_user")
    if not me:
        return jsonify({'ok': False, 'need_login': True, 'msg': 'need_dingtalk_login'}), 401
    data = request.get_json(force=True, silent=True) or {}
    t = str(data.get("type") or "").strip()
    params = data.get("params") or {}
    if t not in ("add_vehicle", "leave_cycle", "reset_net_password", "seal"):
        return jsonify({'ok': False, 'msg': 'type 非法'}), 400
    if not isinstance(params, dict):
        return jsonify({'ok': False, 'msg': 'params 必须是对象'}), 400

    requester_snap = _requester_snapshot_for_queue()
    conn = _db()
    try:
        cur = conn.execute(
            "INSERT INTO requests(type, params_json, requester_json, status, created_at) VALUES(?,?,?,?,?)",
            (t, json.dumps(params, ensure_ascii=False), json.dumps(requester_snap, ensure_ascii=False), "pending", _now_iso())
        )
        conn.commit()
        rid = cur.lastrowid
    finally:
        conn.close()
    return jsonify({'ok': True, 'id': rid})


@app.route('/api/seal-request', methods=['POST'])
def api_seal_request():
    """
    校章申请：上传PDF + 位置点，直接写入审批队列（type=seal）。
    """
    me = web_session.get("dt_user")
    if not me:
        return jsonify({'ok': False, 'need_login': True, 'msg': 'need_dingtalk_login'}), 401
    if 'pdf' not in request.files:
        return jsonify({'ok': False, 'msg': '缺少 pdf 文件'}), 400
    f = request.files['pdf']
    if not f or not f.filename:
        return jsonify({'ok': False, 'msg': 'pdf 文件名为空'}), 400
    name = str(f.filename).lower()
    if not name.endswith('.pdf'):
        return jsonify({'ok': False, 'msg': '只支持 PDF'}), 400

    positions_raw = (request.form.get('positions') or '').strip()
    remark = (request.form.get('remark') or '').strip()
    if not positions_raw:
        return jsonify({'ok': False, 'msg': 'positions 为空'}), 400
    try:
        positions = json.loads(positions_raw)
        if not isinstance(positions, list) or len(positions) == 0:
            return jsonify({'ok': False, 'msg': 'positions 必须是非空数组'}), 400
    except Exception as e:
        return jsonify({'ok': False, 'msg': 'positions JSON 解析失败: ' + str(e)}), 400

    # save file
    fn = f"seal_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex}.pdf"
    save_path = os.path.join(UPLOADS_DIR, fn)
    f.save(save_path)

    params = {
        "pdf_url": f"/uploads/{fn}",
        "positions": positions,
        "remark": remark,
    }
    requester_snap = _requester_snapshot_for_queue()
    conn = _db()
    try:
        cur = conn.execute(
            "INSERT INTO requests(type, params_json, requester_json, status, created_at) VALUES(?,?,?,?,?)",
            ("seal", json.dumps(params, ensure_ascii=False), json.dumps(requester_snap, ensure_ascii=False), "pending", _now_iso())
        )
        conn.commit()
        rid = cur.lastrowid
    finally:
        conn.close()
    return jsonify({'ok': True, 'id': rid})


@app.route('/api/admin/requests', methods=['GET'])
def api_admin_list_requests():
    if not _admin_api_authorized():
        return _admin_api_denied_response()
    status = (request.args.get('status') or '').strip()
    conn = _db()
    try:
        if status:
            rows = conn.execute("SELECT * FROM requests WHERE status=? ORDER BY id DESC LIMIT 200", (status,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM requests ORDER BY id DESC LIMIT 200").fetchall()
        return jsonify([_row_to_req(r) for r in rows])
    finally:
        conn.close()


@app.route('/api/my-requests', methods=['GET'])
def api_my_requests():
    """
    仅返回“当前登录用户”的近 200 条申请，用于教师页展示“入队后结果”。
    由于请求发起人信息存入 requester_json（钉钉资料快照），这里在服务端做过滤。
    """
    me = web_session.get("dt_user")
    if not me:
        return jsonify({'ok': False, 'need_login': True, 'msg': 'need_dingtalk_login'}), 401
    if not _me_has_dingtalk_identity(me):
        return jsonify({
            'ok': False,
            'msg': '当前登录信息缺少钉钉用户标识，无法筛选「我的申请」。请在钉钉内重新打开本页并完成登录。',
        }), 403

    conn = _db()
    try:
        rows = conn.execute("SELECT * FROM requests ORDER BY id DESC LIMIT 200").fetchall()
    finally:
        conn.close()

    out = []
    for row in rows:
        try:
            requester = json.loads(row["requester_json"] or "null")
        except Exception:
            requester = None
        if not isinstance(requester, dict):
            continue
        # 仅返回与当前登录者为同一钉钉身份的记录（userId / openId / unionId 任一一致）
        if _same_dingtalk_identity(me, requester):
            out.append(_row_to_req(row))

    return jsonify({'ok': True, 'data': out})


@app.route('/api/admin/requests/<int:rid>', methods=['GET'])
def api_admin_get_request(rid: int):
    if not _admin_api_authorized():
        return _admin_api_denied_response()
    conn = _db()
    try:
        row = conn.execute("SELECT * FROM requests WHERE id=?", (rid,)).fetchone()
        if not row:
            return jsonify({'ok': False, 'msg': 'not found'}), 404
        return jsonify({'ok': True, 'data': _row_to_req(row)})
    finally:
        conn.close()


@app.route('/api/admin/requests/<int:rid>/review', methods=['POST'])
def api_admin_review_request(rid: int):
    if not _admin_api_authorized():
        return _admin_api_denied_response()
    data = request.get_json(force=True, silent=True) or {}
    st = str(data.get('status') or '').strip()
    comment = str(data.get('comment') or '').strip()
    if st not in ('approved', 'rejected'):
        return jsonify({'ok': False, 'msg': 'status 只能是 approved/rejected'}), 400
    conn = _db()
    try:
        row = conn.execute("SELECT * FROM requests WHERE id=?", (rid,)).fetchone()
        if not row:
            return jsonify({'ok': False, 'msg': 'not found'}), 404
        reviewed_at = _now_iso()
        exec_obj = None
        if st == "approved":
            req_obj = _row_to_req(row)
            exec_obj = _execute_approved_queue_item(req_obj)
            if str(req_obj.get("type") or "") == "seal":
                if not isinstance(exec_obj, dict) or not bool(exec_obj.get("ok")):
                    msg = ""
                    if isinstance(exec_obj, dict):
                        msg = str(exec_obj.get("message") or "").strip()
                    return jsonify({'ok': False, 'msg': msg or '校章自动生成结果 PDF 失败，未通过审批'}), 400
            exec_json = json.dumps(exec_obj, ensure_ascii=False, default=str)
            executed_at = _now_iso()
            conn.execute(
                "UPDATE requests SET status=?, reviewed_at=?, review_comment=?, execute_result=?, executed_at=? WHERE id=?",
                (st, reviewed_at, comment, exec_json, executed_at, rid),
            )
        else:
            # 驳回：勿清空已通过时留下的执行记录（若曾误审可人工在库中处理）
            conn.execute(
                "UPDATE requests SET status=?, reviewed_at=?, review_comment=? WHERE id=?",
                (st, reviewed_at, comment, rid),
            )
        conn.commit()
        out = {"ok": True}
        if exec_obj is not None:
            out["execution"] = exec_obj
        return jsonify(out)
    finally:
        conn.close()


def _seal_result_filename(rid: int) -> str:
    return f"seal_result_{rid}.pdf"


@app.route("/api/admin/requests/<int:rid>/seal-result", methods=["POST"])
def api_admin_upload_seal_result(rid: int):
    """管理员上传盖章后的 PDF，保存后教师端可下载。"""
    if not _admin_api_authorized():
        return _admin_api_denied_response()
    f = request.files.get("pdf") or request.files.get("file")
    if not f or not f.filename:
        return jsonify({"ok": False, "msg": "缺少 pdf 文件"}), 400
    name = str(f.filename).lower()
    if not name.endswith(".pdf"):
        return jsonify({"ok": False, "msg": "只支持 PDF"}), 400

    conn = _db()
    try:
        row = conn.execute("SELECT * FROM requests WHERE id=?", (rid,)).fetchone()
        if not row:
            return jsonify({"ok": False, "msg": "not found"}), 404
        if str(row["type"] or "") != "seal":
            return jsonify({"ok": False, "msg": "仅支持 seal 类型"}), 400

        fn = _seal_result_filename(rid)
        save_path = os.path.join(UPLOADS_DIR, fn)
        try:
            f.save(save_path)
        except OSError as e:
            return jsonify({"ok": False, "msg": str(e)}), 500

        # 合并/写入 execute_result：保留既有字段，追加 stamped_pdf_url
        keys = list(row.keys())
        exec_raw = row["execute_result"] if "execute_result" in keys else None
        try:
            exec_obj = json.loads(exec_raw) if exec_raw else {}
        except Exception:
            exec_obj = {}
        if not isinstance(exec_obj, dict):
            exec_obj = {}
        exec_obj["stamped_pdf_url"] = f"/uploads/{fn}"
        # 对 seal 来说 executed_at 表示“结果文件已更新”的时间也合理
        executed_at = _now_iso()
        conn.execute(
            "UPDATE requests SET execute_result=?, executed_at=? WHERE id=?",
            (json.dumps(exec_obj, ensure_ascii=False, default=str), executed_at, rid),
        )
        conn.commit()
        return jsonify({"ok": True, "url": exec_obj["stamped_pdf_url"]})
    finally:
        conn.close()


@app.route('/api/admin/requests/<int:rid>/patch-add-vehicle', methods=['POST'])
def api_admin_patch_add_vehicle_request(rid: int):
    """
    管理员在「添加职工车牌」页选好职工后，将 team_uid 等字段回写到审批单 params_json。
    可选 reset_to_pending=1：把已通过（但执行失败）的单重置为待审核，便于重新审批执行。
    """
    if not _admin_api_authorized():
        return _admin_api_denied_response()
    data = request.get_json(force=True, silent=True) or {}
    conn = _db()
    try:
        row = conn.execute("SELECT * FROM requests WHERE id=?", (rid,)).fetchone()
        if not row:
            return jsonify({"ok": False, "msg": "not found"}), 404
        if str(row["type"] or "") != "add_vehicle":
            return jsonify({"ok": False, "msg": "仅支持 add_vehicle 类型"}), 400

        try:
            params = json.loads(row["params_json"] or "{}")
        except Exception:
            params = {}
        if not isinstance(params, dict):
            params = {}

        # 仅覆盖本次明确传入且非空的字段，避免误清空已有参数
        for k in ("team_uid", "plate_no", "plate_type", "remark", "start_date", "end_date"):
            if k in data:
                v = str(data.get(k) or "").strip()
                if v:
                    params[k] = v

        params_json = json.dumps(params, ensure_ascii=False)
        reset_to_pending = str(data.get("reset_to_pending") or "").strip().lower() in ("1", "true", "yes", "on")
        if reset_to_pending:
            conn.execute(
                "UPDATE requests SET params_json=?, status='pending', reviewed_at=NULL, review_comment=NULL, execute_result=NULL, executed_at=NULL WHERE id=?",
                (params_json, rid),
            )
            msg = "已回写车牌参数，并重置为待审核"
        else:
            conn.execute("UPDATE requests SET params_json=? WHERE id=?", (params_json, rid))
            msg = "已回写车牌参数"
        conn.commit()
        return jsonify({"ok": True, "msg": msg, "data": {"id": rid, "params": params}})
    finally:
        conn.close()


def _get_flask_secret_key():
    # order: env var -> KeAdmin .env -> random per run
    t = (os.environ.get("FLASK_SECRET_KEY") or "").strip()
    if t:
        return t
    env_defaults = _read_env_file(_env_here())
    t = (env_defaults.get("FLASK_SECRET_KEY") or "").strip()
    if t and t.lower() != "change-me-to-a-random-long-string":
        return t
    return os.urandom(32)


app.secret_key = _get_flask_secret_key()


def _get_chat_server_token() -> str:
    # order: env var -> 本目录 .env -> QUICKFORM_ENV_PATH 指向的 .env（可选）
    t = (os.environ.get('CHAT_SERVER_API_TOKEN') or '').strip()
    if t:
        return t
    t = (_read_env_file(_env_here()).get('CHAT_SERVER_API_TOKEN') or '').strip()
    if t:
        return t
    qf = _env_get("QUICKFORM_ENV_PATH", "")
    if qf and os.path.isfile(qf):
        return (_read_env_file(qf).get('CHAT_SERVER_API_TOKEN') or '').strip()
    return ""

def _get_dingtalk_cfg():
    env_defaults = _read_env_file(_env_here())
    cid = (os.environ.get("DINGTALK_CLIENT_ID") or env_defaults.get("DINGTALK_CLIENT_ID") or "").strip()
    sec = (os.environ.get("DINGTALK_CLIENT_SECRET") or env_defaults.get("DINGTALK_CLIENT_SECRET") or "").strip()
    redirect_uri = (os.environ.get("DINGTALK_REDIRECT_URI") or env_defaults.get("DINGTALK_REDIRECT_URI") or "").strip()
    if not redirect_uri:
        # default to public domain (you said you have one)
        redirect_uri = "https://wzkjgz.site/auth/dingtalk/callback"
    return {"client_id": cid, "client_secret": sec, "redirect_uri": redirect_uri}

def _dingtalk_user_access_token(code: str):
    cfg = _get_dingtalk_cfg()
    if not cfg["client_id"] or not cfg["client_secret"]:
        raise ValueError("missing DINGTALK_CLIENT_ID / DINGTALK_CLIENT_SECRET")
    url = "https://api.dingtalk.com/v1.0/oauth2/userAccessToken"
    payload = {
        "clientId": cfg["client_id"],
        "clientSecret": cfg["client_secret"],
        "code": code,
        "grantType": "authorization_code",
    }
    r = requests.post(url, json=payload, timeout=15)
    if r.status_code != 200:
        raise ValueError(f"dingtalk token http {r.status_code}: {(r.text or '')[:300]}")
    j = r.json()
    # expected: accessToken, expireIn, refreshToken, corpId (optional)
    return j


_DT_APP_TOKEN_CACHE = {"token": "", "expires_at": 0}
_DT_USER_RESOLVE_CACHE = {}

def _dingtalk_app_access_token(force_refresh: bool = False) -> str:
    """
    企业内部应用 access_token（应用级），用于 requestAuthCode 的 code 换取用户身份。
    """
    cfg = _get_dingtalk_cfg()
    if not cfg["client_id"] or not cfg["client_secret"]:
        raise ValueError("missing DINGTALK_CLIENT_ID / DINGTALK_CLIENT_SECRET")
    now = int(time.time())
    if (not force_refresh) and _DT_APP_TOKEN_CACHE["token"] and _DT_APP_TOKEN_CACHE["expires_at"] > now + 30:
        return _DT_APP_TOKEN_CACHE["token"]

    url = "https://api.dingtalk.com/v1.0/oauth2/accessToken"
    payload = {
        "appKey": cfg["client_id"],
        "appSecret": cfg["client_secret"],
    }
    r = requests.post(url, json=payload, timeout=15)
    if r.status_code != 200:
        raise ValueError(f"dingtalk app token http {r.status_code}: {(r.text or '')[:300]}")
    j = r.json() or {}
    token = (j.get("accessToken") or "").strip()
    expires_in = int(j.get("expireIn") or 7200)
    if not token:
        raise ValueError("dingtalk app token missing accessToken")
    _DT_APP_TOKEN_CACHE["token"] = token
    _DT_APP_TOKEN_CACHE["expires_at"] = now + max(expires_in, 300)
    return token


def _dingtalk_h5_userinfo_by_code(auth_code: str) -> dict:
    """
    钉钉工作台 H5：requestAuthCode(code) -> user/getuserinfo（企业内部应用流程）
    """
    app_token = _dingtalk_app_access_token()
    url = "https://oapi.dingtalk.com/user/getuserinfo"
    r = requests.get(url, params={"access_token": app_token, "code": auth_code}, timeout=15)
    if r.status_code != 200:
        raise ValueError(f"dingtalk getuserinfo http {r.status_code}: {(r.text or '')[:300]}")
    j = r.json() or {}
    err = j.get("errcode")
    if err not in (0, "0", None):
        # 常见：40078（code无效/过期/非本应用签发）
        raise ValueError(f"dingtalk getuserinfo errcode={j.get('errcode')} errmsg={j.get('errmsg')}")
    uid = str(j.get("userid") or j.get("userId") or "").strip()
    if not uid:
        raise ValueError("dingtalk getuserinfo missing userid")
    prof = {
        "userId": uid,
        "display_name": str(j.get("name") or uid),
        "summary": "钉钉userId:" + uid,
    }
    return prof


def _dingtalk_user_profile_by_userid(user_id: str) -> dict:
    """
    通过钉钉企业内部应用 access_token + userId 查询用户资料（姓名/手机号等）。
    需要通讯录读取权限；无权限时返回仅含 userId 的最小结构。
    """
    uid = str(user_id or "").strip()
    if not uid:
        return {}

    now = int(time.time())
    c = _DT_USER_RESOLVE_CACHE.get(uid)
    if isinstance(c, dict) and int(c.get("expires_at") or 0) > now + 10:
        return dict(c.get("profile") or {})

    try:
        app_token = _dingtalk_app_access_token()
        # 企业内部应用按 userId 查人：topapi/v2/user/get
        url = "https://oapi.dingtalk.com/topapi/v2/user/get"
        r = requests.post(
            url,
            params={"access_token": app_token},
            json={"userid": uid, "language": "zh_CN"},
            timeout=15,
        )
        j = r.json() if r.status_code == 200 else {}
        if str(j.get("errcode")) in ("0", "None", ""):
            res = j.get("result") if isinstance(j.get("result"), dict) else {}
            p = {
                "userId": uid,
                "name": str(res.get("name") or "").strip(),
                "mobile": str(res.get("mobile") or "").strip(),
                "title": str(res.get("title") or "").strip(),
            }
            p["display_name"] = p["name"] or ("钉钉userId:" + uid)
            p["summary"] = p["name"] or ("钉钉userId:" + uid)
            _DT_USER_RESOLVE_CACHE[uid] = {"expires_at": now + 300, "profile": p}
            return p
    except Exception:
        pass

    p = {"userId": uid, "display_name": "钉钉userId:" + uid, "summary": "钉钉userId:" + uid}
    _DT_USER_RESOLVE_CACHE[uid] = {"expires_at": now + 120, "profile": p}
    return p

def _dingtalk_me(access_token: str):
    url = "https://api.dingtalk.com/v1.0/contact/users/me"
    headers = {"x-acs-dingtalk-access-token": access_token}
    r = requests.get(url, headers=headers, timeout=15)
    if r.status_code != 200:
        raise ValueError(f"dingtalk me http {r.status_code}: {(r.text or '')[:300]}")
    return r.json()


def _dingtalk_normalize_profile(me: dict) -> dict:
    """
    从钉钉「获取用户通讯录个人信息」接口响应中抽取可展示、可审计字段。
    实际能拿到哪些字段取决于开放平台权限与 OAuth scope（默认仅 openid 时可能只有基础 id）。
    可在 .env 设置 DINGTALK_OAUTH_SCOPE，例如：openid Contact.User.Read
    """
    if not isinstance(me, dict):
        return {}
    scalar_keys = (
        "userId", "userid", "unionId", "unionid", "openId", "open_id",
        "nick", "name", "avatarUrl", "avatar",
        "mobile", "telephone", "email", "orgEmail", "org_email",
        "title", "jobNumber", "job_number", "workPlace", "remark", "stateCode",
        "hiredDate", "active", "admin", "leader", "exclusiveAccount",
    )
    out = {}
    for k in scalar_keys:
        if k not in me:
            continue
        v = me.get(k)
        if v is None or v == "":
            continue
        if isinstance(v, (str, int, float, bool)):
            out[k] = v
    uid = str(out.get("userId") or out.get("userid") or "").strip()
    if uid:
        out["userId"] = uid
    out.pop("userid", None)
    uni = str(out.get("unionId") or out.get("unionid") or "").strip()
    if uni:
        out["unionId"] = uni
    out.pop("unionid", None)
    oid = str(out.get("openId") or out.get("open_id") or "").strip()
    if oid:
        out["openId"] = oid
    out.pop("open_id", None)
    if out.get("avatar") and not out.get("avatarUrl"):
        out["avatarUrl"] = out.get("avatar")
    out.pop("avatar", None)

    dl = me.get("deptIdList") or me.get("deptIds")
    if isinstance(dl, list) and dl:
        out["deptIdList"] = [str(x) for x in dl[:40]]

    display = (
        str(out.get("name") or out.get("nick") or me.get("name") or me.get("nick") or "").strip() or "-"
    )
    out["display_name"] = display
    bits = [display]
    if out.get("mobile"):
        bits.append(str(out["mobile"]))
    if out.get("title"):
        bits.append(str(out["title"]))
    if out.get("userId"):
        bits.append("钉钉userId:" + str(out["userId"]))
    out["summary"] = " · ".join(bits)
    return out


@app.route("/api/me", methods=["GET"])
def api_me():
    u = web_session.get("dt_user")
    if not u:
        return jsonify({"ok": True, "logged_in": False, "user": None})
    return jsonify({"ok": True, "logged_in": True, "user": u})


@app.route("/api/admin/dingtalk-users/resolve", methods=["POST"])
def api_admin_dingtalk_users_resolve():
    """
    管理员页按 userId 批量补全姓名展示（避免只显示“钉钉userId:xxxx”）。
    """
    if not _admin_api_authorized():
        return _admin_api_denied_response()
    data = request.get_json(force=True, silent=True) or {}
    arr = data.get("user_ids") if isinstance(data.get("user_ids"), list) else []
    ids = []
    seen = set()
    for x in arr:
        uid = str(x or "").strip()
        if not uid or uid in seen:
            continue
        seen.add(uid)
        ids.append(uid)
        if len(ids) >= 100:
            break
    out = {}
    for uid in ids:
        out[uid] = _dingtalk_user_profile_by_userid(uid)
    return jsonify({"ok": True, "data": out})


@app.route("/api/dingtalk/web-config", methods=["GET"])
def api_dingtalk_web_config():
    """
    前端判断：是否展示「钉钉内登录」（H5 微应用 JSAPI）。
    需 DINGTALK_USE_H5_JSAPI=1 且配置 DINGTALK_CORP_ID。
    """
    corp = _env_get("DINGTALK_CORP_ID", "")
    use_h5 = str(_env_get("DINGTALK_USE_H5_JSAPI", "")).lower() in ("1", "true", "yes", "on")
    dc = _get_dingtalk_cfg()
    return jsonify({
        "corp_id": corp or None,
        "h5_jsapi_enabled": bool(use_h5 and corp.strip()),
        "browser_oauth_enabled": bool((dc.get("client_id") or "").strip()),
    })


def _dingtalk_put_user_session(tok: dict, me: dict, login_via: str):
    prof = _dingtalk_normalize_profile(me)
    prof["provider"] = "dingtalk"
    prof["corpId"] = (tok.get("corpId") or "") or _env_get("DINGTALK_CORP_ID", "")
    prof["login_at"] = _now_iso()
    prof["login_via"] = login_via
    web_session["dt_user"] = prof


@app.route("/api/dingtalk/h5-auth", methods=["POST"])
def api_dingtalk_h5_auth():
    """
    钉钉客户端内 H5 微应用：JSAPI requestAuthCode 拿到的临时码，在此换用户并写入 session。
    与 H5 微应用同一套 DINGTALK_CLIENT_ID / DINGTALK_CLIENT_SECRET。
    """
    data = request.get_json(force=True, silent=True) or {}
    code = (data.get("authCode") or data.get("code") or "").strip()
    if not code:
        return jsonify({"ok": False, "msg": "missing authCode"}), 400
    try:
        me = _dingtalk_h5_userinfo_by_code(code)
        _dingtalk_put_user_session({"corpId": _env_get("DINGTALK_CORP_ID", "")}, me, "h5_jsapi")
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@app.route("/auth/dingtalk/login", methods=["GET"])
def auth_dingtalk_login():
    return (
        "Browser OAuth is disabled. Please open this app inside DingTalk Workbench and use H5 login.",
        410,
    )

@app.route("/auth/dingtalk/callback", methods=["GET"])
def auth_dingtalk_callback():
    return (
        "Browser OAuth callback is disabled. Please return to DingTalk Workbench and use H5 login.",
        410,
    )

@app.route("/auth/logout", methods=["GET"])
def auth_logout():
    web_session.pop("dt_user", None)
    web_session.pop("dt_oauth_state", None)
    web_session.pop("dt_next", None)
    web_session.pop("ke_admin_gate_ok", None)
    return redirect("/teacher.html")


def _call_siliconflow_chat(messages, model='deepseek-ai/DeepSeek-V2.5', max_tokens=1024, temperature=0):
    api_key = _get_chat_server_token()
    if not api_key:
        raise ValueError('CHAT_SERVER_API_TOKEN not configured')
    url = 'https://api.siliconflow.cn/v1/chat/completions'
    headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {api_key}'}
    payload = {
        'model': model,
        'messages': messages,
        'max_tokens': max_tokens,
        'temperature': temperature,
        'response_format': {'type': 'json_object'},
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=(10, 120))
    if resp.status_code != 200:
        detail = (resp.text or '').strip()[:300]
        raise ValueError(f'LLM HTTP {resp.status_code}: {detail}')
    data = resp.json()
    content = (((data.get('choices') or [{}])[0].get('message') or {}).get('content') or '').strip()
    if not content:
        raise ValueError('LLM empty response')
    return content


def _wzkgz_2025s1_resolve_leave_times(weekday, text: str, lesson_hint: str):
    """
    温科高 2025 学年第一学期作息时间表（2025-08-24 起）。
    用规则把「课节口语」落到 timestart/timeend，避免 LLM 用错通用默认值（尤其晚自习）。
    weekday: 1=周一 … 7=周日；未知则按非周一处理（早读/第一节等周一特例不生效）。
    """
    try:
        wd = int(weekday)
        if wd < 1 or wd > 7:
            wd = None
    except (TypeError, ValueError):
        wd = None

    chunks = []
    if text:
        chunks.append(str(text))
    if lesson_hint:
        chunks.append(str(lesson_hint))
    s = "".join(chunks).replace(" ", "").replace("　", "").strip()
    if not s:
        return None

    def _mon(mon_range, other_range):
        return mon_range if wd == 1 else other_range

    # ---------- 晚自习（优先匹配，避免「第三节」歧义）----------
    evening_rules = [
        (
            r"晚(?:自修|自习)?\s*3|晚三|晚自习\s*3|晚自习第三|晚自习第\s*3\s*节|晚自习第三节|晚自修第三|第三节晚|晚\s*3\s*节|第三(?:节)?晚自习",
            ("20:50", "21:40", "晚自修3"),
        ),
        (
            r"晚(?:自修|自习)?\s*2|晚二|晚自习\s*2|晚自习第二|晚自习第\s*2\s*节|晚自修第二|晚\s*2\s*节|第二(?:节)?晚自习",
            ("19:20", "20:30", "晚自修2"),
        ),
        (
            r"晚(?:自修|自习)?\s*1|晚一|晚自习\s*1|晚自习第一|晚自习第\s*1\s*节|晚自修第一|晚\s*1\s*节|第一(?:节)?晚自习",
            ("17:50", "19:10", "晚自修1"),
        ),
    ]
    for pat, triple in evening_rules:
        if re.search(pat, s):
            return triple

    # ---------- 下午第 n 节（口语「下午第三节」= 第八节课）----------
    pm_map = {
        "一": ("13:30", "14:10", "第六节"),
        "1": ("13:30", "14:10", "第六节"),
        "二": ("14:25", "15:05", "第七节"),
        "2": ("14:25", "15:05", "第七节"),
        "三": ("15:15", "15:55", "第八节"),
        "3": ("15:15", "15:55", "第八节"),
        "四": ("16:05", "16:45", "第九节/课外活动"),
        "4": ("16:05", "16:45", "第九节/课外活动"),
    }
    m = re.search(r"下午第?\s*([一二三四1234])\s*节", s)
    if m:
        key = m.group(1)
        if key in pm_map:
            return pm_map[key]

    # ---------- 全天序号节次（第六节…第九节）----------
    full_rules = [
        (r"第\s*6\s*节|第六节", ("13:30", "14:10", "第六节")),
        (r"第\s*7\s*节|第七节", ("14:25", "15:05", "第七节")),
        (r"第\s*8\s*节|第八节", ("15:15", "15:55", "第八节")),
        (r"第\s*9\s*节|第九节|课外活动", ("16:05", "16:45", "第九节")),
    ]
    for pat, triple in full_rules:
        if re.search(pat, s):
            return triple

    # ---------- 上午 / 早读（周一第一节、早自修时间不同）----------
    if re.search(r"早自修|早读|晨读", s):
        ts, te = _mon(("06:50", "07:10"), ("06:50", "07:20"))
        return ts, te, "早自修" + ("(周一)" if wd == 1 else "")

    if re.search(r"上午第?\s*一\s*节|上午第?\s*1\s*节", s):
        ts, te = _mon(("07:20", "08:00"), ("07:30", "08:10"))
        return ts, te, "第一节" + ("(周一)" if wd == 1 else "")

    if re.search(r"大课间|周一晨会|晨会", s):
        ts, te = _mon(("08:00", "08:35"), ("08:10", "08:35"))
        return ts, te, "大课间/晨会" + ("(周一)" if wd == 1 else "")

    am_rules = [
        (r"上午第?\s*二\s*节|上午第?\s*2\s*节", ("08:35", "09:15", "第二节")),
        (r"上午第?\s*三\s*节|上午第?\s*3\s*节", ("09:25", "10:05", "第三节")),
        (r"眼保健操", ("10:15", "10:20", "眼保健操")),
        (r"上午第?\s*四\s*节|上午第?\s*4\s*节", ("10:20", "11:00", "第四节")),
        (r"上午第?\s*五\s*节|上午第?\s*5\s*节", ("11:15", "11:55", "第五节(默认高一结束时间，高三/高二略不同)")),
    ]
    for pat, triple in am_rules:
        if re.search(pat, s):
            return triple

    return None


def _leave_nlp_apply_wzkgz_timetable(parsed: dict, original_text: str):
    """若命中本校课表规则，覆盖 time，并在 notes 中标注。"""
    if not isinstance(parsed, dict):
        return parsed
    wd = parsed.get("weekday")
    hint = str(parsed.get("lesson_hint") or "")
    hit = _wzkgz_2025s1_resolve_leave_times(wd, original_text, hint)
    if not hit:
        return parsed
    ts, te, label = hit
    t = parsed.get("time")
    if not isinstance(t, dict):
        t = {}
    t["timestart"] = ts
    t["timeend"] = te
    parsed["time"] = t
    note = str(parsed.get("notes") or "").strip()
    extra = f"课节时间已按温科高2025学年第一学期作息表校对：{label} → {ts}-{te}。"
    parsed["notes"] = (note + " " + extra).strip() if note else extra
    return parsed


def _infer_leave_weekday_from_text(text: str):
    """从自然语言中推断 weekday 1-7（周一=1…周日=7），无法可靠推断时返回 None。"""
    from datetime import date, timedelta
    if not text:
        return None
    t = str(text).replace(" ", "").replace("　", "")
    today = date.today()
    if re.search(r"今天|当日|今晚", t):
        return today.weekday() + 1
    if re.search(r"明天", t):
        return (today + timedelta(days=1)).weekday() + 1
    if re.search(r"后天", t):
        return (today + timedelta(days=2)).weekday() + 1
    if re.search(r"昨天|昨日", t):
        return (today + timedelta(days=-1)).weekday() + 1
    for k, v in [
        ("周一", 1), ("周二", 2), ("周三", 3), ("周四", 4), ("周五", 5), ("周六", 6), ("周日", 7), ("周天", 7), ("星期日", 7),
    ]:
        if k in t:
            return v
    m = re.search(r"星期([一二三四五六日天])", t)
    if m:
        mp = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "日": 7, "天": 7}
        return mp.get(m.group(1))
    return None


def _leave_params_resolve_dates_from_text(text: str, params: dict) -> None:
    """根据「今天/明天」等为周期请假填充 time_start/time_end（YYYY-MM-DD），原地修改 params。"""
    from datetime import date, timedelta
    if not text or not isinstance(params, dict):
        return
    t = str(text).replace(" ", "").replace("　", "")
    today = date.today()
    d0 = None
    if re.search(r"今天|当日", t):
        d0 = today
    elif re.search(r"明天", t):
        d0 = today + timedelta(days=1)
    elif re.search(r"后天", t):
        d0 = today + timedelta(days=2)
    elif re.search(r"昨天|昨日", t):
        d0 = today + timedelta(days=-1)
    if d0 is None:
        return
    iso = d0.isoformat()
    vague = {"", "今天", "明天", "后天", "昨日", "昨天", "当日", "本周", "这周", "下周"}
    ts = str(params.get("time_start") or params.get("timeStart") or "").strip()
    te = str(params.get("time_end") or params.get("timeEnd") or "").strip()
    if not ts or ts in vague:
        params["time_start"] = iso
    if not te or te in vague:
        params["time_end"] = iso


def _enrich_leave_cycle_params_from_original_text(original_text: str, params: dict) -> dict:
    """
    快速申请 /api/request-parse 入队用的周期请假参数：用原文 + 本校作息表补全 timestart/timeend，
    避免模型把「今天」等日期词误填入作息时段字段。
    """
    if not isinstance(params, dict):
        return params
    text = (original_text or "").strip()
    params = dict(params)

    stu = params.get("students")
    if isinstance(stu, str) and stu.strip():
        params["students"] = [x.strip() for x in re.split(r"[;；,，\s\n]+", stu) if x.strip()]

    inferred_multi = _infer_weekday_numbers_from_leave_text(text)
    if inferred_multi:
        params["week"] = ",".join(str(x) for x in inferred_multi)

    wd = None
    if inferred_multi:
        wd = inferred_multi[0]
    wd_llm = params.get("weekday")
    if wd_llm is None:
        wd_llm = params.get("week")
    if wd is None:
        try:
            if wd_llm is not None and str(wd_llm).strip().isdigit():
                n = int(str(wd_llm).strip())
                if 1 <= n <= 7:
                    wd = n
        except (TypeError, ValueError):
            wd = None
        if wd is None:
            wd = _infer_leave_weekday_from_text(text)
    if wd is not None:
        params["weekday"] = wd

    vague_te = re.compile(r"^(今天|明天|后天|昨日|昨天|当日|本周|这周|下周)$")

    blob_parts = [text]
    for k in ("timestart", "timeend", "lesson_hint", "reason", "notes"):
        v = params.get(k)
        if v:
            blob_parts.append(str(v))
    t_obj = params.get("time")
    if isinstance(t_obj, dict):
        blob_parts.append(str(t_obj.get("timestart") or ""))
        blob_parts.append(str(t_obj.get("timeend") or ""))
    blob = " ".join(blob_parts)
    lesson_hint = str(params.get("lesson_hint") or "")

    hit = _wzkgz_2025s1_resolve_leave_times(wd, blob, lesson_hint)
    if hit:
        ts, te, label = hit
        params["timestart"] = ts
        params["timeend"] = te
        if not str(params.get("lesson_hint") or "").strip():
            params["lesson_hint"] = label

    t_obj2 = params.get("time")
    if isinstance(t_obj2, dict):
        for fld in ("timestart", "timeend"):
            cur = str(params.get(fld) or "").strip()
            tv = str(t_obj2.get(fld) or "").strip()
            if tv and ":" in tv and (not cur or bool(vague_te.match(cur))):
                params[fld] = tv

    _leave_params_resolve_dates_from_text(text, params)

    for key in ("timestart", "timeend"):
        v = str(params.get(key) or "").strip()
        if vague_te.match(v):
            params.pop(key, None)

    if isinstance(params.get("time"), dict):
        params.pop("time", None)

    _sanitize_leave_cycle_dates(params, text)

    return params


def _enrich_leave_nlp_for_cycle_form(text: str, parsed: dict) -> dict:
    """管理中心 /api/leave-nlp：从原文推断多星期、默认/纠正日期范围，供前端周期请假表单使用。"""
    from datetime import date, timedelta

    if not isinstance(parsed, dict):
        return parsed
    inferred = _infer_weekday_numbers_from_leave_text(text)
    if inferred:
        parsed["week"] = ",".join(str(x) for x in inferred)
        parsed["weekday"] = inferred[0]
    today = date.today()
    ts = str(parsed.get("time_start") or parsed.get("timeStart") or "").strip()
    te = str(parsed.get("time_end") or parsed.get("timeEnd") or "").strip()
    shim = {"time_start": ts, "time_end": te, "week": parsed.get("week")}
    if not shim["time_start"]:
        shim["time_start"] = today.isoformat()
    if not shim["time_end"]:
        ds = date.fromisoformat(shim["time_start"])
        shim["time_end"] = (ds + timedelta(days=20)).isoformat()
    _sanitize_leave_cycle_dates(shim, text)
    parsed["time_start"] = shim.get("time_start")
    parsed["time_end"] = shim.get("time_end")
    return parsed


@app.route('/api/leave-nlp', methods=['POST'])
def api_leave_nlp():
    data = request.get_json(force=True, silent=True) or {}
    text = (data.get('text') or '').strip()
    if not text:
        return jsonify({'ok': False, 'msg': 'text 为空'}), 400

    from datetime import date, timedelta

    _nlp_ex0 = date.today().isoformat()
    _nlp_ex1 = (date.today() + timedelta(days=20)).isoformat()
    # Provide context and strict schema for JSON output
    schema_hint = {
        "students": ["姓名1", "姓名2"],
        "weekday": 1,
        "week": "1,2,3,4,5",
        "time_start": _nlp_ex0,
        "time_end": _nlp_ex1,
        "time": {"timestart": "15:15", "timeend": "15:55"},
        "lesson_hint": "下午第三节/晚三/早读等原话（可空）",
        "reason": "请假原因（可空）",
        "notes": "解析依据/不确定点（可空）"
    }
    timetable_block = (
        "【温科高 2025 学年第一学期作息 — 课节对应时间段（提交请假用）】\n"
        "早自修：周一 06:50-07:10，其它日 06:50-07:20\n"
        "第一节：周一 07:20-08:00，其它日 07:30-08:10\n"
        "大课间/周一晨会：周一 08:00-08:35，其它日 08:10-08:35\n"
        "第二节 08:35-09:15；第三节 09:25-10:05；眼保健操 10:15-10:20；第四节 10:20-11:00\n"
        "第五节（年级错峰结束）：高三 11:05-11:45，高二 11:10-11:50，高一 11:15-11:55（不确定年级时用高一）\n"
        "第六节(下午第一节) 13:30-14:10；眼保健操 14:20-14:25\n"
        "第七节(下午第二节) 14:25-15:05；第八节(下午第三节) 15:15-15:55\n"
        "第九节/课外活动(下午第四节) 16:05-16:45\n"
        "晚自修1 17:50-19:10；晚自修2 19:20-20:30；晚自修3 20:50-21:40\n"
        "口语「下午第1节」=第六节，「下午第2节」=第七节，「下午第3节」=第八节，「下午第4节」=第九节。\n"
    )
    sys = (
        "你是学校教务助理。任务：把老师口述的请假描述解析成结构化字段，用于“周期请假”表单自动填充。\n"
        "学校：温科高。请严格按下方作息表填写 time（24小时制 HH:MM），不要沿用过时默认值。\n"
        + timetable_block +
        "\n请只输出 JSON（不要额外文字），必须符合以下字段：\n"
        "- students: 学生姓名数组（去重，按出现顺序）\n"
        "- weekday: 1-7（周一=1…周日=7）。若文本含“周三/星期三”则为3。\n"
        "- week: 可选。多个固定星期时用英文逗号分隔，如「周一到周五每天」→ \"1,2,3,4,5\"；单天可省略（仅用 weekday）。\n"
        "- time_start、time_end: 可选，周期起止日期 YYYY-MM-DD；未说明时模型可省略（服务端会按「今天」起算并校正）。\n"
        "- time: {timestart,timeend}，必须与上面作息表一致。\n"
        "- lesson_hint: 保留原话（如“晚三”“下午第三节”），便于人工核对。\n"
        "- reason: 若文本中出现原因就提取，否则空字符串。\n"
        "- notes: 不确定/缺失信息提示（例如未说明年级时的第五节）。\n"
        f"参考 JSON 结构示例：{json.dumps(schema_hint, ensure_ascii=False)}"
    )
    user = f"请解析这段话：{text}"
    try:
        content = _call_siliconflow_chat(
            messages=[{"role": "system", "content": sys}, {"role": "user", "content": user}],
            max_tokens=800,
            temperature=0
        )
        # Ensure valid JSON
        parsed = json.loads(content)
        parsed = _leave_nlp_apply_wzkgz_timetable(parsed, text)
        parsed = _enrich_leave_nlp_for_cycle_form(text, parsed)
        return jsonify({'ok': True, 'data': parsed, 'raw': content})
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)}), 500


def _parse_duration_to_dates(duration_text: str):
    """将「一年」「半年」「三个月」「一个月」等转为 (start_date, end_date) YYYY-MM-DD。从今天起算。"""
    from datetime import date, timedelta
    if not duration_text or not isinstance(duration_text, str):
        return None, None
    s = duration_text.strip()
    today = date.today()
    days = 0
    num_map = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10, '两': 2}
    if '年' in s:
        if '半' in s:
            days = 182
        else:
            n = 1
            for i, c in enumerate(s):
                if c in num_map:
                    n = num_map[c]
                    break
                if c.isdigit():
                    j = i
                    while j < len(s) and s[j].isdigit():
                        j += 1
                    n = int(s[i:j]) if j > i else 1
                    break
            days = 365 * n
    elif '月' in s:
        if '半' in s:
            days = 15
        else:
            n = 1
            for i, c in enumerate(s):
                if c in num_map:
                    n = num_map[c]
                    break
                if c.isdigit():
                    j = i
                    while j < len(s) and s[j].isdigit():
                        j += 1
                    n = int(s[i:j]) if j > i else 1
                    break
            days = 30 * n
    elif '周' in s or '星期' in s:
        n = 1
        for i, c in enumerate(s):
            if c in num_map:
                n = num_map[c]
                break
            if c.isdigit():
                j = i
                while j < len(s) and s[j].isdigit():
                    j += 1
                n = int(s[i:j]) if j > i else 1
                break
        days = 7 * n
    if days <= 0:
        return None, None
    end = today + timedelta(days=days)
    return today.isoformat(), end.isoformat()


@app.route('/api/vehicle-nlp', methods=['POST'])
def api_vehicle_nlp():
    data = request.get_json(force=True, silent=True) or {}
    text = (data.get('text') or '').strip()
    if not text:
        return jsonify({'ok': False, 'msg': 'text 为空'}), 400

    schema_hint = {
        "name": "张三",
        "plate_no": "浙A9X000",
        "plate_type": "1",
        "remark": "可选备注",
        "duration_text": "一年",
        "notes": "不确定点（可空）"
    }
    sys = (
        "你是学校信息化助手。从老师/同事发来的自然语言中提取车牌管理所需信息。\n"
        "请只输出 JSON（不要额外文字），字段：\n"
        "- name: 姓名（有则填，无则空字符串；如“部门 张三”中取“张三”）\n"
        "- plate_no: 车牌号（保留省份简称，字母大写，如 浙A9X000）\n"
        "- plate_type: \"0\"=长期，\"1\"=临时。若出现“开一年/半年/三个月/临时”等则为 \"1\"，否则 \"0\"\n"
        "- remark: 备注（可选）\n"
        "- duration_text: 仅当为临时时填时长描述，如“一年”“半年”“三个月”“一个月”，否则空字符串\n"
        "- notes: 不确定/缺失信息提示\n"
        "规则：多个人名只取最明确的一个；多个车牌只取一个。\n"
        f"参考示例：{json.dumps(schema_hint, ensure_ascii=False)}"
    )
    user = f"请解析：{text}"
    try:
        content = _call_siliconflow_chat(
            messages=[{"role": "system", "content": sys}, {"role": "user", "content": user}],
            max_tokens=400,
            temperature=0
        )
        parsed = json.loads(content)
        name = str(parsed.get('name') or '').strip()
        plate = str(parsed.get('plate_no') or '').strip()
        plate = plate.replace(' ', '').upper()
        if plate:
            plate = plate.replace('，', '').replace(',', '')
        parsed['name'] = name
        parsed['plate_no'] = plate
        if 'remark' not in parsed or parsed.get('remark') is None:
            parsed['remark'] = ''
        if 'notes' not in parsed or parsed.get('notes') is None:
            parsed['notes'] = ''
        plate_type = str(parsed.get('plate_type') or '0').strip()
        if plate_type not in ('0', '1'):
            plate_type = '1' if (parsed.get('duration_text') or '').strip() else '0'
        parsed['plate_type'] = plate_type
        duration_text = (parsed.get('duration_text') or '').strip()
        if plate_type == '1' and duration_text:
            start_d, end_d = _parse_duration_to_dates(duration_text)
            parsed['start_date'] = start_d or ''
            parsed['end_date'] = end_d or ''
        else:
            parsed['start_date'] = ''
            parsed['end_date'] = ''
        return jsonify({'ok': True, 'data': parsed, 'raw': content})
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)}), 500


@app.after_request
def add_cors(response):
    """允许注入脚本从任意页面跨域 POST 到 /debug-log"""
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response


@app.route('/')
def root():
    """默认入口：教师页面"""
    return send_from_directory(WEB_ROOT, 'teacher.html')


@app.route('/teacher')
def teacher_page():
    """普通教师申请（独立入口）"""
    return send_from_directory(WEB_ROOT, 'teacher.html')


@app.route('/seal')
def seal_page():
    """校章申请（独立入口）"""
    return send_from_directory(WEB_ROOT, 'seal.html')


@app.route('/portal')
def portal_page():
    """门户首页快捷入口"""
    return send_from_directory(WEB_ROOT, 'home.html')


@app.route('/admin')
def admin_page():
    """管理中心快捷入口"""
    return send_from_directory(WEB_ROOT, 'index.html')

def _load_eduyun_cfg():
    """
    Read config from eduyun.php (path in EDU_CFG_PHP).
    Expected keys: team_id, appbase.client_id, appbase.client_secret, appbase.server_url
    """
    global _EDU_CFG
    if _EDU_CFG is not None:
        return _EDU_CFG
    if not EDU_CFG_PHP or not os.path.exists(EDU_CFG_PHP):
        raise FileNotFoundError(
            "Missing Eduyun config: set EDU_CFG_PHP in .env to the full path of eduyun.php"
        )
    txt = open(EDU_CFG_PHP, "r", encoding="utf-8", errors="ignore").read()
    def m(pat):
        mm = re.search(pat, txt)
        return mm.group(1) if mm else ""
    team_id = m(r"'team_id'\s*=>\s*'([^']+)'")
    client_id = m(r"'client_id'\s*=>\s*'([^']+)'")
    client_secret = m(r"'client_secret'\s*=>\s*'([^']+)'")
    server_url = m(r"'server_url'\s*=>\s*'([^']+)'")
    if not (client_id and client_secret and server_url and team_id):
        raise ValueError("Failed to parse eduyun.php (team_id/client_id/client_secret/server_url)")
    _EDU_CFG = {
        "team_id": team_id,
        "client_id": client_id,
        "client_secret": client_secret,
        "server_url": server_url.rstrip("/"),
    }
    return _EDU_CFG

def _eduyun_get_token(force_refresh=False):
    """
    Ported from wwwroot_backup: EduyunService::eduyunToken()
    grant_type=client, sign=md5(concat(sorted(param values)) + client_secret)
    """
    cfg = _load_eduyun_cfg()
    now = int(time.time())
    if (not force_refresh) and _EDU_TOKEN_CACHE["token"] and _EDU_TOKEN_CACHE["expires_at"] > now + 30:
        return _EDU_TOKEN_CACHE["token"]

    params = {
        "client_id": cfg["client_id"],
        "grant_type": "client",
        # must match the callback registered in Eduyun app config (use same as ThinkPHP site)
        "redirect_uri": LEAVE_BASE.rstrip("/") + "/base/platform/eduyun?appname=appbase",
    }
    values = [params[k] for k in sorted(params.keys())]
    values.append(cfg["client_secret"])
    sign = hashlib.md5("".join(values).encode("utf-8")).hexdigest()
    params["sign"] = sign

    r = session.post(
        cfg["server_url"] + "/ssologin/gettoken",
        data=params,
        headers={"content-type": "application/x-www-form-urlencoded;charset=UTF-8", "accept": "application/json, text/plain, */*"},
        timeout=15,
    )
    j = r.json()
    data = j.get("data") or {}
    token = data.get("access_token") or ""
    expires_in = int(data.get("expires_in") or j.get("expires_in") or 0)
    if not token:
        raise ValueError("gettoken failed: " + (j.get("msg") or json.dumps(j, ensure_ascii=False)))
    _EDU_TOKEN_CACHE["token"] = token
    _EDU_TOKEN_CACHE["expires_at"] = now + (expires_in if expires_in > 0 else 3600)
    return token

def _leave_encrypt_payload(usrname: str, passwd: str, vercode: str = '') -> str:
    inner = {'usrname': usrname, 'passwd': passwd}
    if vercode:
        inner['vercode'] = vercode
    raw = json.dumps(inner, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    key = RSA.import_key(LEAVE_PUBLIC_KEY_PEM)
    cipher = PKCS1_v1_5.new(key)
    block = key.size_in_bytes() - 11
    if len(raw) > block:
        raise ValueError('login payload too large for RSA block')
    enc = cipher.encrypt(raw)
    return base64.b64encode(enc).decode('ascii')


def _platform_login(usrname: str, passwd: str, vercode: str = ''):
    """Login to ThinkPHP platform and keep cookies in platform_session."""
    platform_session.get(f'{LEAVE_BASE}/base/login.html', timeout=15)
    data = {
        'encrypt': _leave_encrypt_payload(usrname, passwd, vercode),
        'redirect_url': '',
        'client_id': '',
        'response_type': '',
        'state': '',
    }
    headers = {
        'accept': 'application/json, text/javascript, */*; q=0.01',
        'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'x-requested-with': 'XMLHttpRequest',
    }
    return platform_session.post(f'{LEAVE_BASE}/base/login.html', data=data, headers=headers, timeout=15)


def _get_schoolisover_access_token():
    """
    Fetch /base/synclogin/schoolisover.html and extract iframeUrl, then parse access_token.
    Requires platform_session already logged in with admin permission.
    """
    from urllib.parse import unquote
    r = platform_session.get(f'{LEAVE_BASE}/base/synclogin/schoolisover.html', timeout=20)
    html = r.text or ''
    iframe_url = ''
    for pat in [r'<iframe[^>]+src=["\']([^"\']+)["\']', r'src=["\']([^"\']*access_token[^"\']+)["\']']:
        m = re.search(pat, html, re.I)
        if m:
            iframe_url = m.group(1).replace('&amp;', '&')
            break
    if not iframe_url:
        return '', '', html[:500]
    token = ''
    for name in ['access_token', 'accessToken', 'token']:
        m2 = re.search(r'[?&]' + re.escape(name) + r'=([^&?#]+)', iframe_url, re.I)
        if m2:
            token = unquote(m2.group(1).strip())
            break
    if token and not token.startswith('Bearer '):
        token = 'Bearer ' + token
    return token, iframe_url, html[:500]


def _cloud_dept_children(dept_id: str):
    """Call Eduyun deptAuthChild and return JSON dict (best effort)."""
    cfg = _load_eduyun_cfg()
    edu_base = cfg["server_url"]
    token = _eduyun_get_token()
    url = f'{edu_base}/api/dept/deptAuthChild'
    payload = {
        'type': 'contacts',
        'id': str(dept_id),
        'onlydept': '0',
        'access_token': token,
    }
    headers = {
        'accept': 'application/json, text/plain, */*',
        'content-type': 'application/x-www-form-urlencoded;charset=UTF-8',
        'access_token': token,
        'x-requested-with': 'XMLHttpRequest',
    }
    r = session.post(url, data=payload, headers=headers, timeout=15)
    try:
        j = r.json()
    except Exception:
        j = {'code': r.status_code, 'msg': 'non-json', '_raw_text_head': (r.text or '')[:600]}

    # If requires login, try authorization token extracted from platform.
    try:
        need_login = isinstance(j, dict) and (j.get("code") in (401, 403) or "重新登录" in str(j.get("msg", "")) or "授权已无效" in str(j.get("msg", "")))
        if need_login:
            t, _iframe_url, _preview = _get_schoolisover_access_token()
            if not t:
                return {'code': 403, 'msg': 'need_platform_login', 'hint': '请先完成平台管理员登录后再全局搜索', 'data': []}
            # try with/without Bearer
            t2 = str(t).strip()
            auth_candidates = [t2]
            if t2.lower().startswith('bearer '):
                auth_candidates.append(t2.split(' ', 1)[1].strip())
            else:
                auth_candidates.append('Bearer ' + t2)
            tried = set()
            payload2 = dict(payload)
            payload2.pop('access_token', None)
            for auth in auth_candidates:
                if not auth or auth in tried:
                    continue
                tried.add(auth)
                headers2 = dict(headers)
                headers2.pop('access_token', None)
                headers2['authorization'] = auth
                r2 = session.post(url, data=payload2, headers=headers2, timeout=15)
                try:
                    j2 = r2.json()
                except Exception:
                    j2 = {'code': r2.status_code, 'msg': 'non-json', '_raw_text_head': (r2.text or '')[:600]}
                if r2.status_code != 403:
                    return j2
            return j
    except Exception:
        pass
    return j


@app.route('/api/contacts-search', methods=['POST'])
def api_contacts_search():
    """Global search users by name across dept tree (best effort BFS)."""
    data = request.get_json(force=True, silent=True) or {}
    q = (data.get('q') or '').strip()
    limit = int(data.get('limit') or 30)
    limit = max(1, min(limit, 100))
    if not q:
        return jsonify({'ok': False, 'msg': 'q 为空'}), 400

    # BFS over dept tree using deptAuthChild
    visited = set()
    queue = ['1']
    results = []
    max_nodes = 220  # safety to avoid very long traversal
    nodes = 0

    q_low = q.lower()
    while queue and len(results) < limit and nodes < max_nodes:
        did = queue.pop(0)
        if did in visited:
            continue
        visited.add(did)
        nodes += 1

        j = _cloud_dept_children(did)
        if isinstance(j, dict) and j.get('msg') == 'need_platform_login':
            return jsonify({'ok': False, 'need_platform_login': True, 'msg': 'need_platform_login', 'hint': j.get('hint', '')}), 403
        if not isinstance(j, dict) or j.get('code') != 200:
            continue
        d = j.get('data') or {}
        deptlist = d.get('deptlist') or []
        userlist = d.get('userlist') or []
        path = d.get('path') or []
        path_text = ''
        try:
            if isinstance(path, list) and path:
                path_text = ' / '.join([str(x.get('name') or x.get('title') or '') for x in path if isinstance(x, dict)])
        except Exception:
            path_text = ''

        for dep in deptlist:
            if isinstance(dep, dict) and dep.get('id') is not None:
                queue.append(str(dep.get('id')))
        for u in userlist:
            if not isinstance(u, dict):
                continue
            name = str(u.get('name') or u.get('title') or '').strip()
            uid = u.get('id') or u.get('uid') or u.get('user_id')
            if not name or uid is None:
                continue
            if q_low in name.lower():
                results.append({'id': str(uid), 'name': name, 'path': path_text})
                if len(results) >= limit:
                    break

    return jsonify({'ok': True, 'users': results, 'scanned_depts': nodes})


@app.route('/api/platform-login', methods=['POST'])
def api_platform_login():
    if not LEAVE_BASE:
        return jsonify({'ok': False, 'msg': '未配置智慧校园地址：请在 .env 中设置 LEAVE_BASE'}), 503
    data = request.get_json(force=True, silent=True) or {}
    usrname = (data.get('usrname') or '').strip()
    passwd = (data.get('passwd') or '').strip()
    vercode = (data.get('vercode') or '').strip()
    # If frontend does not input credentials, fall back to KeAdmin/.env
    env_here = os.path.join(os.path.dirname(__file__), '.env')
    env_defaults = _read_env_file(env_here)
    if not usrname:
        usrname = (os.environ.get('PLATFORM_USRNAME') or env_defaults.get('PLATFORM_USRNAME') or '').strip()
    if not passwd:
        passwd = (os.environ.get('PLATFORM_PASSWD') or env_defaults.get('PLATFORM_PASSWD') or '').strip()
    if not usrname or not passwd:
        return jsonify({'ok': False, 'msg': 'usrname/passwd 不能为空（请在前端输入或在 KeAdmin/.env 配置 PLATFORM_USRNAME/PLATFORM_PASSWD）'}), 400
    try:
        resp = _platform_login(usrname, passwd, vercode)
        j = resp.json()
        if j.get('code') == 1 or str(j.get('code')) == '1':
            return jsonify({'ok': True, 'msg': '登录成功', 'url': j.get('url', '')})
        if j.get('data') == 'captcha' or ('验证码' in str(j.get('msg', ''))):
            return jsonify({'ok': False, 'need_captcha': True, 'msg': j.get('msg', '需要验证码')}), 403
        return jsonify({'ok': False, 'msg': j.get('msg', '登录失败'), 'raw': j}), 403
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)}), 500

def _leave_login(sess: requests.Session, vercode: str = ''):
    # establish cookies
    sess.get(f'{LEAVE_BASE}/base/login.html', timeout=15)
    data = {
        'encrypt': _leave_encrypt_payload(LEAVE_USER, LEAVE_PASS, vercode),
        'redirect_url': '',
        'client_id': '',
        'response_type': '',
        'state': '',
    }
    headers = {
        'accept': 'application/json, text/javascript, */*; q=0.01',
        'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'x-requested-with': 'XMLHttpRequest',
    }
    resp = sess.post(f'{LEAVE_BASE}/base/login.html', data=data, headers=headers, timeout=15)
    return resp

def _leave_fetch_token(sess: requests.Session, grade: str, time_change: str):
    url = f'{LEAVE_BASE}/studentwork/teacher.studentleavecycle/add/grade/{grade}/time_change/{time_change}.html'
    resp = sess.get(url, timeout=15)
    html = resp.text or ''
    import re
    m = re.search(r'name=[\"\']__token__[\"\']\\s+value=[\"\']([^\"\']+)[\"\']', html)
    if m:
        return m.group(1)
    m = re.search(r'value=[\"\']([^\"\']+)[\"\']\\s+name=[\"\']__token__[\"\']', html)
    return m.group(1) if m else ''

def _leave_grade_uncertain(primary: str) -> bool:
    """年级未指定时：按高一→高二→高三（见 LEAVE_GRADE_GIDS_TRY）依次尝试。"""
    g = str(primary or "").strip().lower()
    return g in ("", "auto", "*", "不确定", "unknown", "x")


def _leave_grade_gids_try_order(primary: str) -> list:
    """
    学生选择器 POST /base/selector/student 的 gids 必须与平台「关联年级」一致。

    - **年级未指定**（空、auto、* 等）：只按 .env **LEAVE_GRADE_GIDS_TRY** 遍历（默认 1,2,3 表示高一/高二/高三），
      各校可改为 17,18,19 等真实 ID。
    - **已指定年级**：先该 gids，再按 LEAVE_STUDENT_SEARCH_GIDS_FALLBACK 追加尝试（补救）。
    """
    if _leave_grade_uncertain(primary):
        seen = set()
        order = []
        raw = (_env_get("LEAVE_GRADE_GIDS_TRY", "1,2,3") or "1,2,3").replace("，", ",")
        for x in [s.strip() for s in raw.split(",")]:
            if x and x not in seen:
                seen.add(x)
                order.append(x)
        return order or ["1"]
    seen = set()
    order = []
    p = str(primary or "").strip() or "1"
    for x in [p] + [s.strip() for s in (_env_get("LEAVE_STUDENT_SEARCH_GIDS_FALLBACK", "") or "").replace("，", ",").split(",")]:
        if not x or x in seen:
            continue
        seen.add(x)
        order.append(x)
    return order or ["1"]


def _leave_resolve_one_name_with_gids(sess: requests.Session, gids: str, name: str) -> tuple:
    """
    返回 (user_id, system_name, json) ；未找到返回 ("", "", dict)。
    """
    headers = {
        'accept': 'application/json, text/javascript, */*; q=0.01',
        'x-requested-with': 'XMLHttpRequest',
    }
    data = {'gids': str(gids), 'mode': 'username', 'keylist': name}
    resp = sess.post(f'{LEAVE_BASE}/base/selector/student', data=data, headers=headers, timeout=15)
    try:
        j = resp.json()
    except Exception:
        return "", "", {"_parse_error": True, "text": (resp.text or "")[:200]}
    if j.get('keyfail'):
        return "", "", j
    rows = j.get('rows') or {}
    uid = ''
    sys_name = ''
    if isinstance(rows, dict):
        for _cls, students in rows.items():
            if isinstance(students, list) and students:
                uid = str(students[0].get('user_id') or students[0].get('id') or '')
                sys_name = str(students[0].get('user_name') or '')
                break
    return uid, sys_name, j


def _leave_resolve_user_ids(sess: requests.Session, grade: str, names):
    # names: list[str] — gids 与平台「周期请假申请」所选关联年级必须一致，不是简单的「高一=1、高二=2」。
    out = []
    gid_order = _leave_grade_gids_try_order(grade)
    for name in names:
        uid = ""
        sys_name = ""
        used_gid = ""
        last_j = None
        for gid in gid_order:
            uid, sys_name, last_j = _leave_resolve_one_name_with_gids(sess, gid, name)
            if uid:
                used_gid = gid
                break
        if not uid:
            kf = (last_j or {}).get("keyfail") if isinstance(last_j, dict) else None
            raise ValueError(
                f"student not found: {name} (keyfail={kf}); "
                f"tried gids={gid_order}. 请确认「关联年级」与平台地址 …/add/grade/【数字】/ 一致。"
            )
        out.append({
            'name': name,
            'user_id': uid,
            'system_name': sys_name,
            'matched_gid': used_gid,
        })
    return out


# 线上抓包（teacher.studentleavecycle/add.html）常见：固定提交 groupList[0]…groupList[9] 共 10 行，未用行为空字符串。
# 可通过 .env LEAVE_CYCLE_GROUP_SLOTS 调整（1–30）。
def _leave_cycle_group_list_slot_count() -> int:
    try:
        n = int((_env_get("LEAVE_CYCLE_GROUP_SLOTS", "10") or "10").strip())
    except (TypeError, ValueError):
        n = 10
    return max(1, min(n, 30))


def _leave_cycle_submit_core(data: dict):
    """
    与 /api/leave-cycle 相同逻辑，返回 (body_dict, http_status)。

    与智慧校园「周期请假申请」页对齐的批量约定（与 ThinkPHP 表单一致，需与线上页面抓包核对）：
    - 端点：POST {LEAVE_BASE}/studentwork/teacher.studentleavecycle/add.html
    - Content-Type：application/x-www-form-urlencoded
    - 多名学生：cycle_stuids 为多个 user_id 的英文逗号拼接，一次提交即平台理解的「批量学生」。
    - 多天/多时段：同一 POST 内使用多条 groupList[i]，每条含 week(1–7)、timestart、timeend、lessoncode。
      浏览器通常会固定 POST 多行（如 0..9），未勾选行为 week/lessoncode/timestart/timeend 全空；本实现默认补齐到
      LEAVE_CYCLE_GROUP_SLOTS（默认 10），与常见抓包一致。
    - 从课表/节次选择器提交时 lessoncode 可能非空（如 K[week]2w）；纯手填时刻时多为空。请求 JSON 可传 lessoncode
      与平台一致；不传则对有效行填空字符串。
    - 与页面 URL 一致：先 GET …/add/grade/{grade}/time_change/{times|lesson}.html 取 __token__（勿让 time_change 为 undefined）。
    """
    if not LEAVE_BASE or not LEAVE_USER or not LEAVE_PASS:
        return {
            'ok': False,
            'msg': '未配置周期请假：请在 .env 中设置 LEAVE_BASE、LEAVE_USER、LEAVE_PASS',
        }, 503
    # grade：未传键时默认 "1"（兼容旧客户端）；传 "" / auto 等表示不确定 → 按 LEAVE_GRADE_GIDS_TRY 遍历高一/高二/高三
    _gr = data.get("grade")
    if _gr is None:
        grade = "1"
    else:
        grade = str(_gr).strip()

    students_raw = (data.get('students') or '').strip()
    time_start = (data.get('time_start') or '').strip()
    time_end = (data.get('time_end') or '').strip()
    week = str(data.get('week') or '3').strip()
    week_slots = _parse_leave_week_slots(week)
    timestart = (data.get('timestart') or '').strip()
    timeend = (data.get('timeend') or '').strip()
    reason = (data.get('reason') or '').strip()
    cycle_replace = str(data.get('cycle_replace') or '0').strip()
    mode = (data.get('mode') or 'times').strip().lower()
    vercode = (data.get('vercode') or '').strip()
    lessoncode_tpl = str(data.get('lessoncode') or data.get('lesson_code') or '').strip()

    if not students_raw:
        return {'ok': False, 'msg': 'students 为空（用逗号或换行分隔）'}, 400
    if not time_start or not time_end:
        return {'ok': False, 'msg': 'time_start 或 time_end 为空（YYYY-MM-DD）'}, 400
    if not timestart or not timeend:
        return {'ok': False, 'msg': 'timestart 或 timeend 为空（HH:MM）'}, 400
    if not reason:
        return {'ok': False, 'msg': 'reason 不能为空'}, 400

    names = []
    for part in students_raw.replace('\r', '\n').replace('，', ',').split('\n'):
        for x in part.split(','):
            x = x.strip()
            if x:
                names.append(x)
    names = list(dict.fromkeys(names))

    sess = requests.Session()
    try:
        login_resp = _leave_login(sess, vercode=vercode)
        j = login_resp.json()
        if not (j.get('code') == 1 or str(j.get('code')) == '1'):
            msg = j.get('msg', '')
            if j.get('data') == 'captcha' or ('验证码' in str(msg)):
                return {'ok': False, 'need_captcha': True, 'msg': msg or '需要验证码'}, 403
            return {'ok': False, 'msg': msg or '登录失败', 'raw': j}, 403

        resolved = _leave_resolve_user_ids(sess, grade, names)
        gids_found = [x.get("matched_gid") for x in resolved if x.get("matched_gid")]
        uniq_g = set(gids_found)
        if len(uniq_g) > 1:
            raise ValueError(
                "多名学生解析到不同年级 ID：" + ", ".join(sorted(uniq_g)) + "。"
                "自动按高一/高二/高三查找时，同一单内需为同一届；请拆分提交或指定「关联年级」。"
            )
        if _leave_grade_uncertain(grade):
            if not uniq_g:
                raise ValueError("未能确定年级（请检查姓名，或在表单中指定关联年级 ID）。")
            eff_grade = next(iter(uniq_g))
        else:
            eff_grade = str(grade).strip()

        cycle_stuids = ','.join([x['user_id'] for x in resolved])

        time_change = 'lesson' if mode == 'lesson' else 'times'
        token = _leave_fetch_token(sess, eff_grade, time_change)

        slot_n = _leave_cycle_group_list_slot_count()
        form = {
            'grade': eff_grade,
            'time_change': time_change,
            'cycle_replace': cycle_replace,
            'cycle_stuids': cycle_stuids,
            'time_start': time_start,
            'time_end': time_end,
            'reason': reason,
            'leave_school': str(data.get('leave_school') or '0'),
            'id': '',
        }
        for i in range(slot_n):
            if i < len(week_slots):
                wn = week_slots[i]
                form[f'groupList[{i}][week]'] = str(wn)
                form[f'groupList[{i}][lessoncode]'] = lessoncode_tpl
                form[f'groupList[{i}][timestart]'] = timestart
                form[f'groupList[{i}][timeend]'] = timeend
            else:
                form[f'groupList[{i}][week]'] = ''
                form[f'groupList[{i}][lessoncode]'] = ''
                form[f'groupList[{i}][timestart]'] = ''
                form[f'groupList[{i}][timeend]'] = ''
        if token:
            form['__token__'] = token

        headers = {
            'accept': 'application/json, text/javascript, */*; q=0.01',
            'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'x-requested-with': 'XMLHttpRequest',
            'referer': f'{LEAVE_BASE}/studentwork/teacher.studentleavecycle/add/grade/{eff_grade}/time_change/{time_change}.html',
        }
        resp = sess.post(f'{LEAVE_BASE}/studentwork/teacher.studentleavecycle/add.html', data=form, headers=headers, timeout=30)
        return {
            'ok': True,
            'students': resolved,
            'cycle_stuids': cycle_stuids,
            'submit_status': resp.status_code,
            'submit_json': resp.json() if resp.headers.get('content-type', '').startswith('application/json') else None,
            'submit_text': (resp.text or '')[:800],
            # 便于与浏览器 F12 中平台原生表单对照：学生批量条数、星期行数、模式
            'post_summary': {
                'endpoint': 'studentwork/teacher.studentleavecycle/add.html',
                'grade_input': grade,
                'grade_submitted': eff_grade,
                'grade_auto_scan': bool(_leave_grade_uncertain(grade)),
                'time_change': time_change,
                'groupList_slot_count': slot_n,
                'student_count': len(resolved),
                'groupList_rows_filled': len(week_slots),
                'week_slots': week_slots,
                'lessoncode_sent': bool(lessoncode_tpl),
                'form_keys_sample': [
                    'grade',
                    'time_change',
                    'cycle_replace',
                    'cycle_stuids',
                    'time_start',
                    'time_end',
                    'reason',
                    'leave_school',
                    'id',
                ]
                + [f'groupList[{i}][week]' for i in range(min(slot_n, 4))],
            },
        }, 200
    except Exception as e:
        return {'ok': False, 'msg': str(e)}, 500


# ---------- 5. 周期请假（教师端快捷提交） ----------
@app.route('/api/leave-cycle', methods=['POST'])
def api_leave_cycle():
    data = request.get_json(force=True, silent=True) or {}
    body, code = _leave_cycle_submit_core(data)
    return jsonify(body), code


def _cloud_post_add_vehicle(data: dict):
    """
    调用云平台「职工/团队车辆」表单接口（与 /api/add-vehicle 相同）。
    data: plate_no, plate_type, team_uid, remark, start_date, end_date, edu_auth_token(可选)
    返回 (cloud_j, http_status, need_login_payload_or_None)
    need_login_payload_or_None 非空时表示需平台登录，调用方应直接返回该 JSON。
    """
    plate_no = (data.get('plate_no') or '').strip()
    plate_type = str(data.get('plate_type') or '0')
    team_uid = (str(data.get('team_uid') or '')).strip()
    remark = (data.get('remark') or '').strip()
    edu_auth_token = (data.get('edu_auth_token') or '').strip()
    start_date = (data.get('start_date') or '').strip()
    end_date = (data.get('end_date') or '').strip()

    cfg = _load_eduyun_cfg()
    edu_base = cfg["server_url"]
    token = _eduyun_get_token()
    url = f'{edu_base}/api/schoolisover/user/teamvehicle/form'
    payload = {
        'plate_no': plate_no,
        'plate_type': plate_type,
    }
    if team_uid:
        payload['team_uid'] = team_uid
    if remark:
        payload['remark'] = remark
    if plate_type == '1':
        payload['empdate[]'] = [start_date, end_date]
        payload['empsdate'] = start_date
        payload['empedate'] = end_date

    headers = {
        'accept': 'application/json, text/plain, */*',
        'content-type': 'application/x-www-form-urlencoded;charset=UTF-8',
        'access_token': token,
        'x-requested-with': 'XMLHttpRequest',
    }

    payload2 = dict(payload)
    payload2["access_token"] = token
    resp = session.post(url, data=payload2, headers=headers, timeout=15)
    try:
        j = resp.json()
        need_login = isinstance(j, dict) and (j.get("data") == "login" or "重新登录" in str(j.get("msg", "")))
        if need_login and edu_auth_token:
            headers2 = dict(headers)
            headers2.pop("access_token", None)
            headers2["authorization"] = edu_auth_token
            resp = session.post(url, data=payload, headers=headers2, timeout=15)
        elif need_login:
            t, iframe_url, _preview = _get_schoolisover_access_token()
            if t:
                auth_candidates = []
                t2 = str(t).strip()
                if t2:
                    auth_candidates.append(t2)
                    low = t2.lower()
                    if low.startswith('bearer '):
                        auth_candidates.append(t2.split(' ', 1)[1].strip())
                    else:
                        auth_candidates.append('Bearer ' + t2)

                tried = set()
                for auth in auth_candidates:
                    if not auth or auth in tried:
                        continue
                    tried.add(auth)
                    headers3 = {
                        'accept': 'application/json, text/plain, */*',
                        'content-type': 'application/x-www-form-urlencoded;charset=UTF-8',
                        'x-requested-with': 'XMLHttpRequest',
                        'authorization': auth,
                    }
                    resp_try = session.post(url, data=payload, headers=headers3, timeout=15)
                    if resp_try.status_code != 403:
                        resp = resp_try
                        break
            else:
                return None, 403, {
                    'code': 0,
                    'data': 'need_platform_login',
                    'msg': '云平台要求重新登录。请先在本页“平台管理员登录”成功后再添加车牌。',
                    'iframe_url': iframe_url,
                }
    except Exception:
        pass

    try:
        cloud_j = resp.json()
    except Exception:
        cloud_j = {'_raw_text_head': (resp.text or '')[:600]}

    code_val = None
    msg_val = None
    try:
        if isinstance(cloud_j, dict):
            code_val = cloud_j.get('code')
            msg_val = cloud_j.get('msg')
    except Exception:
        pass
    need_debug = resp.status_code >= 400 or (msg_val and code_val is not None and str(code_val) != '200')
    if isinstance(cloud_j, dict) and need_debug:
        payload2_debug = {}
        try:
            if isinstance(payload2, dict):
                payload2_debug = {k: v for k, v in payload2.items() if k != 'access_token'}
        except Exception:
            payload2_debug = {}
        cloud_j['_debug'] = {
            'cloud_status': resp.status_code,
            'cloud_url': url,
            'request_payload_head': json.dumps(payload2_debug, ensure_ascii=False)[:800],
            'cloud_text_head': (resp.text or '')[:300],
        }
    return cloud_j, resp.status_code, None


# ---------- 1. 添加职工车牌 ----------
@app.route('/api/add-vehicle', methods=['POST'])
def api_add_vehicle():
    data = request.get_json(force=True, silent=True) or {}
    plate_no = (data.get('plate_no') or '').strip()
    plate_type = str(data.get('plate_type') or '0')
    team_uid = (str(data.get('team_uid') or '')).strip()
    remark = (data.get('remark') or '').strip()
    start_date = (data.get('start_date') or '').strip()
    end_date = (data.get('end_date') or '').strip()

    if not plate_no:
        return jsonify({'code': 400, 'msg': 'plate_no 不能为空'}), 400
    if plate_type != '1' and not team_uid:
        return jsonify({'code': 400, 'msg': '长期车牌请选择职工'}), 400
    if plate_type == '1' and (not start_date or not end_date):
        return jsonify({'code': 400, 'msg': '临时车牌请填写授权开始、结束日期'}), 400

    cloud_j, sc, need_login = _cloud_post_add_vehicle(data)
    if need_login is not None:
        return jsonify(need_login), sc
    return jsonify(cloud_j), sc


# ---------- 2. 部门/人员选择 ----------
@app.route('/api/deptAuthChild', methods=['POST'])
def api_dept_auth_child():
    data = request.get_json(force=True, silent=True) or {}
    dept_id = str(data.get('id') or '1')

    cfg = _load_eduyun_cfg()
    edu_base = cfg["server_url"]
    token = _eduyun_get_token()
    url = f'{edu_base}/api/dept/deptAuthChild'
    payload = {
        'type': 'contacts',
        'id': dept_id,
        'onlydept': '0',
        'access_token': token,
    }
    headers = {
        'accept': 'application/json, text/plain, */*',
        'content-type': 'application/x-www-form-urlencoded;charset=UTF-8',
        'access_token': token,
        'x-requested-with': 'XMLHttpRequest',
    }

    resp = session.post(url, data=payload, headers=headers, timeout=15)
    try:
        j = resp.json()
        if isinstance(j, dict) and (j.get("code") in (401, 403) or "重新登录" in str(j.get("msg", "")) or "授权已无效" in str(j.get("msg", ""))):
            # try using platform schoolisover user token
            t, _iframe_url, _preview = _get_schoolisover_access_token()
            if t:
                headers2 = dict(headers)
                headers2.pop("access_token", None)
                auth_candidates = []
                t2 = str(t).strip()
                if t2:
                    auth_candidates.append(t2)
                    low = t2.lower()
                    if low.startswith('bearer '):
                        auth_candidates.append(t2.split(' ', 1)[1].strip())
                    else:
                        auth_candidates.append('Bearer ' + t2)

                payload3 = dict(payload)
                payload3.pop("access_token", None)

                tried = set()
                resp_try = None
                for auth in auth_candidates:
                    if not auth or auth in tried:
                        continue
                    tried.add(auth)
                    headers2_try = dict(headers2)
                    headers2_try["authorization"] = auth
                    resp_try = session.post(url, data=payload3, headers=headers2_try, timeout=15)
                    if resp_try.status_code != 403:
                        resp = resp_try
                        break

                if resp_try is None:
                    resp_try = session.post(url, data=payload3, headers=headers2, timeout=15)
                    resp = resp_try

                # best-effort return with debug
                try:
                    cloud_j = resp.json()
                except Exception:
                    cloud_j = {'_raw_text_head': (resp.text or '')[:600]}
                if isinstance(cloud_j, dict) and resp.status_code >= 400:
                    cloud_j['_debug'] = {
                        'cloud_status': resp.status_code,
                        'cloud_url': url,
                        'request_payload_head': json.dumps(payload3, ensure_ascii=False)[:800],
                        'cloud_text_head': (resp.text or '')[:300],
                    }
                return jsonify(cloud_j), resp.status_code
            return jsonify({'code': 403, 'msg': 'need_platform_login', 'hint': '请先在“添加职工车牌”页面完成平台管理员登录后再加载通讯录', 'data': []}), 403
    except Exception:
        pass
    try:
        cloud_j = resp.json()
    except Exception:
        cloud_j = {'_raw_text_head': (resp.text or '')[:600]}
    code_val = None
    msg_val = None
    try:
        if isinstance(cloud_j, dict):
            code_val = cloud_j.get('code')
            msg_val = cloud_j.get('msg')
    except Exception:
        pass
    need_debug = resp.status_code >= 400 or (msg_val and code_val is not None and str(code_val) != '200')
    if isinstance(cloud_j, dict) and need_debug:
        cloud_j['_debug'] = {
            'cloud_status': resp.status_code,
            'cloud_url': url,
            'request_payload_head': json.dumps(payload, ensure_ascii=False)[:800],
            'cloud_text_head': (resp.text or '')[:300],
        }
    return jsonify(cloud_j), resp.status_code


# ---------- 3. 搜索用户（网管平台） ----------
@app.route('/api/search-users', methods=['POST'])
def api_search_users():
    if not _admin_api_authorized():
        return _admin_api_denied_response()
    data = request.get_json(force=True, silent=True) or {}
    campus_base, campus_token = _campus_cfg_from_request(data)
    if not campus_base or not campus_token:
        return jsonify({
            'code': 503,
            'msg': '未配置校园网管接口：请在 .env 中设置 CAMPUS_BASE、CAMPUS_TOKEN（本地调试可设 CAMPUS_ALLOW_CLIENT_OVERRIDE=1 并走请求体覆盖）',
        }), 503
    user_group_id = data.get('userGroupId') or ''
    user_name = (data.get('userName') or '').strip()

    if not user_name:
        return jsonify({'code': 400, 'msg': 'userName 不能为空'}), 400

    url = f'{campus_base}/controller/campus/v1/usermgr/users'
    body = {
        'userGroupId': user_group_id or '00000000-0000-0000-0000-000000000000',
        'quickQuery': False,
        'queryAll': False,
        'pageIndex': 1,
        'pageSize': 20,
        'userName': user_name,
        'flag': False,
    }
    headers = {
        'accept': 'application/json',
        'content-type': 'application/json',
        'x-requested-with': 'XMLHttpRequest',
        'http_x_requested_with': 'XMLHttpRequest',
        'x-uni-crsf-token': campus_token,
        'roarand': campus_token,
    }
    try:
        resp = session.post(url, json=body, headers=headers, timeout=15, verify=_campus_verify_tls())
    except requests.exceptions.SSLError as e:
        return jsonify({
            'code': 502,
            'msg': '校园网管 HTTPS 证书校验失败。若为内网自签证书，请在 .env 设置 CAMPUS_VERIFY_TLS=0 后重试。',
            'detail': str(e),
        }), 502
    except requests.RequestException as e:
        return jsonify({'code': 502, 'msg': f'请求校园网管失败：{e}'}), 502
    try:
        return jsonify(resp.json()), resp.status_code
    except Exception:
        return jsonify({'code': resp.status_code, 'msg': '校园网管返回非 JSON', 'raw': (resp.text or '')[:800]}), resp.status_code


# ---------- 4. 重置网络密码 ----------
@app.route('/api/reset-net-password', methods=['POST'])
def api_reset_net_password():
    if not _admin_api_authorized():
        return _admin_api_denied_response()
    data = request.get_json(force=True, silent=True) or {}
    campus_base, campus_token = _campus_cfg_from_request(data)
    if not campus_base or not campus_token:
        return jsonify({
            'code': 503,
            'msg': '未配置校园网管接口：请在 .env 中设置 CAMPUS_BASE、CAMPUS_TOKEN（本地调试可设 CAMPUS_ALLOW_CLIENT_OVERRIDE=1 并走请求体覆盖）',
        }), 503
    user_id = (data.get('userId') or '').strip()
    user_name = (data.get('userName') or '').strip() or user_id
    password = data.get('password') or ''

    if not user_id or not password:
        return jsonify({'code': 400, 'msg': 'userId 或 password 为空'}), 400

    url = f'{campus_base}/controller/campus/v1/usermgr/userpwd/{user_id}'
    body = {
        'userName': user_name,
        'userId': user_id,
        'password': password,
        'passwordConfirm': password,
    }
    headers = {
        'accept': 'application/json',
        'content-type': 'application/json',
        'x-requested-with': 'XMLHttpRequest',
        'http_x_requested_with': 'XMLHttpRequest',
        'x-uni-crsf-token': campus_token,
        'roarand': campus_token,
    }
    try:
        resp = session.put(url, json=body, headers=headers, timeout=15, verify=_campus_verify_tls())
    except requests.exceptions.SSLError as e:
        return jsonify({
            'code': 502,
            'msg': '校园网管 HTTPS 证书校验失败。若为内网自签证书，请在 .env 设置 CAMPUS_VERIFY_TLS=0 后重试。',
            'detail': str(e),
        }), 502
    except requests.RequestException as e:
        return jsonify({'code': 502, 'msg': f'请求校园网管失败：{e}'}), 502
    try:
        return jsonify(resp.json()), resp.status_code
    except Exception:
        return jsonify({'code': resp.status_code, 'msg': '校园网管返回非 JSON', 'raw': (resp.text or '')[:800]}), resp.status_code


@app.route('/api/schoolisover-token', methods=['GET'])
def api_schoolisover_token():
    """
    在完成平台管理员登录后，从 synclogin/schoolisover 页解析出云平台 access_token，
    供前端填入「云平台 Authorization Token」或排查鉴权问题。
    """
    try:
        t, iframe_url, _ = _get_schoolisover_access_token()
        if not t:
            return jsonify({'ok': False, 'msg': '未获取到 token，请先在本页完成「平台管理员登录」后再试', 'iframe_url': iframe_url}), 404
        return jsonify({'ok': True, 'token': t})
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)}), 500


if __name__ == '__main__':
    _main_port = int(_env_get("PORT", "8000") or "8000")
    _flask_debug = str(_env_get("DEBUG", "0")).strip().lower() in ("1", "true", "yes", "on")
    app.run(host='0.0.0.0', port=_main_port, debug=_flask_debug, threaded=True)
