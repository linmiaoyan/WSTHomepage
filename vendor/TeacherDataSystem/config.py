"""
系统配置文件
"""
import os
from pathlib import Path


def _read_env_file(path: Path) -> dict:
    env = {}
    if not path or not path.exists():
        return env
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            s = (line or "").strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    except Exception:
        return env
    return env


def _env_get(key: str, default: str = "") -> str:
    v = (os.getenv(key) or "").strip()
    if v:
        return v
    here = Path(__file__).parent / ".env"
    v = (_read_env_file(here).get(key) or "").strip()
    if v:
        return v
    root = Path(__file__).resolve().parents[2] / ".env"
    return (_read_env_file(root).get(key) or default).strip()

# 项目根目录
BASE_DIR = Path(__file__).parent

# 数据库配置
DATABASE_URL = "sqlite:///./teacher_data.db"

# 文件上传配置
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATE_DIR = UPLOAD_DIR / "templates"
TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
EXPORT_DIR = UPLOAD_DIR / "exports"
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

# 允许的文件类型
ALLOWED_EXTENSIONS = {'.pdf', '.html'}

# 最大文件大小（MB）
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

# HTML文件大小限制（MB）
MAX_HTML_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# 管理员密码：必须通过环境变量 ADMIN_PASSWORD 设置，禁止仓库内默认弱口令
ADMIN_PASSWORD = _env_get("ADMIN_PASSWORD")

# 大模型配置（如果需要使用）
# LLM_API_KEY = os.getenv("LLM_API_KEY", "")
# LLM_API_URL = os.getenv("LLM_API_URL", "")
# USE_LLM = os.getenv("USE_LLM", "false").lower() == "true"

# QuickJudge（方案B：VL 辅助“选字段”，不做自动定位）
QUICKJUDGE_BASE_URL = _env_get("QUICKJUDGE_BASE_URL", "http://localhost:5001").rstrip("/")
# QuickJudge 侧要求：files 里的路径需要是它本地可访问的相对目录（见 QuickJudge/app.py 的 _resolve_file_path_to_full）
QUICKJUDGE_ROOT_DIR = (BASE_DIR.parent / "QuickJudge").resolve()
QUICKJUDGE_VL_CROPS_DIR = QUICKJUDGE_ROOT_DIR / "vl_crops"
QUICKJUDGE_VL_CROPS_DIR.mkdir(parents=True, exist_ok=True)

# 硅基流动视觉模型：用于 PDF 模板“AI 预识别填空位置”
# 复用主站常用的 CHAT_SERVER_API_TOKEN；模型名可按硅基流动实际可用列表调整。
SILICONFLOW_API_KEY = (_env_get("SILICONFLOW_API_KEY") or _env_get("CHAT_SERVER_API_TOKEN")).strip()
SILICONFLOW_API_URL = _env_get("SILICONFLOW_API_URL", "https://api.siliconflow.cn/v1/chat/completions")
TEMPLATE_VISION_MODEL = _env_get("TEMPLATE_VISION_MODEL", "moonshotai/Kimi-VL-A3B-Thinking")
TEMPLATE_VISION_MAX_TOKENS = int(_env_get("TEMPLATE_VISION_MAX_TOKENS", "2048") or "2048")

