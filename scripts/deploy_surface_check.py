#!/usr/bin/env python3
# -*- coding: ascii -*-
"""deploy_surface_check.py - audit what a directory-deploy host is actually serving.

The deploy uploads the working directory, so the only trustworthy answer to
"is my credential file / build log / internal doc readable from the internet"
is a probe from the public domain. This script runs that probe as a matrix and
reports BOTH sides:

  deny  matrix : paths that must NOT be readable  -> expect 403 / 404 / 410
  allow matrix : paths that must keep working     -> expect 200
  local scan   : risk-shaped files in the tree    -> each one probed live

A deny-only run cannot tell "blocked" from "broken" (it is equally green when
the whole site is down), which is why the allow side is not optional.

Usage:
  python deploy_surface_check.py --url https://example.com
  python deploy_surface_check.py --url https://example.com --allow admin --allow api/health
  python deploy_surface_check.py --url https://example.com --scan-dir .
  python deploy_surface_check.py --url https://example.com --json

Exit code: 0 all pass, 1 any FAIL or EXPOSED.
Pure stdlib, no dependencies. ASCII only.
"""

import argparse
import json
import os
import re
import ssl
import subprocess
import sys
import urllib.error
import urllib.request

TIMEOUT = 10
UA = "deploy-surface-check/1.0"

# Class-based deny list. Deny by class, not by the one filename that leaked.
DEFAULT_DENY = [
    # dotfiles / VCS
    "/.env", "/.env.local", "/.env.production", "/.git/config",
    "/.gitignore", "/.gitattributes", "/.DS_Store", "/Thumbs.db",
    # package manifests and build config (reveal deps, scripts, secret refs)
    "/package.json", "/package-lock.json", "/yarn.lock", "/pnpm-lock.yaml",
    "/tsconfig.json", "/vite.config.js", "/next.config.js",
    # server / middleware / build source
    "/middleware.js", "/predeploy.mjs", "/server.js",
    "/cloud-functions/api/index.js",
    "/cloud-functions/api/%5B%5Bdefault%5D%5D.js",
    # internal docs and tooling
    "/deliverables/", "/.workbuddy/memory/MEMORY.md",
    # launcher shims
    "/node.cmd", "/npm.cmd", "/deploy.bat", "/deploy.ps1",
    # credential-shaped scratch files (underscore convention)
    "/_ck.txt", "/_oc_ck.txt", "/_session.txt", "/_cookie.txt",
    "/%5Fck.txt",
    # logs / exports / keys / archives
    "/build.log", "/debug.log", "/leads.csv", "/export.csv",
    "/server.pem", "/server.key", "/id_rsa", "/backup.zip",
    # traversal
    "/..%2f..%2fetc%2fpasswd", "/%2e%2e/%2e%2e/etc/passwd",
]

DEFAULT_ALLOW = ["/", "/robots.txt", "/sitemap.xml"]

# Shapes that should never sit inside a directory that gets uploaded whole.
RISK_PATTERNS = [
    (re.compile(r"^_.*\.txt$", re.I), "underscore scratch file (debug/cookie jar)"),
    (re.compile(r".*\.cookie$", re.I), "cookie jar"),
    (re.compile(r"^\.env(\..*)?$", re.I), "env file"),
    (re.compile(r".*\.(pem|key|p12|pfx)$", re.I), "private key / cert"),
    (re.compile(r"^id_rsa.*$", re.I), "ssh private key"),
    (re.compile(r".*\.(log|csv)$", re.I), "log or data export"),
]

DENY_OK = (403, 404, 410)
SKIP_DIRS = {".git", "node_modules", "dist", ".edgeone", "__pycache__"}


def msys_root():
    """Windows form of '/' under Git Bash / MSYS, used to undo argument mangling."""
    try:
        out = subprocess.run(["cygpath", "-w", "/"], capture_output=True, text=True, timeout=5)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip().replace("\\", "/").rstrip("/")
    except Exception:  # noqa: BLE001
        pass
    return None


def norm_path(value):
    """Normalize a CLI path.

    Git Bash rewrites a bare '/foo' argument into '<git-install-root>/foo' before
    the program ever sees it, which silently turns --allow /admin into a Windows
    path. Detect that and undo it, so the caller does not have to remember
    MSYS_NO_PATHCONV=1.
    """
    p = value.replace("\\", "/").strip()
    if re.match(r"^[A-Za-z]:/", p):
        root = msys_root()
        if root and p.startswith(root + "/"):
            p = p[len(root):]
        else:
            raise SystemExit(
                "[path] %r is a Windows path, not a URL path.\n"
                "        Drop the leading slash (--allow admin) or run with MSYS_NO_PATHCONV=1." % value
            )
    return p if p.startswith("/") else "/" + p


def _opener():
    """Never inherit the system proxy.

    urllib reads http_proxy/https_proxy from the environment, so a corporate
    proxy turns every probe of a local or private host into a 502 - and a 502
    reads as "unreachable", which on the deny side is indistinguishable from
    "blocked". Opt back in explicitly with SURFACE_CHECK_PROXY if you really
    need a proxy.
    """
    proxy_env = os.environ.get("SURFACE_CHECK_PROXY", "").strip()
    if proxy_env:
        handler = urllib.request.ProxyHandler({"http": proxy_env, "https": proxy_env})
    else:
        handler = urllib.request.ProxyHandler({})
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return urllib.request.build_opener(handler, urllib.request.HTTPSHandler(context=ctx))


OPENER = _opener()


