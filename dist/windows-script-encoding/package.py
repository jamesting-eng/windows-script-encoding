#!/usr/bin/env python3
"""Build a SkillHub-ready zip package for windows-script-encoding.

Usage:  python package.py [--verbose]
        python package.py --selftest   # prove gate 1 blames the right field

What it does:
  1. Runs four gates (see validate()) before touching the zip.
  2. Zips all skill files under a `windows-script-encoding/` prefix (SkillHub
     expects a folder-wrapped package), excluding repo/runtime artifacts.
  3. Re-opens the zip it just wrote and checks every member against dist/ byte
     for byte — an [OK] before that check would only describe the writer.
  4. Writes dist/windows-script-encoding-<version>.zip and prints a manifest.
     Older packages left in dist/ by the cloud-sync client are reported as INFO,
     because they are residue, not a packaging defect.

SkillHub ships the CHINESE dist copy (dist/windows-script-encoding/); the repo
root holds the ENGLISH GitHub source. This builder packages the dist copy.

Requires pyyaml for gate 1 (the frontmatter gate). An unavailable parser is a
hard stop, never a reason to skip the check — that is exactly how an invalid
frontmatter ships twice. Set PYTHONPATH to the directory that holds it.

Run from the repo root.
"""
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PKG_NAME = "windows-script-encoding"
VERSION = "1.17.0"
DIST_SRC = ROOT / "dist" / PKG_NAME  # Chinese ShipHub-ready copy

# Gate 1 checks every field against its OWN expected type. A whole-block test
# ("every list item is a string") cannot say anything about a scalar field, so a
# `summary` that had turned into a mapping shipped with the whole suite green —
# the gate only ever spoke about lists. Each entry below is a field the skill
# publishes, and the type SkillHub's readers rely on.
FIELD_TYPES = (
    ("name", str),
    ("slug", str),
    ("version", str),
    ("description", str),
    ("summary", str),
    ("read_when", list),
    ("tags", list),
)

# The one YAML mistake that produces this shape, named in the error so the fixer
# does not have to guess: `summary: Families covered: Windows` is either a hard
# parse error or, with the value on the next line, a dict where a string was
# promised.
COLON_SPACE_HINT = (
    " (an ASCII colon-space inside an unquoted scalar turns it into a mapping — "
    "use a dash, or quote the whole value)"
)

# Gate 2 thresholds. Measured: the Chinese copy runs ~90% CJK lines, the English
# root ~1%. Wide margins so a legitimate bilingual example never trips it.
CJK_RATIO_MIN_DIST = 0.30
CJK_LINES_MIN_DIST = 20
CJK_RATIO_MAX_ROOT = 0.15

EXCLUDE_NAMES = {
    ".git", ".github", "dist", "__pycache__", "node_modules",
    "package.py",  # build tool itself, not part of the skill
}
EXCLUDE_SUFFIXES = {".log", ".pid", ".pyc", ".zip", ".bak"}

CJK_RANGE = ("\u4e00", "\u9fff")


def _frontmatter_from_text(text: str) -> str:
    assert text.startswith("---"), "must start with YAML frontmatter"
    parts = text.split("---", 2)
    assert len(parts) >= 3, "frontmatter is not closed by a second ---"
    return parts[1]


def _frontmatter(path: Path) -> str:
    return _frontmatter_from_text(path.read_text(encoding="utf-8"))


def _blame_line(fm_text: str, exc: Exception) -> str:
    """Name the field on the line the parser choked on, when it can be found.

    A plain `ScannerError` reports a line and a column and nothing else, which
    is exactly the "the error points somewhere else" problem: the reader knows
    something is wrong at line 6 but not that the field is `summary`.
    """
    mark = getattr(exc, "problem_mark", None)
    if mark is None:
        return ""
    lines = fm_text.splitlines()
    if not 0 <= mark.line < len(lines):
        return ""
    line = lines[mark.line]
    field = line.split(":", 1)[0].strip() if ":" in line else ""
    return f" — the offending line declares the field '{field}'" if field else ""


