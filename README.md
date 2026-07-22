
# Claude Session Skill Picker

A pair of [Claude Code](https://claude.ai/code) hooks that pop a checkbox dialog at the start of every session so you can pick which skills to activate. Picks get injected as context on your first message — Claude turns them on before replying.

Also connects to **Codex** (ChatGPT's coding agent) — same dialog, same skill catalog, picked skills get activated there too.

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
|<img width="867" height="454" alt="Screenshot 2026-06-01 at 2 55 22 PM" src="https://github.com/user-attachments/assets/1ae64e00-51fe-44af-a14b-8b2f865d9c36" />
| ![Windows dialog](images/win.png) |

---

## Prerequisites

| Platform | Need |
|---|---|
| macOS | Python 3 (preinstalled); `jq` for auto-install (`brew install jq`) |
| Windows | Python 3 from [python.org](https://www.python.org/downloads/); PowerShell 5+ |

---

## Installation

### Claude Code — macOS

```bash
git clone https://github.com/m-taj/claude-session-skill-picker.git
cd claude-session-skill-picker
bash install.sh
```

### Claude Code — Windows

```powershell
git clone https://github.com/m-taj/claude-session-skill-picker.git
cd claude-session-skill-picker
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Start a new Claude Code session — the dialog appears.

### Also connect Codex

Requires the Claude Code install above to be done first (Codex reuses those
same hook scripts rather than duplicating them).

```bash
python3 adapters/codex.py install
```

**Special cases for Codex / the ChatGPT app — read before you file a "it's not
working" issue:**

- **New hooks require a one-time manual trust approval, and it only works
  from a real Terminal.** Run `codex` (or the full path printed by the
  install command above) in Terminal, type `/hooks`, and approve the two new
  entries. Typing `/hooks` into the **ChatGPT desktop app's chat box does
  not work** — it gets answered as a normal chat message instead of opening
  the actual review UI. This is a limitation of Codex itself, not something
  this installer can fix.
- **If the ChatGPT desktop app was already running, fully quit it (Cmd+Q,
  not just closing the window) and relaunch.** Its background `app-server`
  process only reads `hooks.json` at its own startup, not per new chat tab —
  a hook written while it's already running won't be picked up until it
  restarts.
- Re-run `python3 adapters/codex.py install` any time to re-sync the hook
  (e.g. after updating this repo) — it's safe to run repeatedly and won't
  duplicate entries or touch unrelated hooks you already have configured.

---

## Disable / adjust timeout

```bash
export CLAUDE_SKILLS_PICKER=off              # skip the dialog entirely
export CLAUDE_SKILLS_PICKER_TIMEOUT=180      # auto-close after N seconds (default 60)
```

Windows: `$env:CLAUDE_SKILLS_PICKER = "off"`

---

## Uninstall

Use the ⚙ Settings button in the dialog, or run the script directly:

```bash
bash ~/.claude/hooks/uninstall.sh          # macOS
```

```powershell
powershell -ExecutionPolicy Bypass -File ~\.claude\hooks\uninstall.ps1   # Windows
```

Removes the installed scripts, cache files, and only this project's entries
from `~/.claude/settings.json` — anything else you have configured there is
left untouched.

If you also connected Codex: `python3 adapters/codex.py uninstall` (run from
the repo checkout) removes its hook entries the same way.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Dialog never appears (macOS) | Run manually to see errors: `python3 ~/.claude/hooks/skills-picker.py /tmp/test.txt ~/.claude/cache/skills-catalog.json` |
| Dialog never appears (Windows) | Install Python 3 from python.org with "Add to PATH" checked, rerun `install.ps1` |
| Selections don't seem to activate | Check `~/.claude/settings.json` has both hook entries pointing at the right scripts |
| Codex: dialog never appears | See "Special cases for Codex" above — usually a missing `/hooks` trust approval or a stale `app-server` process |
| Picker logs | `~/.claude/cache/skills-picker-<session_id>.log` |

---

## License

See [LICENSE](LICENSE).
