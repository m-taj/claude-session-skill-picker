# Claude Session Skill Picker

A pair of [Claude Code](https://claude.ai/code) hooks that show a checkbox dialog at the start of every session so you can choose which skills to activate. Selections are injected as context on your first message, before Claude replies.

Also connects to **Codex** (ChatGPT's coding agent) and **OpenCode** — same dialog, same skill catalog, activated in whichever agent you're using.

## Features

- Same dialog on macOS and Windows, rendered as HTML/CSS in a native webview (via the optional `pywebview` package), with automatic fallback to a plain native dialog (NSAlert on macOS, tkinter on Windows) if `pywebview` isn't installed
- Auto-discovers installed user skills and enabled plugin skills every session
- Skills with multiple modes (e.g. `lite | full | ultra`) get a dropdown next to the checkbox
- "Auto-select these picks next session" carries your selections forward without re-picking
- Add a GitHub repo URL in Settings and its `SKILL.md` files join the catalog, grouped by repo
- Connect or disconnect Codex and OpenCode from Settings — one checkbox per detected agent
- A double-click Desktop shortcut opens Settings directly, with no terminal required

> First run after install may take ~2 seconds longer than usual — that's macOS/Windows initializing the webview runtime for the first time, not a recurring cost.

---

## What it looks like

| macOS | Windows |
|---|---|
|<img width="867" height="454" alt="Screenshot 2026-06-01 at 2 55 22 PM" src="https://github.com/user-attachments/assets/1ae64e00-51fe-44af-a14b-8b2f865d9c36" />
| ![Windows dialog](images/win.png) |

---

## Prerequisites

| Platform | Requirement |
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

### Codex

Requires the Claude Code install above (Codex reuses those same hook scripts rather than duplicating them).

```bash
python3 adapters/codex.py install
```

**Known limitations:**

- New hooks require a one-time manual trust approval, and it only works from a real terminal. Run `codex` (or the full path printed by the install command) in Terminal, type `/hooks`, and approve the two new entries. Typing `/hooks` into the ChatGPT desktop app's chat box does not work — it is answered as a normal chat message rather than opening the review UI. This is a limitation of Codex itself.
- If the ChatGPT desktop app was already running, fully quit it (Cmd+Q, not just closing the window) and relaunch. Its background `app-server` process only reads `hooks.json` at its own startup, not per new chat tab.
- Re-running `python3 adapters/codex.py install` is safe at any time — it won't duplicate entries or touch unrelated hooks you already have configured.

### OpenCode

Also requires the Claude Code install above (OpenCode's plugin reuses `skills-launch.py`).

```bash
python3 adapters/opencode.py install
```

- No trust-approval step — the plugin only needs to be on disk before OpenCode starts.
- Fully quit OpenCode (Cmd+Q, not just closing the window), relaunch, and start a new chat. Same reason as Codex above: it only reads its plugins directory at its own process startup.
- Re-running `python3 adapters/opencode.py install` is safe at any time.

### Managing connected agents

Once Codex and/or OpenCode are detected, the Settings panel (⚙) shows a checkbox for each — toggle either on or off without touching the command line.

To open Settings without waiting for a new session, double-click **Skill Picker Settings** on your Desktop (added automatically by the installer).

---

## Skill repos

Add any GitHub repo containing `SKILL.md` files (at the repo root or under a `skills/` folder) from Settings → Skill Repos. It's shallow-cloned into `~/.claude/cache/skill-repos/`, scanned alongside your local skills, and shown in the picker grouped by `owner/repo`. Refreshing is manual — repos are never re-fetched automatically on session start.

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

Removes the installed scripts, cache files, adapters, and Desktop shortcut, and only this project's entries from `~/.claude/settings.json` — anything else you have configured there is left untouched. Any connected agent (Codex, OpenCode) is disconnected automatically first.

To disconnect a single agent without a full uninstall, use its checkbox in Settings, or run its adapter directly (`python3 adapters/codex.py uninstall` / `python3 adapters/opencode.py uninstall`, from the repo checkout).

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Dialog never appears (macOS) | Run manually to see errors: `python3 ~/.claude/hooks/skills-picker.py /tmp/test.txt ~/.claude/cache/skills-catalog.json` |
| Dialog never appears (Windows) | Install Python 3 from python.org with "Add to PATH" checked, rerun `install.ps1` |
| Selections don't seem to activate | Check `~/.claude/settings.json` has both hook entries pointing at the right scripts |
| Codex: dialog never appears | See Codex limitations above — usually a missing `/hooks` trust approval or a stale `app-server` process |
| OpenCode: picked skill doesn't seem active | Fully quit (Cmd+Q) and relaunch OpenCode, then start a genuinely new chat |
| Picker logs | `~/.claude/cache/skills-picker-<session_id>.log` |

---

## License

See [LICENSE](LICENSE).
