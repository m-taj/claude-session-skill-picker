#!/bin/bash
# Installer for claude-session-skill-picker on macOS.
set -e

HOOK_DIR="$HOME/.claude/hooks"
SETTINGS="$HOME/.claude/settings.json"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing claude-session-skill-picker..."

# ── 1. Sanity checks ──────────────────────────────────────────────────────────
if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "  This installer is for macOS. For Windows, run install.ps1 in PowerShell."
    exit 1
fi

PY=$(command -v python3 || true)
if [[ -z "$PY" ]]; then
    echo "  ✗ python3 not found. Install Python 3 (e.g. 'brew install python') and rerun."
    exit 1
fi
echo "  ✓ python3 found at $PY"

if ! command -v jq &>/dev/null; then
    echo ""
    echo "  ⚠ jq not found. Install with 'brew install jq' OR add this hook block"
    echo "    to $SETTINGS manually:"
    echo ""
    cat <<EOF
    "hooks": {
      "SessionStart": [
        { "matcher": "",
          "hooks": [{ "type": "command",
                      "command": "python3 ~/.claude/hooks/skills-launch.py",
                      "async": true }] }
      ],
      "UserPromptSubmit": [
        { "matcher": "",
          "hooks": [{ "type": "command",
                      "command": "python3 ~/.claude/hooks/skills-inject.py",
                      "timeout": 5 }] }
      ]
    }
EOF
    NO_JQ=1
else
    NO_JQ=0
fi

# ── 2. Copy scripts ───────────────────────────────────────────────────────────
mkdir -p "$HOOK_DIR"
for f in skills-launch.py skills-picker.py skills-inject.py; do
    cp "$SCRIPT_DIR/$f" "$HOOK_DIR/$f"
    chmod +x "$HOOK_DIR/$f"
    echo "  ✓ Installed $HOOK_DIR/$f"
done

# ── 3. Patch settings.json ────────────────────────────────────────────────────
if [[ "$NO_JQ" == "1" ]]; then
    echo ""
    echo "Done (scripts installed; add the hooks block manually then start a new session)."
    exit 0
fi

mkdir -p "$(dirname "$SETTINGS")"
[[ -f "$SETTINGS" ]] || echo '{}' > "$SETTINGS"

LAUNCH_ENTRY='{
  "matcher": "",
  "hooks": [{ "type": "command",
              "command": "python3 ~/.claude/hooks/skills-launch.py",
              "async": true }]
}'
INJECT_ENTRY='{
  "matcher": "",
  "hooks": [{ "type": "command",
              "command": "python3 ~/.claude/hooks/skills-inject.py",
              "timeout": 5 }]
}'

UPDATED=$(jq \
    --argjson launch "$LAUNCH_ENTRY" \
    --argjson inject "$INJECT_ENTRY" '
    .hooks //= {}
    | .hooks.SessionStart =
        (((.hooks.SessionStart // []) | map(select(
            (.hooks // []) | all(.command | contains("skills-launch.py") | not)
        ))) + [$launch])
    | .hooks.UserPromptSubmit =
        (((.hooks.UserPromptSubmit // []) | map(select(
            (.hooks // []) | all(.command | contains("skills-inject.py") | not)
        ))) + [$inject])
' "$SETTINGS")

printf '%s\n' "$UPDATED" > "$SETTINGS"
echo "  ✓ Patched $SETTINGS"

echo ""
echo "Done. Start a new Claude Code session to see the skill picker."
echo "Disable temporarily with: export CLAUDE_SKILLS_PICKER=off"
