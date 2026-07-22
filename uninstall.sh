#!/bin/bash
# Uninstaller for claude-session-skill-picker on macOS. Mirrors install.sh in reverse.
set -e

HOOK_DIR="$HOME/.claude/hooks"
SETTINGS="$HOME/.claude/settings.json"
CACHE_DIR="$HOME/.claude/cache"

echo "Uninstalling claude-session-skill-picker..."

# ── 1. Remove installed scripts + assets ──────────────────────────────────────
for f in skills-launch.py skills-picker.py skills-inject.py skills-picker-overrides.json; do
    if [[ -f "$HOOK_DIR/$f" ]]; then
        rm -f "$HOOK_DIR/$f"
        echo "  ✓ Removed $HOOK_DIR/$f"
    fi
done
if [[ -d "$HOOK_DIR/images" ]]; then
    rm -rf "$HOOK_DIR/images"
    echo "  ✓ Removed $HOOK_DIR/images"
fi

# ── 2. Clear cache/state files ────────────────────────────────────────────────
rm -f "$CACHE_DIR"/skills-catalog.json \
      "$CACHE_DIR"/skills-remembered-picks.json \
      "$CACHE_DIR"/skills-spawned-*.txt \
      "$CACHE_DIR"/skills-pending-*.txt \
      "$CACHE_DIR"/skills-picker-*.log 2>/dev/null || true
echo "  ✓ Cleared cache files"

# ── 3. Strip the hook entries from settings.json ──────────────────────────────
if command -v jq &>/dev/null && [[ -f "$SETTINGS" ]]; then
    UPDATED=$(jq '
        .hooks.SessionStart = ((.hooks.SessionStart // []) | map(select(
            (.hooks // []) | all(.command | contains("skills-launch.py") | not)
        )))
        | .hooks.UserPromptSubmit = ((.hooks.UserPromptSubmit // []) | map(select(
            (.hooks // []) | all(.command | contains("skills-inject.py") | not)
        )))
    ' "$SETTINGS")
    printf '%s\n' "$UPDATED" > "$SETTINGS"
    echo "  ✓ Removed hook entries from $SETTINGS"
else
    echo "  ⚠ jq not found (or no settings.json) — remove the SessionStart /"
    echo "    UserPromptSubmit entries referencing skills-launch.py / skills-inject.py"
    echo "    from $SETTINGS manually."
fi

echo ""
echo "Done. Skill picker removed. Restart Claude Code to complete."

# Remove self last — safe on POSIX systems even while this script is running.
rm -f "$HOOK_DIR/uninstall.sh" 2>/dev/null || true
