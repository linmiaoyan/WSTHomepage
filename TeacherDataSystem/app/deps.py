"""
FastAPI 依赖：管理员 / 教师鉴权
"""
from typing import Optional

from fastapi import Request, HTTPException

from app.sessions import verify_admin_session, verify_teacher_session


def require_admin(request: Request) -> None:
    token = request.headers.get("X-Admin-Token") or request.cookies.get("admin_token")
    if not verify_admin_session(token):
        raise HTTPException(status_code=401, detail="需要管理员登录")


def get_admin_token_optional(request: Request) -> Optional[str]:
    return request.headers.get("X-Admin-Token") or request.cookies.get("admin_token")


def require_teacher_id(request: Request) -> int:
    token = request.headers.get("X-Teacher-Token") or request.cookies.get("teacher_token")
    tid = verify_teacher_session(token)
    if not tid:
        raise HTTPException(status_code=401, detail="请先登录教师账号")
    return int(tid)


def assert_admin_or_teacher(request: Request, teacher_id: int) -> None:
    """允许管理员，或已登录且 teacher_id 匹配的教师。"""
    admin_tok = request.headers.get("X-Admin-Token") or request.cookies.get("admin_token")
    if verify_admin_session(admin_tok):
        return
    token = request.headers.get("X-Teacher-Token") or request.cookies.get("teacher_token")
    vid = verify_teacher_session(token)
    if vid is not None and int(vid) == int(teacher_id):
        return
    raise HTTPException(status_code=403, detail="无权以该教师身份提交数据")
