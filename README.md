
# Claude Session Skill Picker

A pair of [Claude Code](https://claude.ai/code) hooks that pop a **native checkbox dialog** at the start of every session so you can pick which skills to activate. Picks get injected as context on your first message — Claude turns them on before replying.

- macOS: native NSAlert with real checkbox accessory view (via JXA + Cocoa, no install)
- Windows: tkinter checkbox dialog (ships with the python.org installer, no extra install)

No more `/caveman:caveman ultra` typing every session. No terminal UI conflicts. No freezing on startup.

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

Both installers do the same three things:

1. Copy `skills-launch.py`, `skills-picker.py`, `skills-inject.py` into `~/.claude/hooks/`
2. Add a `SessionStart` (async) and a `UserPromptSubmit` (sync) hook entry to `~/.claude/settings.json`
3. Print next steps

Start a new Claude Code session — the dialog appears.

---

## How it works

Three small Python scripts wired into two hook events:

```
session starts
    └─> SessionStart hook (async)         ── skills-launch.py
            └─> spawns detached GUI       ── skills-picker.py
                    └─> writes selection to ~/.claude/cache/skills-pending-<sid>.txt
        ^ launcher exits in ~45 ms; Claude TUI never blocks

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

## Customize: add or remove skills

Edit `~/.claude/hooks/skills-picker.py` — the `SKILLS` list at the top:

```python
SKILLS = [
    ("caveman full",  "terse output (~75% fewer tokens)"),
    ("claude-api",    "Anthropic SDK / Claude API focus"),
    ("my-own-skill",  "what it does, shown in the dialog"),
    # …
]
```

Then add a matching entry in `~/.claude/hooks/skills-inject.py` → `ACTIVATION_MAP`:

```python
ACTIVATION_MAP = {
    "my-own-skill": ("my-own-skill", None),         # no arg
    "caveman full": ("caveman:caveman", "full"),    # with arg
    # …
}
```

The first key in the tuple is the skill name Claude invokes via the `Skill` tool; the second is an optional `args` value.

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

---

## Uninstall

Delete the scripts and the two hook entries:

```bash
# macOS
rm ~/.claude/hooks/skills-launch.py
rm ~/.claude/hooks/skills-picker.py
rm ~/.claude/hooks/skills-inject.py
# then edit ~/.claude/settings.json, remove the SessionStart and UserPromptSubmit
# entries that reference skills-launch.py / skills-inject.py
```

```powershell
# Windows
Remove-Item "$env:USERPROFILE\.claude\hooks\skills-launch.py"
Remove-Item "$env:USERPROFILE\.claude\hooks\skills-picker.py"
Remove-Item "$env:USERPROFILE\.claude\hooks\skills-inject.py"
# then edit %USERPROFILE%\.claude\settings.json the same way
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Dialog never appears (macOS) | `osascript` blocked by enterprise MDM | Pre-approve `osascript` in your security profile, or test by running the picker manually: `python3 ~/.claude/hooks/skills-picker.py /tmp/test.txt` |
| Dialog never appears (Windows) | `python` not on PATH, or sandboxed Microsoft-Store Python | Install Python 3 from python.org (check "Add to PATH"), rerun `install.ps1` |
| Dialog appears but selections aren't activated | `UserPromptSubmit` hook missing or pointing elsewhere | Open `~/.claude/settings.json`, confirm both `SessionStart` and `UserPromptSubmit` entries reference the scripts |
| Need to inspect picker errors | Logs at `~/.claude/cache/skills-picker-<session_id>.log` | Open in any editor |
| Want to force re-show this session | Delete the marker: `rm ~/.claude/cache/skills-spawned-<sid>.txt`, then send a new prompt | |

---

## Why a session-startup picker?

If you keep several Claude Code skills (caveman compression mode, language-specific helpers, security review, etc.) you usually want a couple active per session and the rest dormant. Typing `/skill-name` three times at the start of every session gets tedious; auto-activating everything pollutes the context window.

This hook puts the choice in one click, once, at the right moment — without disturbing the Claude Code TUI.

---

## License

MIT. See [LICENSE](LICENSE) if present, otherwise treat as MIT.
