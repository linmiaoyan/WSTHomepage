"""
系统启动脚本
"""
import logging
import os

import uvicorn

PRODUCTION = os.getenv("PRODUCTION", "0").strip().lower() in ("1", "true", "yes", "on")
HOST = os.getenv("HOST") or os.getenv("TEACHERDATA_HOST") or ("127.0.0.1" if PRODUCTION else "0.0.0.0")
PORT = int(os.getenv("PORT") or os.getenv("TEACHERDATA_PORT") or "5009")
DEBUG = (not PRODUCTION) and os.getenv("DEBUG", "1").strip().lower() in ("1", "true", "yes", "on")
if PRODUCTION:
    logging.getLogger("uvicorn.error").setLevel(logging.ERROR)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=HOST,
        port=PORT,
        reload=DEBUG,
        log_level="error" if PRODUCTION else "info",
    )

