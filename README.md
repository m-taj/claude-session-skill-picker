
# Claude Session Skill Picker

A pair of [Claude Code](https://claude.ai/code) hooks that pop a **native checkbox dialog** at the start of every session so you can pick which skills to activate. Picks get injected as context on your first message — Claude turns them on before replying.

- macOS: native NSAlert with real checkbox accessory view (via JXA + Cocoa, no install)
- Windows: tkinter checkbox dialog (ships with the python.org installer, no extra install)
- **Auto-discovers** installed user skills and enabled plugin skills every session — install a new skill, it appears next time; uninstall one, it disappears.
- Skills with multiple modes (e.g. `caveman` has `lite | full | ultra`) get a dropdown next to the checkbox so you pick one and only one.

No more `/caveman:caveman ultra` typing every session. No terminal UI conflicts. No freezing on startup. No hardcoded skill list going stale.

---

## What it looks like

| macOS | Windows |
|---|---|
|<img width="867" height="454" alt="Screenshot 2026-06-01 at 2 55 22 PM" src="https://github.com/user-attachments/assets/1ae64e00-51fe-44af-a14b-8b2f865d9c36" />
| ![Windows dialog](images/win.png) |

Same UX both sides — click checkboxes, hit **Activate**.

---

## Prerequisites

| Platform | Need |
|---|---|
| macOS | Python 3 (preinstalled at `/usr/bin/python3` on modern macOS); `jq` for auto-install (`brew install jq`) |
| Windows | Python 3 from [python.org](https://www.python.org/downloads/) (Microsoft Store builds also work); PowerShell 5+ |

---

## Install

### macOS

```bash
git clone https://github.com/m-taj/claude-session-skill-picker.git
cd claude-session-skill-picker
bash install.sh
```

### Windows

```powershell
git clone https://github.com/m-taj/claude-session-skill-picker.git
cd claude-session-skill-picker
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Both installers do the same things:

1. Copy `skills-launch.py`, `skills-picker.py`, `skills-inject.py` into `~/.claude/hooks/`
2. Copy `skills-picker-overrides.json` into `~/.claude/hooks/` (only on first install — won't clobber your customized one)
3. Add a `SessionStart` (async) and a `UserPromptSubmit` (sync) hook entry to `~/.claude/settings.json`
4. Print next steps

Start a new Claude Code session — the dialog appears.

---

## How it works

Three small Python scripts wired into two hook events:

```
session starts
    └─> SessionStart hook (async)         ── skills-launch.py
            ├─ scan ~/.claude/skills/ (user skills)
            ├─ scan ~/.claude/plugins/cache/<owner>/<plugin>/*/skills/ for each enabled plugin
            ├─ merge with ~/.claude/hooks/skills-picker-overrides.json
            ├─ write ~/.claude/cache/skills-catalog.json
            └─ spawn detached GUI         ── skills-picker.py
                    └─> writes selection to ~/.claude/cache/skills-pending-<sid>.txt
        ^ launcher exits in <100 ms; Claude TUI never blocks

user types first message
    └─> UserPromptSubmit hook (sync)      ── skills-inject.py
            └─> reads pending file, emits additionalContext, deletes file
        ^ ~40 ms; runs once per session, silent thereafter

Claude sees the activation instruction in its context and invokes the
Skill tool for each pick in parallel before responding.
```

Key design choices:

- **`SessionStart` with `"async": true`** — hook returns immediately so the Claude Code TUI starts unblocked.
- **GUI runs in its own OS window** — the picker never touches `/dev/tty` or the Claude Code terminal, so there is no rendering conflict, no curses-vs-TUI fight, no freeze.
- **Selection delivered via `UserPromptSubmit` injection** — by the time Claude reads its first user prompt, the pending file is either present (inject + delete) or absent (no-op). Either way the inject hook runs in tens of milliseconds.

---

## Customize: the overrides file

Skill discovery is automatic — install a new user skill or enable a new plugin and it appears in the dialog next session. But some things can't be discovered from disk alone (built-in skills with no on-disk presence; per-skill mode dropdowns; skills you want hidden from the picker). Those go in `~/.claude/hooks/skills-picker-overrides.json`:

```json
{
  "include_builtins": [
    { "name": "claude-api",      "description": "Anthropic SDK / Claude API focus" },
    { "name": "security-review", "description": "security audit mode" }
  ],

  "args": {
    "caveman:caveman": {
      "choices": ["lite", "full", "ultra"],
      "default": "full"
    }
  },

  "labels": {
    "caveman:caveman": "caveman  (compression mode)"
  },

  "hide": [
    "caveman:caveman-help",
    "caveman:caveman-stats"
  ]
}
```

| Field | Effect |
|---|---|
| `include_builtins` | Add skills that don't have an on-disk `SKILL.md` (built-ins shipped by Claude Code itself). |
| `args` | Show a dropdown next to a skill's checkbox so the user picks one mode. The arg is appended to the Skill tool call. |
| `labels` | Override the display name for a skill. Useful for `caveman:caveman` → `caveman (compression mode)`. |
| `hide` | Suppress skills you don't want cluttering the dialog (e.g. utility variants like `caveman:caveman-help`). |

The installer copies a default `skills-picker-overrides.json` into `~/.claude/hooks/` the first time. On reinstall it leaves your customized file alone — delete it if you want the defaults back.

---

## Disable temporarily

Set an environment variable in the shell that launches Claude Code:

```bash
# macOS / shell
export CLAUDE_SKILLS_PICKER=off

# Windows PowerShell
$env:CLAUDE_SKILLS_PICKER = "off"
```

Both hooks short-circuit when this is `off`, `0`, `false`, or `no`. Unset to re-enable.

You can also extend the picker's auto-close timeout (default 60 seconds) if you want more time to think:

```bash
export CLAUDE_SKILLS_PICKER_TIMEOUT=180   # 3 minutes
```

---

## Uninstall

Delete the scripts and the two hook entries:

```bash
# macOS
rm ~/.claude/hooks/skills-launch.py
rm ~/.claude/hooks/skills-picker.py
rm ~/.claude/hooks/skills-inject.py
rm ~/.claude/hooks/skills-picker-overrides.json
# then edit ~/.claude/settings.json, remove the SessionStart and UserPromptSubmit
# entries that reference skills-launch.py / skills-inject.py
```

```powershell
# Windows
Remove-Item "$env:USERPROFILE\.claude\hooks\skills-launch.py"
Remove-Item "$env:USERPROFILE\.claude\hooks\skills-picker.py"
Remove-Item "$env:USERPROFILE\.claude\hooks\skills-inject.py"
Remove-Item "$env:USERPROFILE\.claude\hooks\skills-picker-overrides.json"
# then edit %USERPROFILE%\.claude\settings.json the same way
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Dialog never appears (macOS) | `osascript` blocked by enterprise MDM | Pre-approve `osascript` in your security profile, or test by running the picker manually: `python3 ~/.claude/hooks/skills-picker.py /tmp/test.txt ~/.claude/cache/skills-catalog.json` (the catalog is rebuilt on each new session) |
| Dialog never appears (Windows) | `python` not on PATH, or sandboxed Microsoft-Store Python | Install Python 3 from python.org (check "Add to PATH"), rerun `install.ps1` |
| Dialog appears but selections aren't activated | `UserPromptSubmit` hook missing or pointing elsewhere | Open `~/.claude/settings.json`, confirm both `SessionStart` and `UserPromptSubmit` entries reference the scripts |
| Need to inspect picker errors | Logs at `~/.claude/cache/skills-picker-<session_id>.log` | Open in any editor |
| Want to force re-show this session | Delete the marker: `rm ~/.claude/cache/skills-spawned-<sid>.txt`, then send a new prompt | |
| Dialog appears when you wake the laptop, even though you haven't started a new session | Pre-v3.1 pickers were detached and outlived their parent Claude Code session. macOS re-presented their windows on wake. v3.1+ auto-closes the picker after 60 seconds; upgrade and run the zombie cleanup below | |
| Picker takes >60s to interact with | Auto-close timeout is too short for you | Set `CLAUDE_SKILLS_PICKER_TIMEOUT=180` (or any positive integer in seconds) in your shell |

### Zombie picker cleanup (one-shot, when upgrading from a version before v3.1)

If picker dialogs from old sessions kept piling up before you upgraded, sweep them away once:

```bash
# macOS / Linux
pkill -f skills-picker.py
rm -f ~/.claude/cache/skills-spawned-*.txt \
      ~/.claude/cache/skills-pending-*.txt \
      ~/.claude/cache/skills-picker-*.log
```

```powershell
# Windows
Get-Process python* -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match 'skills-picker.py' } |
    Stop-Process -Force
Remove-Item -ErrorAction SilentlyContinue `
    "$env:USERPROFILE\.claude\cache\skills-spawned-*.txt", `
    "$env:USERPROFILE\.claude\cache\skills-pending-*.txt", `
    "$env:USERPROFILE\.claude\cache\skills-picker-*.log"
```

After v3.1 this is a non-issue — the picker self-destructs after 60 seconds.

---

## Why a session-startup picker?

If you keep several Claude Code skills (caveman compression mode, language-specific helpers, security review, etc.) you usually want a couple active per session and the rest dormant. Typing `/skill-name` three times at the start of every session gets tedious; auto-activating everything pollutes the context window.

This hook puts the choice in one click, once, at the right moment — without disturbing the Claude Code TUI.

---

## License

MIT. See [LICENSE](LICENSE) if present, otherwise treat as MIT.
