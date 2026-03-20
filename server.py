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
from urllib.parse import urlencode


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


app = Flask(__name__, static_folder='.', static_url_path='')

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
        conn.commit()
    finally:
        conn.close()

_init_queue_db()

def _now_iso():
    return datetime.utcnow().isoformat() + 'Z'

def _row_to_req(row):
    try:
        params = json.loads(row["params_json"] or "{}")
    except Exception:
        params = {}
    try:
        requester = json.loads(row["requester_json"] or "null")
    except Exception:
        requester = None
    return {
        "id": row["id"],
        "type": row["type"],
        "params": params,
        "requester": requester,
        "status": row["status"],
        "created_at": row["created_at"],
        "reviewed_at": row["reviewed_at"],
        "review_comment": row["review_comment"],
    }


UPLOADS_DIR = os.path.join(os.path.dirname(__file__), 'uploads')
os.makedirs(UPLOADS_DIR, exist_ok=True)

@app.route('/uploads/<path:filename>')
def uploads(filename):
    return send_from_directory(UPLOADS_DIR, filename, as_attachment=False)


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
        return jsonify({'ok': True, 'skip': True})
    return jsonify({'ok': code == expected})


@app.route('/api/request-parse', methods=['POST'])
def api_request_parse():
    """Parse teacher natural language into {type, params} for approval queue."""
    data = request.get_json(force=True, silent=True) or {}
    text = (data.get('text') or '').strip()
    if not text:
        return jsonify({'ok': False, 'msg': 'text 为空'}), 400

    schema_hint = {
        "type": "add_vehicle",
        "params": {
            "name": "林xx",
            "plate_no": "浙CD12345",
            "plate_type": "1",
            "start_date": "2026-03-19",
            "end_date": "2027-03-19",
            "remark": ""
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
        "2) 周期请假：尽量给出 students、week、timestart、timeend、time_start、time_end、reason。\n"
        "3) 重置网络密码：识别 userName/userId 以及新密码。\n"
        f"参考结构：{json.dumps(schema_hint, ensure_ascii=False)}"
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
        out = {"type": t, "params": params, "notes": str(parsed.get("notes") or "")}
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


@app.route('/api/admin/requests/<int:rid>', methods=['GET'])
def api_admin_get_request(rid: int):
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
        conn.execute(
            "UPDATE requests SET status=?, reviewed_at=?, review_comment=? WHERE id=?",
            (st, _now_iso(), comment, rid)
        )
        conn.commit()
        return jsonify({'ok': True})
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
            r"晚(?:自修|自习)?\s*3|晚三|晚自习\s*3|晚自习第三|晚自习第\s*3\s*节|晚自修第三|第三节晚|晚\s*3\s*节|第三(?:节)?晚自习",
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


@app.route('/api/leave-nlp', methods=['POST'])
def api_leave_nlp():
    data = request.get_json(force=True, silent=True) or {}
    text = (data.get('text') or '').strip()
    if not text:
        return jsonify({'ok': False, 'msg': 'text 为空'}), 400

    # Provide context and strict schema for JSON output
    schema_hint = {
        "students": ["姓名1", "姓名2"],
        "weekday": 3,
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
        "name": "周xx",
        "plate_no": "浙C12345",
        "plate_type": "1",
        "remark": "可选备注",
        "duration_text": "一年",
        "notes": "不确定点（可空）"
    }
    sys = (
        "你是学校信息化助手。从老师/同事发来的自然语言中提取车牌管理所需信息。\n"
        "请只输出 JSON（不要额外文字），字段：\n"
        "- name: 姓名（有则填，无则空字符串；如“瓯拳 周秀东”中取“周秀东”）\n"
        "- plate_no: 车牌号（保留省份简称，字母大写，如 浙CDJ9405）\n"
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
    return send_from_directory('.', 'teacher.html')


@app.route('/teacher')
def teacher_page():
    """普通教师申请（独立入口）"""
    return send_from_directory('.', 'teacher.html')


@app.route('/seal')
def seal_page():
    """校章申请（独立入口）"""
    return send_from_directory('.', 'seal.html')

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

def _leave_resolve_user_ids(sess: requests.Session, grade: str, names):
    # names: list[str]
    out = []
    headers = {
        'accept': 'application/json, text/javascript, */*; q=0.01',
        'x-requested-with': 'XMLHttpRequest',
    }
    for name in names:
        data = {'gids': grade, 'mode': 'username', 'keylist': name}
        resp = sess.post(f'{LEAVE_BASE}/base/selector/student', data=data, headers=headers, timeout=15)
        j = resp.json()
        if j.get('keyfail'):
            raise ValueError(f"student not found: {name} (keyfail={j.get('keyfail')})")
        rows = j.get('rows') or {}
        uid = ''
        sys_name = ''
        if isinstance(rows, dict):
            for _cls, students in rows.items():
                if isinstance(students, list) and students:
                    uid = str(students[0].get('user_id') or students[0].get('id') or '')
                    sys_name = str(students[0].get('user_name') or '')
                    break
        if not uid:
            raise ValueError(f"cannot parse user_id for: {name}")
        out.append({'name': name, 'user_id': uid, 'system_name': sys_name})
    return out


# ---------- 5. 周期请假（教师端快捷提交） ----------
@app.route('/api/leave-cycle', methods=['POST'])
def api_leave_cycle():
    if not LEAVE_BASE or not LEAVE_USER or not LEAVE_PASS:
        return jsonify({
            'ok': False,
            'msg': '未配置周期请假：请在 .env 中设置 LEAVE_BASE、LEAVE_USER、LEAVE_PASS',
        }), 503
    data = request.get_json(force=True, silent=True) or {}
    grade = str(data.get('grade') or '1').strip()
    students_raw = (data.get('students') or '').strip()
    time_start = (data.get('time_start') or '').strip()
    time_end = (data.get('time_end') or '').strip()
    week = str(data.get('week') or '3').strip()
    timestart = (data.get('timestart') or '').strip()
    timeend = (data.get('timeend') or '').strip()
    reason = (data.get('reason') or '').strip()
    cycle_replace = str(data.get('cycle_replace') or '0').strip()
    mode = (data.get('mode') or 'times').strip().lower()
    vercode = (data.get('vercode') or '').strip()

    if not students_raw:
        return jsonify({'ok': False, 'msg': 'students 为空（用逗号或换行分隔）'}), 400
    if not time_start or not time_end:
        return jsonify({'ok': False, 'msg': 'time_start 或 time_end 为空（YYYY-MM-DD）'}), 400
    if not timestart or not timeend:
        return jsonify({'ok': False, 'msg': 'timestart 或 timeend 为空（HH:MM）'}), 400
    if not reason:
        return jsonify({'ok': False, 'msg': 'reason 不能为空'}), 400

    # split names by comma / newline
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
                return jsonify({'ok': False, 'need_captcha': True, 'msg': msg or '需要验证码'}), 403
            return jsonify({'ok': False, 'msg': msg or '登录失败', 'raw': j}), 403

        resolved = _leave_resolve_user_ids(sess, grade, names)
        cycle_stuids = ','.join([x['user_id'] for x in resolved])

        time_change = 'lesson' if mode == 'lesson' else 'times'
        token = _leave_fetch_token(sess, grade, time_change)

        form = {
            'grade': grade,
            'time_change': time_change,
            'cycle_replace': cycle_replace,
            'cycle_stuids': cycle_stuids,
            'time_start': time_start,
            'time_end': time_end,
            'reason': reason,
            'leave_school': str(data.get('leave_school') or '0'),
            'id': '',
            'groupList[0][week]': week,
            'groupList[0][lessoncode]': '',
            'groupList[0][timestart]': timestart,
            'groupList[0][timeend]': timeend,
        }
        if token:
            form['__token__'] = token

        headers = {
            'accept': 'application/json, text/javascript, */*; q=0.01',
            'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'x-requested-with': 'XMLHttpRequest',
            'referer': f'{LEAVE_BASE}/studentwork/teacher.studentleavecycle/add/grade/{grade}/time_change/{time_change}.html',
        }
        resp = sess.post(f'{LEAVE_BASE}/studentwork/teacher.studentleavecycle/add.html', data=form, headers=headers, timeout=30)
        return jsonify({
            'ok': True,
            'students': resolved,
            'cycle_stuids': cycle_stuids,
            'submit_status': resp.status_code,
            'submit_json': resp.json() if resp.headers.get('content-type', '').startswith('application/json') else None,
            'submit_text': (resp.text or '')[:800],
        }), 200
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)}), 500


