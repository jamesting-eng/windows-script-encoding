#!/usr/bin/env python3
"""encoding_selfcheck.py - verify scripts follow the CRLF + pure-ASCII iron rules.

One command instead of a manual checklist. Pure ASCII on purpose - this script
must never violate the very rules it checks.

Usage:
  python encoding_selfcheck.py file1.ps1 file2.bat ...   # check specific files
  python encoding_selfcheck.py <dir>                     # scan *.ps1 *.bat *.cmd under dir (recursive)
  python encoding_selfcheck.py <dir> --ext py,ts         # also scan other extensions

Checks per file:
  1. CRLF line endings present, bare-LF count == 0  (for .ps1/.bat/.cmd)
  2. non-ASCII byte count == 0

Exit codes: 0 = all pass, 1 = violations found, 2 = nothing to check.
"""
import os
import sys

SCRIPT_EXTS = {".ps1", ".bat", ".cmd"}
SKIP_DIRS = {".git", "__pycache__", "node_modules"}


def check(path):
    with open(path, "rb") as f:
        data = f.read()
    crlf = data.count(b"\r\n")
    lf_only = data.count(b"\n") - crlf
    nonascii = sum(1 for b in data if b > 127)
    return crlf, lf_only, nonascii


def main():
    argv = sys.argv[1:]
    extra_exts = set()
    if "--ext" in argv:
        i = argv.index("--ext")
        if i + 1 < len(argv):
            extra_exts = {e.lower().lstrip(".") for e in argv[i + 1].split(",")}
            argv = argv[:i] + argv[i + 2:]
    targets = []
    for a in argv:
        if os.path.isdir(a):
            for root, dirs, files in os.walk(a):
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
                for fn in files:
                    ext = os.path.splitext(fn)[1].lower()
                    if ext in SCRIPT_EXTS or ext in extra_exts:
                        targets.append(os.path.join(root, fn))
        elif os.path.isfile(a):
            targets.append(a)
        else:
            print("[SKIP] not found: " + a)
    if not targets:
        print("Nothing to check.")
        print("Usage: python encoding_selfcheck.py <file-or-dir> [...] [--ext py,ts]")
        return 2
    bad = 0
    for p in sorted(targets):
        crlf, lf_only, nonascii = check(p)
        needs_crlf = os.path.splitext(p)[1].lower() in SCRIPT_EXTS
        problems = []
        if needs_crlf and crlf == 0:
            problems.append("no CRLF line endings")
        if lf_only > 0:
            problems.append(str(lf_only) + " bare LF line(s)")
        if nonascii > 0:
            problems.append(str(nonascii) + " non-ASCII byte(s)")
        tag = "FAIL" if problems else "OK"
        if problems:
            bad += 1
        line = "[" + tag + "] " + p + "  (CRLF=" + str(crlf) + ", LF-only=" + str(lf_only) + ", non-ASCII=" + str(nonascii) + ")"
        if problems:
            line += "  <- " + "; ".join(problems)
        print(line)
    print("")
    if bad:
        print(str(bad) + " file(s) FAILED. Fix (CRLF + pure ASCII) and re-run until clean.")
        return 1
    print("All " + str(len(targets)) + " file(s) pass the CRLF + pure-ASCII iron rules.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