def _require_field_types(label: str, fm: dict) -> None:
    """Assert each frontmatter field's own type, by name."""
    for field, expected in FIELD_TYPES:
        if field not in fm:
            raise AssertionError(f"GATE1 FAIL: {field} is missing entirely — file: {label}/SKILL.md")
        value = fm[field]
        if not isinstance(value, expected):
            hint = COLON_SPACE_HINT if expected is str else ""
            raise AssertionError(
                f"GATE1 FAIL: {field} must be {expected.__name__}, "
                f"got {type(value).__name__}{hint} — file: {label}/SKILL.md"
            )
        if expected is list:
            bad = [v for v in value if not isinstance(v, str)]
            if bad:
                raise AssertionError(
                    f"GATE1 FAIL: every {field} item must be str, got "
                    f"{type(bad[0]).__name__} {bad[0]!r} "
                    "(a ': ' inside an unquoted item turns the item into a mapping) "
                    f"— file: {label}/SKILL.md"
                )
            dupes = sorted({v for v in value if value.count(v) > 1})
            if dupes:
                raise AssertionError(
                    f"GATE1 FAIL: {field} has duplicate items {dupes[:3]} — file: {label}/SKILL.md"
                )


def _gate1(label: str, fm_text: str) -> dict:
    """Parse one frontmatter block and type-check it; raise AssertionError naming the field."""
    try:
        import yaml
    except ImportError as exc:  # a missing parser is a hard stop, never a skip
        raise AssertionError(
            "GATE1 FAIL: pyyaml is required for the frontmatter gate — an unavailable parser is "
            "a hard stop, never a reason to skip. Set PYTHONPATH to the directory that holds it "
            "(PYTHONPATH=<shared-pkgs-dir>) and rerun."
        ) from exc
    try:
        fm = yaml.safe_load(fm_text)
    except Exception as exc:  # a YAML syntax error surfaces here
        raise AssertionError(
            f"GATE1 FAIL: {label}/SKILL.md frontmatter does not parse: "
            f"{str(exc).splitlines()[0]}{_blame_line(fm_text, exc)} — file: {label}/SKILL.md"
        ) from exc
    if not isinstance(fm, dict):
        raise AssertionError(
            f"GATE1 FAIL: frontmatter must be a mapping, got {type(fm).__name__} — file: {label}/SKILL.md"
        )
    _require_field_types(label, fm)
    return fm


def _cjk_stats(text: str):
    lo, hi = CJK_RANGE
    lines = [l for l in text.splitlines() if l.strip()]
    cjk_lines = [l for l in lines if any(lo <= ch <= hi for ch in l)]
    ratio = len(cjk_lines) / max(1, len(lines))
    return len(cjk_lines), len(lines), ratio


