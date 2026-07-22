
# Claude Session Skill Picker

A pair of [Claude Code](https://claude.ai/code) hooks that pop a checkbox dialog at the start of every session so you can pick which skills to activate. Picks get injected as context on your first message — Claude turns them on before replying.

Also connects to **Codex** (ChatGPT's coding agent) and **OpenCode** — same dialog, same skill catalog, picked skills get activated there too.

- Same dialog on macOS and Windows: rendered as HTML/CSS in a native webview (via the optional `pywebview` package) — falls back automatically to a plain native dialog (NSAlert on macOS, tkinter on Windows) if `pywebview` isn't installed
- Auto-discovers installed user skills and enabled plugin skills every session
- Skills with multiple modes (e.g. `lite | full | ultra`) get a dropdown next to the checkbox
- Check "Auto-select these picks next session" to carry your selections forward without re-picking
- **Bring your own skill repos** — add a GitHub repo URL in ⚙ Settings and its `SKILL.md` files show up in the catalog alongside your local ones, grouped by repo
- **Connect/disconnect Codex and OpenCode** from ⚙ Settings — a checkbox per detected agent, wired straight to that agent's own hook/plugin mechanism, no separate install step needed once they're detected
- **"Skill Picker Settings" app on your Desktop** (added automatically on install) — double-click to jump straight to Settings any time, e.g. to reconnect an agent, without waiting for a new Claude Code session. No terminal, no console window.
- ⚙ Settings button — connected agents, skill repos, uninstall, plus account/subscription info (placeholder today, accounts aren't built yet)

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

### Also connect OpenCode

Also requires the Claude Code install above (OpenCode's plugin reuses the
same `skills-launch.py`).

```bash
python3 adapters/opencode.py install
```

- OpenCode has no trust-approval step — the plugin just needs to be on disk
  before OpenCode starts.
- **Fully quit OpenCode (Cmd+Q, not just closing the window) and relaunch,
  then start a new chat.** Same reason as Codex above: it only reads its
  plugins directory at its own process startup, not per new chat tab.
- Re-run `python3 adapters/opencode.py install` any time to re-sync — safe
  to run repeatedly.

### Managing connected agents from Settings

Once Codex and/or OpenCode are detected on your machine, ⚙ Settings shows a
checkbox for each — toggle either on/off any time without touching the
command line. This calls the same `install()`/`uninstall()` shown above,
just from the UI.

To open Settings without waiting for a new session, double-click **"Skill
Picker Settings"** on your Desktop (added automatically by the installer).
It opens the picker straight to the Settings panel — no terminal, no
console window.

---

## Skill repos

Add any GitHub repo containing `SKILL.md` files (at the repo root or under a
`skills/` folder) from ⚙ Settings → Skill Repos. It's shallow-cloned into
`~/.claude/cache/skill-repos/`, scanned alongside your local skills, and
shown in the picker grouped by `owner/repo`. Refreshing is manual (a
"Refresh" button in the same section) — repos are never re-fetched
automatically on every session start.

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

Removes the installed scripts, cache files, adapters, and Desktop shortcut,
and only this project's entries from `~/.claude/settings.json` — anything
else you have configured there is left untouched. Any connected agent
(Codex, OpenCode) is disconnected automatically before its files are removed
— you don't need to disconnect them separately first.

To disconnect just one agent without uninstalling everything else, use its
checkbox in ⚙ Settings, or run its adapter directly:
`python3 adapters/codex.py uninstall` / `python3 adapters/opencode.py uninstall`
(run from the repo checkout).

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Dialog never appears (macOS) | Run manually to see errors: `python3 ~/.claude/hooks/skills-picker.py /tmp/test.txt ~/.claude/cache/skills-catalog.json` |
| Dialog never appears (Windows) | Install Python 3 from python.org with "Add to PATH" checked, rerun `install.ps1` |
| Selections don't seem to activate | Check `~/.claude/settings.json` has both hook entries pointing at the right scripts |
| Codex: dialog never appears | See "Special cases for Codex" above — usually a missing `/hooks` trust approval or a stale `app-server` process |
| OpenCode: picked skill doesn't seem active | Fully quit (Cmd+Q) and relaunch OpenCode, then start a genuinely new chat — same stale-process cause as Codex above |
| Settings checkboxes are empty when opened via the Desktop shortcut | Update to the latest version — earlier builds had a race between the panel opening and the webview bridge being ready |
| Picker logs | `~/.claude/cache/skills-picker-<session_id>.log` |

---

## License

See [LICENSE](LICENSE).
