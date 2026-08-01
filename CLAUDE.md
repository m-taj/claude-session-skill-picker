# claude-session-skill-picker — project conventions

## Architecture

- `skills-launch.py`, `skills-picker.py`, `skills-inject.py`, `skills-suggest.py`,
  `skills-update.py` are independent standalone scripts, **not a package** —
  they do not import from each other. Matching helper logic (cache-file path
  resolution, prefs loading, checksum verification, etc.) is deliberately
  duplicated in each file rather than shared via a common module. Keep this
  pattern when adding new hook scripts or background workers.
- Background work that shouldn't block a Claude Code session (suggestions,
  update checks) is a fully detached `subprocess.Popen` spawned from
  `skills-launch.py`, `stdout=DEVNULL`, wrapped in `try/except Exception: pass`.
  Each worker gates itself on a once-per-day cache file (`already_fresh()`
  comparing `date.today().isoformat()`) — never re-check more than once/day
  without a real reason.
- `install.sh`/`install.ps1` unconditionally overwrite every installed file
  except `skills-picker-overrides.json` (only copied if absent, to preserve
  user customization). This idempotent copy is the actual update mechanism —
  reuse it (shell out to it) rather than writing new install/copy logic.

## Release process

- Bump `VERSION`, run `python3 gen_checksums.py` to regenerate `CHECKSUMS.txt`,
  commit both, then `git tag vX.Y.Z` and cut a GitHub Release with
  `install.sh`/`install.ps1` attached.
- The self-update flow (`run_update()` in `skills-picker.py`) clones a
  **released git tag only, never `main`**. This is the trust boundary for the
  whole update channel — a bad push to `main` must never be able to reach an
  installed user; only a deliberate, tagged Release can.

## Anti-tamper stance (see `~/plans/skill-picker-plan/monetization-security-checklist.md` §9.6)

- No client-side Python is ever truly uncrackable. Don't build heavy DRM
  (PyArmor, compiled binaries, phone-home enforcement, license-key binding)
  — it doesn't stop a motivated actor and there's no server yet to make
  enforcement meaningful.
- `CHECKSUMS.txt`/tamper detection is informational only — flag mismatches,
  never auto-revert a user's local edit on their own machine.
- `licensing.py`'s `is_licensed()` is a seam for future paid features, not
  enforcement. It always returns `True` until real server-side entitlement
  infra exists — don't add local-only license validation before that.

## Working conventions

- `main` is a protected branch — every change goes through a feature branch
  + PR merged via the GitHub web UI. Direct pushes to `main` are rejected.
- `gh` CLI is unauthenticated in this environment — create PRs via the manual
  compare URL (`.../compare/main...branch-name`), not `gh pr create`.
- Verify by actually running code, not just reading it. Past real bugs were
  only caught this way: a PowerShell `Invoke-Expression` missing a call
  operator, a `pythonw.exe` path-guessing bug, an unguarded `Join-Path` on an
  empty Desktop path. Install PowerShell Core (`brew install powershell`) for
  real Windows-script dry runs when needed, and uninstall it again afterward.
- When dry-running `uninstall.ps1`/`uninstall.sh` against a fake `$HOME`: the
  Python adapter scripts (`adapters/codex.py`, `adapters/opencode.py`) resolve
  `~` via `os.path.expanduser`, which reads the **real** `$HOME`/`USERPROFILE`
  regardless of a faked PowerShell `$env:USERPROFILE`. Use a fixture with an
  **empty** `adapters/` dir for PowerShell dry runs so the agent-disconnect
  step has nothing to act on — never let it touch the real machine's Codex/
  OpenCode connections.
- pywebview's JS bridge (`window.pywebview.api.*`) is injected asynchronously
  after page load — always gate calls on `window.addEventListener('pywebviewready', fn)`,
  never call synchronously at script top level.
- Never commit API keys or secrets pasted into chat for live testing — they
  belong only in `~/.claude/cache/skills-picker-prefs.json` (outside the repo)
  or a user's own shell environment.

## Planning docs

Full design-decision records for shipped features live in
`~/plans/skill-picker-plan/` (not in this repo — see the project's plan-file
convention). `~/plans/skill-picker-plan/BACKLOG.md` is the single index of
everything shipped and everything still open.