def probe(base, path):
    """GET only, never HEAD.

    A HEAD probe lies in both directions: function routes that declare only GET
    answer HEAD with 404 (so a healthy endpoint looks broken), and a static host
    that serves the file on GET while 404-ing HEAD would make an EXPOSED file
    look denied. That second one is a false negative on the security side, so
    GET is the only method this matrix trusts. Range caps the transfer.
    """
    req = urllib.request.Request(
        base.rstrip("/") + path,
        headers={"User-Agent": UA, "Range": "bytes=0-0", "Accept": "*/*"},
    )
    try:
        with OPENER.open(req, timeout=TIMEOUT) as resp:
            return resp.getcode()
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:  # noqa: BLE001 - network failure is a real signal
        return "ERR:%s" % type(e).__name__


def reachable(code):
    return isinstance(code, int) and 200 <= code < 300


def paths_from_sitemap(base):
    try:
        req = urllib.request.Request(base.rstrip("/") + "/sitemap.xml", headers={"User-Agent": UA})
        with OPENER.open(req, timeout=TIMEOUT) as resp:
            body = resp.read().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return []
    out = []
    for loc in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", body):
        m = re.match(r"^https?://[^/]+(/.*)?$", loc)
        if m:
            p = m.group(1) or "/"
            if p not in out:
                out.append(p)
    return out[:40]


def scan_local(root):
    hits = []
    if not os.path.isdir(root):
        return hits
    for name in sorted(os.listdir(root)):
        if os.path.isdir(os.path.join(root, name)):
            continue
        for pat, label in RISK_PATTERNS:
            if not pat.match(name):
                continue
            try:
                size = os.path.getsize(os.path.join(root, name))
            except OSError:
                size = -1
            if name.lower().startswith(".env") and size == 0:
                break
            hits.append((name, label, size))
            break
    return hits


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--url", required=True, help="base url of the deployed site")
    ap.add_argument("--deny", action="append", default=[], help="extra deny path (admin, not /admin)")
    ap.add_argument("--allow", action="append", default=[], help="extra allow path (api/health, not /api/health)")
    ap.add_argument("--no-sitemap", action="store_true", help="do not derive allow paths from sitemap.xml")
    ap.add_argument("--scan-dir", default="", help="also scan this local dir and probe each risk file live")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    base = args.url
    deny = list(dict.fromkeys([norm_path(p) for p in DEFAULT_DENY] + [norm_path(p) for p in args.deny]))
    allow = list(dict.fromkeys([norm_path(p) for p in DEFAULT_ALLOW] + [norm_path(p) for p in args.allow]))
    if not args.no_sitemap:
        for p in paths_from_sitemap(base):
            if p not in allow and p not in deny:
                allow.append(p)

    rows = []
    for p in deny:
        code = probe(base, p)
        rows.append({"kind": "deny", "path": p, "code": code, "ok": code in DENY_OK})
    for p in allow:
        code = probe(base, p)
        rows.append({"kind": "allow", "path": p, "code": code, "ok": reachable(code)})

    local = []
    for name, label, size in scan_local(args.scan_dir):
        code = probe(base, "/" + name)
        local.append({
            "file": name, "why": label, "bytes": size, "code": code,
            "exposed": reachable(code),
            "ok": code in DENY_OK,
        })

    deny_rows = [r for r in rows if r["kind"] == "deny"]
    allow_rows = [r for r in rows if r["kind"] == "allow"]
    deny_bad = [r for r in deny_rows if not r["ok"]]
    allow_bad = [r for r in allow_rows if not r["ok"]]
    exposed = [r for r in local if r["exposed"]]
    failed = bool(deny_bad or allow_bad or exposed)

    if args.json:
        print(json.dumps({
            "url": base,
            "deny": {"total": len(deny_rows), "failed": [r["path"] for r in deny_bad]},
            "allow": {"total": len(allow_rows), "failed": [r["path"] for r in allow_bad]},
            "local": {"total": len(local), "exposed": [r["file"] for r in exposed], "files": local},
            "pass": not failed,
            "rows": rows,
        }, ensure_ascii=True, indent=2))
        return 1 if failed else 0

    line = "=" * 78
    print(line)
    print("deploy surface audit : %s" % base)
    print(line)

    print("\n[deny matrix] must NOT be readable")
    for r in deny_rows:
        print("  %s  %-12s %-46s expect 403/404/410" % (
            "PASS" if r["ok"] else "FAIL", r["code"], r["path"]))

    print("\n[allow matrix] must keep working")
    for r in allow_rows:
        print("  %s  %-12s %-46s expect 200" % (
            "PASS" if r["ok"] else "FAIL", r["code"], r["path"]))

    if args.scan_dir:
        print("\n[local scan] risk-shaped files under %s, each probed live" % os.path.abspath(args.scan_dir))
        if not local:
            print("  PASS  none")
        for r in local:
            tag = "EXPOSED" if r["exposed"] else "denied"
            print("  %-8s %-12s %-28s %-34s %s bytes" % (
                tag, r["code"], r["file"], r["why"], r["bytes"]))

    print("\n" + "-" * 78)
    print("deny  %d/%d ok%s" % (
        len(deny_rows) - len(deny_bad), len(deny_rows),
        "" if not deny_bad else "   FAILED: " + ", ".join(r["path"] for r in deny_bad)))
    print("allow %d/%d ok%s" % (
        len(allow_rows) - len(allow_bad), len(allow_rows),
        "" if not allow_bad else "   FAILED: " + ", ".join(r["path"] for r in allow_bad)))
    if args.scan_dir:
        print("local %d risk-shaped, %d exposed%s" % (
            len(local), len(exposed),
            "" if not exposed else "   EXPOSED: " + ", ".join(r["file"] for r in exposed)))
    print("VERDICT: %s" % ("PASS" if not failed else "FAIL"))
    print("-" * 78)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
