#!/bin/bash
# Session startup skill selector — fires once per session on first user message

INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | grep -o '"session_id":"[^"]*"' | cut -d'"' -f4 2>/dev/null)
[ -z "$SESSION_ID" ] && exit 0

MARKER="/tmp/claude_session_skills_${SESSION_ID}"
[ -f "$MARKER" ] && exit 0
touch "$MARKER"

SKILL_DIALOG=(
  "caveman full — terse compressed output (~75% fewer tokens)"
  "caveman lite — less verbose, still readable sentences"
  "caveman ultra — max compression, arrows/abbreviations"
  "claude-api — Anthropic SDK / Claude API dev focus"
  "compose-skill — Jetpack Compose / Compose Multiplatform"
  "security — security-aware analysis and review mode"
  "fewer-prompts — scan session + add permission allowlist"
)

SKILL_KEYS=(
  "caveman full"
  "caveman lite"
  "caveman ultra"
  "claude-api"
  "compose-skill"
  "security"
  "fewer-prompts"
)

# ── osascript native macOS dialog (primary) ───────────────────────────────────
select_with_osascript() {
  local as_list=""
  for item in "${SKILL_DIALOG[@]}"; do
    as_list="${as_list}\"${item}\", "
  done
  as_list="{${as_list%, }}"

  osascript <<ASEOF
set skillList to ${as_list}
set chosen to choose from list skillList ¬
  with multiple selections allowed ¬
  with prompt "Select skills to activate for this Claude Code session:" ¬
  OK button name "Activate" ¬
  cancel button name "Skip"

if chosen is false then return ""

set output to ""
repeat with i from 1 to count of skillList
  repeat with c in chosen
    if (c as string) = (item i of skillList as string) then
      if output is "" then
        set output to (i - 1) as string
      else
        set output to output & linefeed & (i - 1) as string
      end if
    end if
  end repeat
end repeat
return output
ASEOF
}

# ── numbered text fallback (non-macOS or osascript unavailable) ───────────────
select_with_fallback() {
  local n=${#SKILL_DIALOG[@]}
  local state=()
  for ((i=0; i<n; i++)); do state+=("false"); done

  render() {
    printf "\n\033[1mActivate skills for this session:\033[0m\n\n" >/dev/tty
    for i in "${!SKILL_DIALOG[@]}"; do
      if [ "${state[$i]}" = "true" ]; then
        printf "  \033[32m[x]\033[0m %d. %s\n" "$((i+1))" "${SKILL_DIALOG[$i]}" >/dev/tty
      else
        printf "  [ ] %d. %s\n"                "$((i+1))" "${SKILL_DIALOG[$i]}" >/dev/tty
      fi
    done
    printf "\n  Number to toggle | Enter to confirm | 'skip' for none: " >/dev/tty
  }

  while true; do
    render
    read -r input </dev/tty
    case "$input" in
      ""|done) break ;;
      skip|none|0)
        for ((i=0; i<n; i++)); do state[$i]="false"; done
        break ;;
      *)
        if [[ "$input" =~ ^[0-9]+$ ]] && [ "$input" -ge 1 ] && [ "$input" -le "$n" ]; then
          local idx=$((input-1))
          [ "${state[$idx]}" = "true" ] && state[$idx]="false" || state[$idx]="true"
        fi ;;
    esac
  done

  for i in "${!state[@]}"; do
    [ "${state[$i]}" = "true" ] && echo "$i"
  done
}

# ── run selector ──────────────────────────────────────────────────────────────
if command -v osascript &>/dev/null; then
  INDICES=$(select_with_osascript)
elif [ -r /dev/tty ] && [ -w /dev/tty ]; then
  INDICES=$(select_with_fallback)
fi

KEYS=""
for idx in $INDICES; do
  [ -n "$idx" ] && KEYS="${KEYS},${SKILL_KEYS[$idx]}"
done
KEYS="${KEYS#,}"

[ -z "$KEYS" ] && exit 0

echo "[STARTUP HOOK — activate these skills before responding: $KEYS]"
