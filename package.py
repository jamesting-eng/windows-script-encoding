#!/usr/bin/env python3
"""Build a SkillHub-ready zip package for windows-script-encoding.

Usage:  python package.py [--out dist]

What it does:
  1. Validates: manifest.yaml + SKILL.md exist, SKILL.md has frontmatter
     with name/description.
  2. Zips all skill files under a `windows-script-encoding/` prefix (SkillHub
     expects a folder-wrapped package), excluding repo/runtime artifacts.
  3. Writes dist/windows-script-encoding-<version>.zip and prints a manifest.

SkillHub ships the CHINESE dist copy (dist/windows-script-encoding/); the repo
root holds the ENGLISH GitHub source. This builder packages the dist copy.

Zero dependencies (stdlib only). Run from the repo root.
"""
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PKG_NAME = "windows-script-encoding"
VERSION = "1.0.0"
DIST_SRC = ROOT / "dist" / PKG_NAME  # Chinese ShipHub-ready copy

EXCLUDE_NAMES = {
    ".git", ".github", "dist", "__pycache__", "node_modules",
    "package.py",  # build tool itself, not part of the skill
}
EXCLUDE_SUFFIXES = {".log", ".pid", ".pyc", ".zip"}


def validate() -> None:
    manifest = ROOT / "manifest.yaml"
    skill = DIST_SRC / "SKILL.md"
    assert manifest.exists(), "manifest.yaml missing (SkillHub required)"
    assert skill.exists(), f"dist/{PKG_NAME}/SKILL.md missing (run from repo root)"
    text = skill.read_text(encoding="utf-8")
    assert text.startswith("---"), "SKILL.md must start with YAML frontmatter"
    fm = text.split("---", 2)[1]
    assert "name:" in fm, "SKILL.md frontmatter missing name"
    assert "description:" in fm, "SKILL.md frontmatter missing description"


def collect_files() -> list[Path]:
    files = []
    for p in sorted(DIST_SRC.rglob("*")):
        if not p.is_file():
            continue
        if any(part in EXCLUDE_NAMES for part in p.relative_to(DIST_SRC).parts):
            continue
        if p.suffix.lower() in EXCLUDE_SUFFIXES:
            continue
        files.append(p)
    return files


def main() -> int:
    try:
        validate()
    except AssertionError as e:
        print(f"[FAIL] {e}")
        return 1

    out_dir = ROOT / "dist"
    out_dir.mkdir(exist_ok=True)
    out_zip = out_dir / f"{PKG_NAME}-{VERSION}.zip"

    files = collect_files()
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in files:
            arcname = Path(PKG_NAME) / p.relative_to(DIST_SRC)
            zf.write(p, arcname.as_posix())

    print(f"[OK] {out_zip}")
    print(f"     {len(files)} files, prefix '{PKG_NAME}/'")
    for p in files:
        print(f"       - {(Path(PKG_NAME) / p.relative_to(DIST_SRC)).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