# ---------- 1. 添加职工车牌 ----------
@app.route('/api/add-vehicle', methods=['POST'])
def api_add_vehicle():
    data = request.get_json(force=True, silent=True) or {}
    plate_no = (data.get('plate_no') or '').strip()
    plate_type = str(data.get('plate_type') or '0')
    team_uid = (str(data.get('team_uid') or '')).strip()
    remark = (data.get('remark') or '').strip()
    edu_auth_token = (data.get('edu_auth_token') or '').strip()
    start_date = (data.get('start_date') or '').strip()
    end_date = (data.get('end_date') or '').strip()

    if not plate_no:
        return jsonify({'code': 400, 'msg': 'plate_no 不能为空'}), 400
    # 临时车牌(1)可不填职工；长期(0)必须填
    if plate_type != '1' and not team_uid:
        return jsonify({'code': 400, 'msg': '长期车牌请选择职工'}), 400
    if plate_type == '1' and (not start_date or not end_date):
        return jsonify({'code': 400, 'msg': '临时车牌请填写授权开始、结束日期'}), 400

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
        # Verified by browser cURL:
        # plate_type=1 requires: empdate[]=start&empdate[]=end&empsdate=start&empedate=end
        payload['empdate[]'] = [start_date, end_date]
        payload['empsdate'] = start_date
        payload['empedate'] = end_date

    headers = {
        'accept': 'application/json, text/plain, */*',
        'content-type': 'application/x-www-form-urlencoded;charset=UTF-8',
        # follow wwwroot_backup style: access_token
        'access_token': token,
        'x-requested-with': 'XMLHttpRequest',
    }

    payload2 = dict(payload)
    payload2["access_token"] = token
    resp = session.post(url, data=payload2, headers=headers, timeout=15)
    # if cloud says login required, retry with user authorization token (optional, local-only)
    try:
        j = resp.json()
        need_login = isinstance(j, dict) and (j.get("data") == "login" or "重新登录" in str(j.get("msg", "")))
        if need_login and edu_auth_token:
            headers2 = dict(headers)
            headers2.pop("access_token", None)
            headers2["authorization"] = edu_auth_token
            resp = session.post(url, data=payload, headers=headers2, timeout=15)
        elif need_login:
            # try: get user access_token from platform schoolisover iframe (requires platform_session login)
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
                    # If auth format works, the cloud should not return 403.
                    if resp_try.status_code != 403:
                        resp = resp_try
                        break
            else:
                return jsonify({
                    'code': 0,
                    'data': 'need_platform_login',
                    'msg': '云平台要求重新登录。请先在本页“平台管理员登录”成功后再添加车牌。',
                    'iframe_url': iframe_url,
                }), 403
    except Exception:
        pass
    # Always try to attach debug info for non-2xx responses.
    try:
        cloud_j = resp.json()
    except Exception:
        cloud_j = {'_raw_text_head': (resp.text or '')[:600]}

    # Many cloud APIs return HTTP 200 with {code: 0, msg: '...'} for validation errors.
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
        # Avoid leaking full token; only include short head of response text.
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
    return jsonify(cloud_j), resp.status_code


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
    if not CAMPUS_BASE or not CAMPUS_TOKEN:
        return jsonify({
            'code': 503,
            'msg': '未配置校园网管接口：请在 .env 中设置 CAMPUS_BASE、CAMPUS_TOKEN',
        }), 503
    data = request.get_json(force=True, silent=True) or {}
    user_group_id = data.get('userGroupId') or ''
    user_name = (data.get('userName') or '').strip()

    if not user_name:
        return jsonify({'code': 400, 'msg': 'userName 不能为空'}), 400

    url = f'{CAMPUS_BASE}/controller/campus/v1/usermgr/users'
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
        'x-uni-crsf-token': CAMPUS_TOKEN,
        'roarand': CAMPUS_TOKEN,
    }

    resp = session.post(url, json=body, headers=headers, timeout=15)
    return jsonify(resp.json()), resp.status_code


# ---------- 4. 重置网络密码 ----------
@app.route('/api/reset-net-password', methods=['POST'])
def api_reset_net_password():
    if not CAMPUS_BASE or not CAMPUS_TOKEN:
        return jsonify({
            'code': 503,
            'msg': '未配置校园网管接口：请在 .env 中设置 CAMPUS_BASE、CAMPUS_TOKEN',
        }), 503
    data = request.get_json(force=True, silent=True) or {}
    user_id = (data.get('userId') or '').strip()
    user_name = (data.get('userName') or '').strip() or user_id
    password = data.get('password') or ''

    if not user_id or not password:
        return jsonify({'code': 400, 'msg': 'userId 或 password 为空'}), 400

    url = f'{CAMPUS_BASE}/controller/campus/v1/usermgr/userpwd/{user_id}'
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
        'x-uni-crsf-token': CAMPUS_TOKEN,
        'roarand': CAMPUS_TOKEN,
    }

    resp = session.put(url, json=body, headers=headers, timeout=15)
    return jsonify(resp.json()), resp.status_code


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
    app.run(host='0.0.0.0', port=8000, debug=True)