def validate() -> None:
    """Four gates. Each one exists because a release went out without it."""
    root_skill = ROOT / "SKILL.md"
    root_manifest = ROOT / "manifest.yaml"
    dist_skill = DIST_SRC / "SKILL.md"
    dist_manifest = DIST_SRC / "manifest.yaml"
    for p in (root_skill, root_manifest, dist_skill, dist_manifest):
        assert p.exists(), f"{p.relative_to(ROOT)} missing (run from repo root)"

    # ---- gate 1: every field parses, and each carries the type it promises
    # (per-field, so a failure names the field rather than a downstream symptom)
    parsed = {}
    for label, path in (("root", root_skill), ("dist", dist_skill)):
        parsed[label] = _gate1(label, _frontmatter(path))

    # ---- gate 2: the Chinese copy must still be Chinese, and must not BE the English root
    dist_text = dist_skill.read_text(encoding="utf-8")
    root_text = root_skill.read_text(encoding="utf-8")
    n_cjk, n_lines, ratio = _cjk_stats(dist_text)
    assert n_cjk >= CJK_LINES_MIN_DIST and ratio >= CJK_RATIO_MIN_DIST, (
        f"dist/SKILL.md looks like the ENGLISH root: {n_cjk}/{n_lines} CJK lines "
        f"({ratio:.0%}), below the {CJK_RATIO_MIN_DIST:.0%} / {CJK_LINES_MIN_DIST}-line floor. "
        "The English root was probably copied over the Chinese copy."
    )
    r_cjk, r_lines, r_ratio = _cjk_stats(root_text)
    assert r_ratio <= CJK_RATIO_MAX_ROOT, (
        f"root/SKILL.md is {r_ratio:.0%} CJK lines ({r_cjk}/{r_lines}) — the Chinese copy "
        "was probably written back over the English source."
    )
    assert dist_text != root_text, "root and dist SKILL.md are identical — one copy was clobbered"

    # ---- gate 3: one version, five places (the builder constant counts)
    declared = {
        "root/SKILL.md": str(parsed["root"]["version"]),
        "root/manifest.yaml": _manifest_version(root_manifest),
        "dist/SKILL.md": str(parsed["dist"]["version"]),
        "dist/manifest.yaml": _manifest_version(dist_manifest),
        "package.py VERSION": VERSION,
    }
    mismatch = {k: v for k, v in declared.items() if v != VERSION}
    assert not mismatch, f"version disagreement (expected {VERSION}): {mismatch}"

    # ---- gate 4: the two copies enumerate the same triggers, index by index
    for key in ("read_when", "tags"):
        a = parsed["root"].get(key) or []
        b = parsed["dist"].get(key) or []
        assert len(a) == len(b), (
            f"'{key}' count differs: root={len(a)} dist={len(b)} — rebuilding both from the "
            "same table is the only way to keep index N meaning the same thing on both sides"
        )


