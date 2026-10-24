# windows-script-encoding

> **Note on the name (legacy).** This skill started life as "Windows script
> (.ps1/.bat/.cmd) encoding iron rules" — hence the name. It has since grown
> into a **battle-tested library of iron rules for avoiding recurring
> engineering pitfalls**. The encoding rules are still the anchor, but the
> skill now also covers cloud-sync build directories, sandbox testing,
> internationalization, CJK diagrams, third-party platform integration,
> cloud-auth SDK integration, and front-end layout debugging. The name stuck
> because it is catchy; the *content* is broader than the name suggests.

Every chapter is written from real failures that recurred across projects, and
follows the same shape: **Symptom → Root cause → Fix → RED anti-lesson**
(what we tried that made it worse). The point is to stop the same bug from
costing days a second time.

## What this skill actually covers

### 1. Windows script encoding & line-ending (the origin)
The founding rules. `.ps1` files must be **CRLF + pure ASCII** — PowerShell 5.1
fails at the *parse stage* on LF-only files (silent exit 1), and non-ASCII
bytes in `.bat`/`.cmd` get mangled by the system codepage (GBK). Includes the
pre-flight self-check (assert CRLF present, LF-only lines == 0, non-ASCII == 0),
trigger symptoms, root cause, the must-follow iron rules, the standard
workflow, anti-patterns, and an emergency fallback. Plus related cross-tool
environment traps and real-world failure cases from production `.bat` scripts.

### 2. Launcher, cloud-sync & sandbox-test traps
How cloud-sync layers resurrect deleted build artifacts, why a sandbox-test
fault looks like a real bug, and how to isolate the two by re-running the same
script on a different channel.

### 3. Internationalization & text-refactor traps
i18n coverage gates (don't let one uncovered key fail the build), storage
cleanup & verification, and the pitfalls of large text refactors.

### 4. Cloud-sync build directories: resurrection & zombie cleanup
Why deleting a file locally does **not** clear it from production (the sync
layer rehydrates it), the runtime-closure BFS copy that ships only what is
actually referenced, and a safe zombie-cleanup procedure.

### 5. PS cmdlet defaults / cross-version / profile pitfalls
The `Out-File` / `Set-Content` encoding matrix across PS 5.1 vs 7+; how PS 7+
aliases shadow native `curl`/`wget`; `$PROFILE` corruption that breaks every
session; and three silent defaults (`Get-Content -Raw`, `.ps1` not in PATH,
`ConvertFrom-Json` depth 2).

### 6. Diagrams with CJK labels in markdown (Mermaid)
The real engine pipeline and the three preprocessors that mangle labels; the
only reliable multi-line label method (`#10;`); `wrappingWidth` pinning;
per-node width via `themeCSS` + `class`; and a reusable local Playwright
verification harness.

### 7. Third-party platform integration & skill publishing iron rules
Ten iron rules for integrating payments / login / push or publishing a skill
(root path returns `success`, config isolation, onboarding order, buyer/seller
separation, sandbox ≠ production, test account, official tool first, **version
alignment**, permission switch, callback-first), a pre-flight checklist, and a
full Alipay Pay-Skill launch post-mortem.

### 8. External-auth / cloud-SDK integration iron rules (WorkBuddy Cloud)
Nine iron rules for integrating the cloud auth SDK or calling `/.cloud/auth/v1/*`
directly — e.g. an admin backend that logs in by phone + SMS OTP. Covers
client-bound sessions (`session issued for another client`), the `verifyOtp`
two-step trap, the `/.cloud/auth` path prefix, the mandatory
`x-wb-webapp-access-key` header, the raw `verification/verify` bypass,
server-side phone whitelists, `curl --noproxy '*'` for localhost, deploy-disk
persistence, and installing a server-side "dashcam" debug recorder on day one.

### 9. Front-end layout debugging iron rules
For screenshot-flagged visual fixes: **measure** real geometry before changing
offsets (never guess from the image), baseline-align number + unit typography,
and headless-screenshot hygiene on Edge.

## How to use it

1. Read the **Pre-flight checklist** (chapter 1) before writing/running any
   Windows script in the trigger list.
2. When you hit a platform/auth error that won't resolve, jump to the relevant
   chapter (7 for third-party platforms, 8 for cloud auth) — eight times out of
   ten one of the iron rules was broken.
3. When a diagram or layout looks wrong, use chapters 6 and 9.

## Repository layout (dual-release)

This repo is the **English source of truth** (GitHub). The Chinese copy for
SkillHub lives under `dist/`.

```
SKILL.md                       # English skill (GitHub)
manifest.yaml                  # English manifest
README.md                      # this file (GitHub)
package.py                     # builds the publishable zip from dist/
dist/windows-script-encoding/  # Chinese copy for SkillHub
    SKILL.md
    manifest.yaml
    package.py
```

Dual-release policy: GitHub = 100% English, SkillHub = 100% Chinese, while
**scripts are never translated** (encoding errors from translation cause
downstream breakage). After editing, keep the version markers aligned across
`SKILL.md` (frontmatter), `manifest.yaml`, `package.py`, and the `dist/`
Chinese copy (chapter 7, Rule 8), then run `package.py` to rebuild the zip and
commit. Push / publish to SkillHub only when you intend to ship.

## License

MIT — see [LICENSE](LICENSE).
