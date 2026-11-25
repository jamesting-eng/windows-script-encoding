# windows-script-encoding

A field-tested ledger of engineering pitfalls. Each entry: symptom, root cause, fix, and the anti-lesson. The name comes from its origin (Windows script encoding), but the scope is broader.

## Coverage

- **Windows script encoding** — CRLF + pure ASCII for `.ps1`/`.bat`/`.cmd`; binary write, immediate self-check, emergency fallback.
- **Launchers, cloud-sync and sandbox tests** — conflict copies, admin-context failures, sandbox-vs-real bug isolation.
- **Cloud-sync build directories** — resurrection of deleted artifacts, zombie cleanup, runtime-closure copy.
- **Related environment traps** — tool paths, PATH drift, shell quoting, deletion shims, network/proxy retries.
- **Front-end engineering** — screenshot-driven layout fixes, headless pixel checks, test visibility, auth-driven UI, page-family consistency.
- **Document generation and diagrams** — HTML → DOCX; CJK labels in Mermaid.
- **Internationalization** — coverage gates, storage cleanup, large text refactors.
- **Third-party integration and external auth** — platform onboarding rules, cloud auth SDK pitfalls.
- **Deploy surface** — the deployed directory is the public surface; `.gitignore` is not a filter.
- **PS cmdlet defaults** — cross-version encoding, alias shadowing, `$PROFILE`.
- **Scripted demos** — playback/export parity, timeline and cursor discipline.

## Use

Read the pre-flight checklist before writing or running a Windows script. On a platform/auth error, find the matching chapter via the symptom table in `SKILL.md`. Run `scripts/encoding_selfcheck.py` to verify encoding before publishing a script.

## Layout

`SKILL.md` is the skill; `scripts/` holds the checkers; `package.py` builds the SkillHub zip from `dist/windows-script-encoding/`.

MIT — see [LICENSE](LICENSE).
