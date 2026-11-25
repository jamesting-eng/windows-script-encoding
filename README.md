# windows-script-encoding

A field-tested ledger of engineering pitfalls. Each entry gives the symptom, the root cause, and the fix — so the same rake is not stepped on twice. The name comes from its origin (Windows script encoding); the scope is broader.

## What it covers

**1. Windows script encoding & line endings** (the origin)
`.ps1` files must be CRLF + pure ASCII — PowerShell 5.1 fails at the *parse stage* on LF-only files (silent exit 1), and non-ASCII bytes in `.bat` / `.cmd` get mangled by the system codepage (GBK). Includes the pre-flight self-check (CRLF present, LF-only lines == 0, non-ASCII == 0), trigger symptoms, root cause, iron rules, standard workflow, anti-patterns, and an emergency fallback. Plus cross-tool environment traps and real-world failure cases from production `.bat` scripts.

**2. Launchers, cloud-sync and sandbox-test traps**
How cloud-sync layers resurrect deleted build artifacts, why a sandbox-test fault looks like a real bug, and how to isolate the two by re-running the same script on a different channel.

**3. Cloud-sync build directories: resurrection & zombie cleanup**
Why deleting a file locally does not clear it from production (the sync layer rehydrates it), the runtime-closure BFS copy that ships only what is actually referenced, and a safe zombie-cleanup procedure.

**4. Related environment traps**
Tool paths, PATH drift, managed binary version drift, shell quoting (`-c` payloads, heredocs, keyword interception), deletion shims, and network/proxy transient failures with retry strategy.

**5. Front-end engineering**
Screenshot-driven layout fixes (measure before changing offsets), number + unit typography, headless pixel-exact exports, test visibility (CSS-hidden ≠ unmounted), auth-driven UI traps, and page-family consistency.

**6. Document generation and diagrams**
HTML → DOCX rules (self-referential CSS variables, dropped empty divs, page breaks, read-back acceptance) and CJK labels in Mermaid (label engine, `#10;`, wrappingWidth, themeCSS, local Playwright verification).

**7. Internationalization and text refactor**
i18n coverage gates (one uncovered key must fail the build), storage cleanup and verification, and pitfalls of large text refactors.

**8. Third-party integration and external auth**
Ten rules for integrating payments / login / push or publishing a skill (config isolation, sandbox ≠ production, version alignment, callback-first), and nine rules for cloud auth SDK / `/.cloud/auth/v1/*` (client-bound sessions, `verifyOtp` two-step, mandatory headers, server-side phone whitelists, `curl --noproxy '*'` for localhost).

**9. Deploy surface**
The directory you deploy IS what the internet can read. `.gitignore` is not a deploy filter — the guarantee is a runtime deny plus a pre-deploy guard, verified on both sides. Also: rebuilding a deploy surface read-only, with four failure modes where "the script believed it succeeded because nothing threw".

**10. PS cmdlet defaults, cross-version and profile pitfalls**
`Out-File` / `Set-Content` encoding differs across PS 5.1 vs 7+; PS 7+ aliases shadow native `curl` / `wget`; a broken `$PROFILE` breaks every session; three silent defaults (`Get-Content -Raw`, `.ps1` not on PATH, `ConvertFrom-Json` depth 2).

**11. Scripted demos and screencasts**
Playback/export parity (verify in the state the user sees), cancellable timeline timers, top-anchored block flow, and a single click driving multi-step work with a human-like cursor.

## Use

1. Read the **pre-flight checklist** in `SKILL.md` before writing or running any Windows script in the trigger list.
2. On a platform / auth error, jump to the matching chapter via the **symptom-to-fix table** — eight times out of ten an iron rule was broken.
3. Before trusting your own check, read the verification-traps chapter — a gate that has never failed is not evidence.

Run `scripts/encoding_selfcheck.py` to verify CRLF + ASCII before publishing a script.

## Repository layout

```
SKILL.md                       # English skill (GitHub)
manifest.yaml                  # English manifest
README.md                      # this file
package.py                     # builds the publishable zip from dist/
scripts/                       # self-check and guard scripts
dist/windows-script-encoding/  # Chinese copy for SkillHub (SKILL.md + manifest + scripts)
```

MIT — see [LICENSE](LICENSE).
