# windows-script-encoding

Iron rules for writing Windows scripts (`.ps1` / `.bat` / `.cmd`) so that
PowerShell parse-stage failures stop recurring across projects.

## The problem

Windows scripts keep breaking in two predictable ways:

1. **LF-only line endings.** PowerShell 5.1 fails at the *parse stage* on
   `.ps1` files that use `\n` instead of `\r\n`. The failure is silent: the
   PowerShell tool swallows stdout/stderr and only returns exit code 1, so the
   real cause is invisible. Re-saving the same content as CRLF makes it run.
2. **Non-ASCII bytes in `.bat`/`.cmd`.** Chinese (or any non-ASCII) characters
   in a batch file get mangled by the system code page (GBK), which can make
   `cmd` mis-execute and surface as a WSH "800A03EA" error.

Both are avoidable with hard rules.

## Iron rules

- `.ps1`: always **CRLF + pure ASCII**. Never write `.ps1` with the Edit/Write
  tool (it tends to emit LF-only). Write via Python in binary mode and force
  `b'\n' -> b'\r\n'`. Self-check after writing: assert CRLF present, LF-only
  lines == 0, non-ASCII bytes == 0.
- `.bat`/`.cmd`: body must be **pure ASCII** (0 non-ASCII bytes). Put any human
  message in English (or keep Chinese in a separate non-executed file).
- Prefer inline PowerShell (`-Command`) over writing a script file.
- When you must produce a file, build it with Python and verify byte-level.

## Repository layout (dual-release)

This repo is the **English source of truth** (GitHub). The Chinese copy for
SkillHub lives under `dist/`.

```
SKILL.md                       # English skill (GitHub)
manifest.yaml                  # English manifest
package.py                     # builds the publishable zip from dist/
dist/windows-script-encoding/  # Chinese copy for SkillHub
    SKILL.md
    manifest.yaml
```

Dual-release policy: GitHub = 100% English, SkillHub = 100% Chinese, while
**scripts are never translated** (encoding errors from translation cause
downstream breakage).

## License

MIT — see [LICENSE](LICENSE).
