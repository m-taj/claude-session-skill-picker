#!/bin/bash
set -e

HOOK_DIR="$HOME/.claude/hooks"
HOOK_FILE="$HOOK_DIR/startup-skills.sh"
SETTINGS="$HOME/.claude/settings.json"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing Claude session skill picker..."

# ── 1. Copy hook script ───────────────────────────────────────────────────────
mkdir -p "$HOOK_DIR"
cp "$SCRIPT_DIR/startup-skills.sh" "$HOOK_FILE"
chmod +x "$HOOK_FILE"
echo "  ✓ Hook script installed at $HOOK_FILE"

# ── 2. Patch settings.json ────────────────────────────────────────────────────
if ! command -v jq &>/dev/null; then
  echo ""
  echo "  ⚠ jq not found — add the hook manually to $SETTINGS:"
  echo ""
  echo '  "hooks": {'
  echo '    "UserPromptSubmit": ['
  echo '      {'
  echo '        "matcher": "",'
  echo '        "hooks": [{ "type": "command", "command": "bash ~/.claude/hooks/startup-skills.sh" }]'
  echo '      }'
  echo '    ]'
  echo '  }'
  echo ""
  exit 0
fi

# Create settings.json if it doesn't exist
if [ ! -f "$SETTINGS" ]; then
  echo '{}' > "$SETTINGS"
fi

# Check if hook is already registered
if jq -e '.hooks.UserPromptSubmit[]?.hooks[]? | select(.command | contains("startup-skills.sh"))' "$SETTINGS" &>/dev/null; then
  echo "  ✓ Hook already registered in settings.json — skipping"
else
  HOOK_ENTRY='{
    "matcher": "",
    "hooks": [{ "type": "command", "command": "bash ~/.claude/hooks/startup-skills.sh" }]
  }'

  UPDATED=$(jq --argjson entry "$HOOK_ENTRY" '
    .hooks.UserPromptSubmit = ((.hooks.UserPromptSubmit // []) + [$entry])
  ' "$SETTINGS")

  echo "$UPDATED" > "$SETTINGS"
  echo "  ✓ Hook registered in $SETTINGS"
fi

echo ""
echo "Done. Start a new Claude Code session to see the skill picker."