def _manifest_version(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("version:"):
            return line.split(":", 1)[1].strip().strip('"').strip("'")
    return "<missing>"


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


SELFTEST_CASES = (
    (
        "a well-formed frontmatter must be accepted (control — without this the \
negative cases prove nothing)",
        """---
name: demo
slug: demo
version: "9.9.9"
description: a demo frontmatter
summary: a plain one-line summary
read_when:
  - 'one'
tags:
  - 'demo'
---
""",
        None,
    ),
    (
        "a summary that became a mapping (value pushed to the next line) — gate 1 must \
blame summary, not read_when",
        """---
name: demo
slug: demo
version: "9.9.9"
description: a demo frontmatter
summary:
  Families covered: Windows
read_when:
  - 'one'
tags:
  - 'demo'
---
""",
        ("GATE1 FAIL", "summary must be str", "got dict", "colon-space"),
    ),
    (
        "the same colon-space kept on the summary line — a parse error must still name the \
field, not just a line number",
        """---
name: demo
slug: demo
version: "9.9.9"
description: a demo frontmatter
summary: Families covered: Windows
read_when:
  - 'one'
tags:
  - 'demo'
---
""",
        ("GATE1 FAIL", "does not parse", "declares the field 'summary'"),
    ),
    (
        "a read_when item with ': ' — here the field really is read_when, and the message \
should say so",
        """---
name: demo
slug: demo
version: "9.9.9"
description: a demo frontmatter
summary: a plain one-line summary
read_when:
  - 'a': b
tags:
  - 'demo'
---
""",
        ("GATE1 FAIL", "read_when", "must be str", "got dict"),
    ),
)


def selftest() -> int:
    """Feed gate 1 frontmatters that are wrong in four ways and read the verdicts.

    The point is not that a bad input is rejected — it is that the rejection
    names the right field. A gate whose message points at `read_when` when
    `summary` is broken costs more time than no gate at all.
    """
    failures = 0
    for title, text, expected in SELFTEST_CASES:
        print(f"[selftest] case: {title}")
        try:
            _gate1("selftest", _frontmatter_from_text(text))
        except AssertionError as e:
            message = str(e)
            print(f"           rejected -> {message}")
            if expected is None:
                print("           FAIL: a valid frontmatter was rejected")
                failures += 1
                continue
            missing = [t for t in expected if t not in message]
            if missing:
                print(f"           FAIL: message does not mention {missing}")
                failures += 1
            elif "summary" in message and "read_when" in message:
                print("           FAIL: message names both summary and read_when — ambiguous")
                failures += 1
            else:
                print("           PASS: names the right field, the expected type and the actual type")
        else:
            if expected is None:
                print("           PASS: accepted, as it should be")
            else:
                print("           FAIL: the broken frontmatter was accepted without a word")
                failures += 1
        print()
    print(f"[selftest] {len(SELFTEST_CASES) - failures}/{len(SELFTEST_CASES)} cases behaved correctly")
    return 0 if failures == 0 else 1


def _arcnames(files: list[Path]) -> list[str]:
    return [(Path(PKG_NAME) / p.relative_to(DIST_SRC)).as_posix() for p in files]


def verify_package(out_zip: Path, files: list[Path]) -> list[str]:
    """Return the defects in the artifact just written; empty means it is sound.

    "A file with the right name exists" is not the same claim as "the package
    is the source". A zip missing a member, carrying an unexpected one, or
    holding a member that no longer matches dist/ is a packaging failure, and it
    must not be printed as a footnote under an [OK].
    """
    if not out_zip.exists():
        return [f"{out_zip.name} was not written"]
    expected = _arcnames(files)
    problems: list[str] = []
    with zipfile.ZipFile(out_zip) as zf:
        names = zf.namelist()
        missing = sorted(set(expected) - set(names))
        extra = sorted(set(names) - set(expected))
        if missing:
            problems.append(f"missing member(s) {missing}")
        if extra:
            problems.append(f"unexpected member(s) {extra}")
        for path, arc in zip(files, expected):
            if arc in names and zf.read(arc) != path.read_bytes():
                problems.append(f"member does not match its source: {arc}")
    return problems


def main(verbose: bool = False) -> int:
    try:
        validate()
    except AssertionError as e:
        print(f"[FAIL] {e}")
        return 1
    except Exception as e:  # anything else is a bug in this builder, say so
        print(f"[FAIL] unexpected error during validation: {type(e).__name__}: {e}")
        return 1

    out_dir = ROOT / "dist"
    out_dir.mkdir(exist_ok=True)
    out_zip = out_dir / f"{PKG_NAME}-{VERSION}.zip"

    files = collect_files()
    arcnames = _arcnames(files)
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, arc in zip(files, arcnames):
            zf.write(path, arc)

    # The artifact is checked before it is announced: an [OK] that precedes the
    # check is a statement about the writer, not about the file.
    problems = verify_package(out_zip, files)
    if problems:
        print(f"[FAIL] package does not match the source: {'; '.join(problems)}")
        return 1

    print(f"[OK] {out_zip}")
    print(f"     {len(files)} files, prefix '{PKG_NAME}/', verified against dist/ byte for byte")
    for arc in arcnames:
        print(f"       - {arc}")

    # Older packages sitting in dist/ are residue from the cloud-sync client, not
    # a defect — the current package was verified above. This used to print at
    # WARN level, permanently, about something that was never wrong: a warning
    # that cannot be cleared is how a real one gets ignored.
    stale = sorted(z.name for z in out_dir.glob(f"{PKG_NAME}-*.zip") if z.name != out_zip.name)
    if stale:
        print(f"[INFO] dist/ also holds older package(s) {', '.join(stale)} — sync-client residue, "
              "not a packaging defect (see --verbose)")
        if verbose:
            print("       The package above was verified against dist/ byte for byte, so these are")
            print("       not part of this release. They may be held open by the sync client, in")
            print("       which case deleting them hangs and rm -f never returns — remove them from")
            print("       the sync client instead of from a shell.")
    elif verbose:
        print("[INFO] dist/ holds no older packages")
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--selftest" in args:
        sys.exit(selftest())
    sys.exit(main(verbose="--verbose" in args))
