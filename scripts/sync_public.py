import os
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"

# 根目录入口页
ROOT_HTML = ["index.html", "home.html", "teacher.html", "seal.html"]
# 前端静态目录
ASSET_DIRS = ["css", "js", "pages"]


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def copy_tree(src: Path, dst: Path) -> None:
    if not src.exists() or not src.is_dir():
        return
    for p in src.rglob("*"):
        rel = p.relative_to(src)
        target = dst / rel
        if p.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            copy_file(p, target)


def main() -> None:
    PUBLIC.mkdir(parents=True, exist_ok=True)

    copied_files = 0
    copied_dirs = 0

    for name in ROOT_HTML:
        src = ROOT / name
        if src.exists() and src.is_file():
            copy_file(src, PUBLIC / name)
            copied_files += 1

    for d in ASSET_DIRS:
        src = ROOT / d
        dst = PUBLIC / d
        if src.exists() and src.is_dir():
            copy_tree(src, dst)
            copied_dirs += 1

    print(f"[ok] public mirror synced: files={copied_files}, dirs={copied_dirs}")


if __name__ == "__main__":
    main()
