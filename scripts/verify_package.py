from __future__ import annotations

import argparse
import zipfile
from pathlib import Path


REQUIRED_FILES = {
    "__init__.py",
    "controller.py",
    "manifest.json",
    "web/reviewer-strip.css",
    "web/reviewer-strip.js",
    "helper/headless.pyw",
    "helper/voice_service.py",
    "helper/control_server.py",
    "helper/legacy_client.pyw",
}
FORBIDDEN_PARTS = {".venv", "__pycache__"}
FORBIDDEN_SUFFIXES = {".pyc", ".log"}
FORBIDDEN_NAMES = {"voice_notes_log.txt"}


def verify_package(path: Path) -> None:
    if not path.exists():
        raise SystemExit(f"Package does not exist: {path}")

    with zipfile.ZipFile(path) as archive:
        files = {
            name.replace("\\", "/").rstrip("/")
            for name in archive.namelist()
            if not name.endswith("/")
        }

    missing = sorted(REQUIRED_FILES - files)
    if missing:
        raise SystemExit(f"Package is missing required files: {', '.join(missing)}")

    forbidden: list[str] = []
    for name in files:
        parts = set(Path(name).parts)
        if parts & FORBIDDEN_PARTS:
            forbidden.append(name)
        elif Path(name).suffix in FORBIDDEN_SUFFIXES:
            forbidden.append(name)
        elif Path(name).name in FORBIDDEN_NAMES:
            forbidden.append(name)
    if forbidden:
        raise SystemExit(f"Package contains runtime files: {', '.join(sorted(forbidden))}")

    print(f"Verified {path} ({len(files)} files).")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("package", type=Path)
    args = parser.parse_args()
    verify_package(args.package)


if __name__ == "__main__":
    main()
