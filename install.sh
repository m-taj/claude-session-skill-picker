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
                      "command": "$PY $HOOK_DIR/skills-launch.py",
                      "async": true }] }
      ],
      "UserPromptSubmit": [
        { "matcher": "",
          "hooks": [{ "type": "command",
                      "command": "$PY $HOOK_DIR/skills-inject.py",
                      "timeout": 5 }] }
      ]
    }
EOF
    NO_JQ=1
else
    NO_JQ=0
fi

# ── 2. Copy scripts + overrides ───────────────────────────────────────────────
mkdir -p "$HOOK_DIR"
for f in skills-launch.py skills-picker.py skills-inject.py skills-settings.py skills-suggest.py; do
    cp "$SCRIPT_DIR/$f" "$HOOK_DIR/$f"
    chmod +x "$HOOK_DIR/$f"
    echo "  ✓ Installed $HOOK_DIR/$f"
done

# Overrides file: do NOT overwrite if the user has already customized it.
OVR_SRC="$SCRIPT_DIR/skills-picker-overrides.json"
OVR_DST="$HOOK_DIR/skills-picker-overrides.json"
if [[ -f "$OVR_DST" ]]; then
    echo "  ~ Kept existing $OVR_DST (delete it to reinstall the default)"
else
    cp "$OVR_SRC" "$OVR_DST"
    echo "  ✓ Installed $OVR_DST"
fi

# Logo assets — the picker loads this GIF relative to its own installed path.
mkdir -p "$HOOK_DIR/images"
cp "$SCRIPT_DIR/images/skillpicker-logo.gif" "$HOOK_DIR/images/skillpicker-logo.gif"
echo "  ✓ Installed $HOOK_DIR/images/skillpicker-logo.gif"

# Uninstaller — copied alongside so the picker's Settings > Uninstall button
# works even if the cloned repo is later deleted.
cp "$SCRIPT_DIR/uninstall.sh" "$HOOK_DIR/uninstall.sh"
chmod +x "$HOOK_DIR/uninstall.sh"
echo "  ✓ Installed $HOOK_DIR/uninstall.sh"

# Per-agent adapters (Codex, OpenCode, ...) — copied alongside so the
# picker's Settings > Connected Agents section can install/uninstall them
# even if the cloned repo is later deleted.
mkdir -p "$HOOK_DIR/adapters"
cp "$SCRIPT_DIR"/adapters/*.py "$HOOK_DIR/adapters/" 2>/dev/null || true
cp "$SCRIPT_DIR"/adapters/*.js "$HOOK_DIR/adapters/" 2>/dev/null || true
echo "  ✓ Installed $HOOK_DIR/adapters/"

# Double-click Settings app — placed on the Desktop so a non-technical user
# can open Settings (e.g. to reconnect Codex/OpenCode) without ever touching
# a terminal. A real .app bundle (not a .command file) so LaunchServices
# runs it directly with no Terminal window flash, and so it gets its own icon.
if [[ -d "$HOME/Desktop" ]]; then
    rm -rf "$HOME/Desktop/Skill Picker Settings.app"
    cp -R "$SCRIPT_DIR/Skill Picker Settings.app" "$HOME/Desktop/Skill Picker Settings.app"
    chmod +x "$HOME/Desktop/Skill Picker Settings.app/Contents/MacOS/launcher"
    xattr -cr "$HOME/Desktop/Skill Picker Settings.app" 2>/dev/null || true
    echo "  ✓ Added \"Skill Picker Settings\" app to your Desktop"
fi

# pywebview — optional. The picker renders as HTML/CSS in a native webview when
# available and falls back automatically to the plain NSAlert/tkinter dialog if
# this isn't installed, so a failure here must never fail the whole install.
if "$PY" -m pip install --quiet pywebview 2>/dev/null; then
    echo "  ✓ Installed pywebview (richer picker UI)"
else
    echo "  ~ pywebview not installed — picker will use the native NSAlert dialog instead"
fi

# ── 3. Patch settings.json ────────────────────────────────────────────────────
if [[ "$NO_JQ" == "1" ]]; then
    echo ""
    echo "Done (scripts installed; add the hooks block manually then start a new session)."
    exit 0
fi

mkdir -p "$(dirname "$SETTINGS")"
[[ -f "$SETTINGS" ]] || echo '{}' > "$SETTINGS"

LAUNCH_CMD="$PY $HOOK_DIR/skills-launch.py"
INJECT_CMD="$PY $HOOK_DIR/skills-inject.py"

LAUNCH_ENTRY=$(jq -n --arg cmd "$LAUNCH_CMD" \
    '{matcher: "", hooks: [{type: "command", command: $cmd, async: true}]}')
INJECT_ENTRY=$(jq -n --arg cmd "$INJECT_CMD" \
    '{matcher: "", hooks: [{type: "command", command: $cmd, timeout: 5}]}')

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

# ── 4. Optional: AI skill suggestions (free) ──────────────────────────────────
if [[ -z "${GEMINI_API_KEY:-}" ]]; then
    echo ""
    echo "Optional: enable AI skill suggestions (free, no credit card)"
    echo "  Based on your usage over time, the picker can suggest skills you"
    echo "  haven't tried yet — a small notification badge shows up next to"
    echo "  the gear icon when one's ready. Off by default until you add a key:"
    echo ""
    echo "    1. Get a free key: https://aistudio.google.com/apikey"
    echo "       (sign in with any Google account — no billing required)"
    echo "    2. Add it to your shell profile (~/.zshrc or ~/.bash_profile):"
    echo "         export GEMINI_API_KEY=\"your-key-here\""
    echo "    3. Restart your terminal (and Claude Code) so the new session"
    echo "       inherits it."
    echo ""
    echo "  Only skill names and pick counts are ever sent — never your"
    echo "  conversation or prompt text. Skip this and the feature just stays"
    echo "  off, silently."
fi
