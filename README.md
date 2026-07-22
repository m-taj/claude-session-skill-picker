
# Claude Session Skill Picker

A pair of [Claude Code](https://claude.ai/code) hooks that pop a checkbox dialog at the start of every session so you can pick which skills to activate. Picks get injected as context on your first message — Claude turns them on before replying.

- Same dialog on macOS and Windows: rendered as HTML/CSS in a native webview (via the optional `pywebview` package) — falls back automatically to a plain native dialog (NSAlert on macOS, tkinter on Windows) if `pywebview` isn't installed
- Auto-discovers installed user skills and enabled plugin skills every session
- Skills with multiple modes (e.g. `lite | full | ultra`) get a dropdown next to the checkbox
- Check "Auto-select these picks next session" to carry your selections forward without re-picking
- ⚙ Settings button — uninstall, plus account/subscription info (placeholder today, accounts aren't built yet)

> First run after install may take ~2 seconds longer than usual — that's macOS/Windows initializing the webview runtime for the first time, not a recurring cost.

---

## What it looks like

| macOS | Windows |
|---|---|
| ![macOS dialog](images/mac.png) | ![Windows dialog](images/win.png) |

---

## Prerequisites

| Platform | Need |
|---|---|
| macOS | Python 3 (preinstalled); `jq` for auto-install (`brew install jq`) |
| Windows | Python 3 from [python.org](https://www.python.org/downloads/); PowerShell 5+ |

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

Start a new Claude Code session — the dialog appears.

---

## Customize: the overrides file

Skill discovery is automatic. For anything discovery can't see on disk — built-in
skills, per-skill mode dropdowns, skills you want hidden — edit
`~/.claude/hooks/skills-picker-overrides.json`:

```json
{
  "include_builtins": [
    { "name": "claude-api", "description": "Anthropic SDK / Claude API focus" }
  ],
  "args": {
    "caveman:caveman": { "choices": ["lite", "full", "ultra"], "default": "full" }
  },
  "labels": {
    "caveman:caveman": "caveman  (compression mode)"
  },
  "hide": ["caveman:caveman-help"]
}
```

The installer copies a default the first time and never overwrites your edits on
reinstall.

---

## Disable / adjust timeout

```bash
export CLAUDE_SKILLS_PICKER=off              # skip the dialog entirely
export CLAUDE_SKILLS_PICKER_TIMEOUT=180      # auto-close after N seconds (default 60)
```

Windows: `$env:CLAUDE_SKILLS_PICKER = "off"`

---

## Uninstall

```bash
rm ~/.claude/hooks/skills-launch.py ~/.claude/hooks/skills-picker.py \
   ~/.claude/hooks/skills-inject.py ~/.claude/hooks/skills-picker-overrides.json
# then remove the SessionStart / UserPromptSubmit entries in ~/.claude/settings.json
```

A one-command uninstall script is planned — see the project plan for status.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Dialog never appears (macOS) | Run manually to see errors: `python3 ~/.claude/hooks/skills-picker.py /tmp/test.txt ~/.claude/cache/skills-catalog.json` |
| Dialog never appears (Windows) | Install Python 3 from python.org with "Add to PATH" checked, rerun `install.ps1` |
| Selections don't seem to activate | Check `~/.claude/settings.json` has both hook entries pointing at the right scripts |
| Picker logs | `~/.claude/cache/skills-picker-<session_id>.log` |

---

## License

See [LICENSE](LICENSE).
