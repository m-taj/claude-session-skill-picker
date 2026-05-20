# Claude Session Skill Picker

A `UserPromptSubmit` hook for [Claude Code](https://claude.ai/code) that pops up a skill selector at the start of each new session. On macOS it shows a native dialog; on other platforms it falls back to a numbered text menu in the terminal.

![Demo placeholder — screenshot of the native macOS skill picker dialog](./images/demo.png)

---

## Prerequisites

- [Claude Code](https://claude.ai/code) installed and configured
- macOS (for the native dialog) **or** any platform with `/dev/tty` access (for the text fallback)
- `jq` for the automated installer (`brew install jq`)

---

## Install

### Option A — One-liner (after cloning)

```bash
git clone https://github.com/m-taj/claude-session-skill-picker.git
cd claude-session-skill-picker
bash install.sh
```

### Option B — Manual (no clone needed)

**1. Create the hooks directory**

```bash
mkdir -p ~/.claude/hooks
```

**2. Download the hook script**

```bash
curl -fsSL https://raw.githubusercontent.com/YOUR_USERNAME/claude-session-skill-picker/main/startup-skills.sh \
  -o ~/.claude/hooks/startup-skills.sh
chmod +x ~/.claude/hooks/startup-skills.sh
```

**3. Register the hook in Claude Code settings**

Open `~/.claude/settings.json` (create it if it doesn't exist) and add the following. If `hooks` already exists, merge the `UserPromptSubmit` entry into it.

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "bash ~/.claude/hooks/startup-skills.sh"
          }
        ]
      }
    ]
  }
}
```

**4. Verify**

```bash
cat ~/.claude/hooks/startup-skills.sh | head -5
```

Start a new Claude Code session — the picker should appear on your first message.

---

## How it works

1. `UserPromptSubmit` fires when you send any message
2. The script checks a session marker file (`/tmp/claude_session_skills_<session_id>`) — if it exists the picker is skipped, so it only runs once per session
3. You select skills from the dialog
4. The script outputs an activation instruction to stdout, which Claude Code injects into Claude's context before processing your message
5. Claude activates the selected skills, then handles your original message

---

## Customize: add or remove skills

Edit `~/.claude/hooks/startup-skills.sh`. The two arrays must stay in sync — `SKILL_DIALOG` holds the display labels, `SKILL_KEYS` holds the skill identifiers Claude receives.

```bash
SKILL_DIALOG=(
  "caveman full — terse compressed output (~75% fewer tokens)"
  "my-skill — description shown in the picker"
  # add more here
)

SKILL_KEYS=(
  "caveman full"
  "my-skill"
  # matching key for each dialog entry above
)
```

Skill keys must match whatever skill name Claude Code recognizes (e.g. the name you'd type in `/skill-name`).

---

## Uninstall

```bash
rm ~/.claude/hooks/startup-skills.sh
```

Then remove the `UserPromptSubmit` hook entry from `~/.claude/settings.json`.

---

## Platform notes

| Platform | UI |
|---|---|
| macOS | Native Cocoa dialog via `osascript` |
| Linux / Windows WSL | Numbered text menu via `/dev/tty` |

The text fallback works by printing a numbered list to the terminal and reading your input. Type a number to toggle that skill on or off, then press Enter to confirm. Type `skip` to activate nothing.
