"""
进程内会话（管理员 / 教师 token）。生产环境建议改为 Redis + JWT 等方案。
"""
import secrets
from typing import Dict, Optional, Set

admin_sessions: Set[str] = set()
teacher_sessions: Dict[str, int] = {}  # token -> teacher_id


def verify_admin_session(session_token: Optional[str] = None) -> bool:
    if not session_token:
        return False
    return session_token in admin_sessions


def create_admin_session() -> str:
    token = secrets.token_urlsafe(32)
    admin_sessions.add(token)
    return token


def remove_admin_session(token: str) -> None:
    admin_sessions.discard(token)


def verify_teacher_session(session_token: Optional[str] = None) -> Optional[int]:
    if not session_token:
        return None
    return teacher_sessions.get(session_token)


def create_teacher_session(teacher_id: int) -> str:
    token = secrets.token_urlsafe(32)
    teacher_sessions[token] = teacher_id
    return token


def remove_teacher_session(token: str) -> None:
    teacher_sessions.pop(token, None)
