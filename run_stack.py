"""Cross-platform START_STACK launcher.

Use PRODUCTION=1 to run Flask apps with waitress and bind services to loopback
by default. Development remains unchanged unless PRODUCTION is set.
"""
import os
import runpy
from pathlib import Path


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    os.environ.setdefault("START_STACK", "1")
    runpy.run_path(str(root / "server.py"), run_name="__main__")
