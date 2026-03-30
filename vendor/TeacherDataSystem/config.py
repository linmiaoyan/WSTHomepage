"""
系统配置文件
"""
import os
from pathlib import Path

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
ADMIN_PASSWORD = (os.getenv("ADMIN_PASSWORD") or "").strip()

# 大模型配置（如果需要使用）
# LLM_API_KEY = os.getenv("LLM_API_KEY", "")
# LLM_API_URL = os.getenv("LLM_API_URL", "")
# USE_LLM = os.getenv("USE_LLM", "false").lower() == "true"

# QuickJudge（方案B：VL 辅助“选字段”，不做自动定位）
QUICKJUDGE_BASE_URL = os.getenv("QUICKJUDGE_BASE_URL", "http://localhost:5001").rstrip("/")
# QuickJudge 侧要求：files 里的路径需要是它本地可访问的相对目录（见 QuickJudge/app.py 的 _resolve_file_path_to_full）
QUICKJUDGE_ROOT_DIR = (BASE_DIR.parent / "QuickJudge").resolve()
QUICKJUDGE_VL_CROPS_DIR = QUICKJUDGE_ROOT_DIR / "vl_crops"
QUICKJUDGE_VL_CROPS_DIR.mkdir(parents=True, exist_ok=True)

