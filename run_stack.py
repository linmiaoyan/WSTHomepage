"""
一键启动：WSTHompage（server.py）+ 原版 QuickVote（Flask）+ 原版 TeacherDataSystem（FastAPI）。

请将【旧项目备份】中的 QuickVote、TeacherDataSystem 复制到 vendor/ 下，
或在 .env 中设置 QUICKVOTE_ROOT、TEACHERDATA_ROOT 指向备份目录。

依赖：主站已有 Python 环境；另需安装两份子项目的依赖（见 vendor/README.md）。
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent


def _load_dotenv() -> None:
    p = BASE / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def _shutdown(procs: list[tuple[str, subprocess.Popen]]) -> None:
    for name, p in procs:
        if p.poll() is None:
            p.terminate()
            try:
                p.wait(timeout=8)
            except subprocess.TimeoutExpired:
                p.kill()
    sys.exit(0)


def main() -> None:
    _load_dotenv()

    main_port = int(os.environ.get("PORT", "8000") or "8000")
    qv_port = int(os.environ.get("QUICKVOTE_PORT", "8001") or "8001")
    td_port = int(os.environ.get("TEACHERDATA_PORT", "8002") or "8002")

    qv_root = Path(os.environ.get("QUICKVOTE_ROOT", str(BASE / "vendor" / "QuickVote")))
    td_root = Path(os.environ.get("TEACHERDATA_ROOT", str(BASE / "vendor" / "TeacherDataSystem")))

    qv_app = qv_root / "app.py"
    td_main = td_root / "app" / "main.py"

    if not qv_app.is_file():
        print(f"[错误] 找不到 QuickVote：{qv_app}")
        print("请将 【旧项目备份】/QuickVote 复制到 vendor/QuickVote，或设置 QUICKVOTE_ROOT。")
        sys.exit(1)
    if not td_main.is_file():
        print(f"[错误] 找不到 TeacherDataSystem：{td_main}")
        print("请将 【旧项目备份】/TeacherDataSystem 复制到 vendor/TeacherDataSystem，或设置 TEACHERDATA_ROOT。")
        sys.exit(1)

    # 供主站 /go/* 跳转（若 .env 未写公网地址，至少本机可打开）
    os.environ.setdefault("QUICKVOTE_PUBLIC_URL", f"http://127.0.0.1:{qv_port}/")
    os.environ.setdefault("TEACHERDATA_PUBLIC_URL", f"http://127.0.0.1:{td_port}/")
    os.environ["PORT"] = str(main_port)

    exe = sys.executable
    procs: list[tuple[str, subprocess.Popen]] = []

    kw: dict = {}
    if sys.platform == "win32":
        kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]

    env_qv = os.environ.copy()
    env_qv["PORT"] = str(qv_port)

    p_qv = subprocess.Popen([exe, "app.py"], cwd=str(qv_root), env=env_qv, **kw)
    procs.append(("QuickVote", p_qv))

    p_td = subprocess.Popen(
        [exe, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", str(td_port)],
        cwd=str(td_root),
        env=os.environ.copy(),
        **kw,
    )
    procs.append(("TeacherDataSystem", p_td))

    time.sleep(1.2)

    p_main = subprocess.Popen([exe, "server.py"], cwd=str(BASE), env=os.environ.copy(), **kw)
    procs.append(("WSTHompage", p_main))

    def _on_sig(*_a):
        _shutdown(procs)

    signal.signal(signal.SIGINT, _on_sig)
    signal.signal(signal.SIGTERM, _on_sig)

    try:
        code = p_main.wait()
        _shutdown(procs)
        sys.exit(code or 0)
    except KeyboardInterrupt:
        _shutdown(procs)


if __name__ == "__main__":
    main()
