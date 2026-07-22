#!/bin/bash
# Uninstaller for claude-session-skill-picker on macOS. Mirrors install.sh in reverse.
set -e

HOOK_DIR="$HOME/.claude/hooks"
SETTINGS="$HOME/.claude/settings.json"
CACHE_DIR="$HOME/.claude/cache"

echo "Uninstalling claude-session-skill-picker..."

# ── 1. Disconnect any connected agents first ──────────────────────────────────
# Each adapter's own uninstall() strips only its own hook/plugin entries —
# never touches unrelated hooks/config the user has for that agent.
if [[ -d "$HOOK_DIR/adapters" ]]; then
    PY=$(command -v python3 || true)
    if [[ -n "$PY" ]]; then
        for adapter in "$HOOK_DIR"/adapters/*.py; do
            [[ -f "$adapter" ]] || continue
            "$PY" "$adapter" uninstall 2>/dev/null || true
        done
    fi
fi

# ── 2. Remove installed scripts + assets ──────────────────────────────────────
for f in skills-launch.py skills-picker.py skills-inject.py skills-settings.py skills-picker-overrides.json; do
    if [[ -f "$HOOK_DIR/$f" ]]; then
        rm -f "$HOOK_DIR/$f"
        echo "  ✓ Removed $HOOK_DIR/$f"
    fi
done
if [[ -d "$HOOK_DIR/images" ]]; then
    rm -rf "$HOOK_DIR/images"
    echo "  ✓ Removed $HOOK_DIR/images"
fi
if [[ -d "$HOOK_DIR/adapters" ]]; then
    rm -rf "$HOOK_DIR/adapters"
    echo "  ✓ Removed $HOOK_DIR/adapters"
fi
if [[ -f "$HOME/Desktop/Skill Picker Settings.command" ]]; then
    rm -f "$HOME/Desktop/Skill Picker Settings.command"
    echo "  ✓ Removed Desktop shortcut"
fi

# ── 3. Clear cache/state files ────────────────────────────────────────────────
rm -f "$CACHE_DIR"/skills-catalog.json \
      "$CACHE_DIR"/skills-remembered-picks.json \
      "$CACHE_DIR"/skills-repo-sources.json \
      "$CACHE_DIR"/skills-connected-agents.json \
      "$CACHE_DIR"/skills-spawned-*.txt \
      "$CACHE_DIR"/skills-pending-*.txt \
      "$CACHE_DIR"/skills-picker-*.log 2>/dev/null || true
rm -rf "$CACHE_DIR/skill-repos" 2>/dev/null || true
echo "  ✓ Cleared cache files"

# ── 4. Strip the hook entries from settings.json ──────────────────────────────
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
