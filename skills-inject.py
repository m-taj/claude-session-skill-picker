#!/usr/bin/env python3
"""
UserPromptSubmit hook.
If a pending skill selection file exists for this session, emit an
additionalContext block telling Claude to activate each skill via the
Skill tool. Otherwise exit silently with no output.
Fast path target: < 50 ms.
"""

import os
import re
import sys
import json

CACHE_DIR = os.path.expanduser("~/.claude/cache")

ACTIVATION_MAP = {
    "caveman full":             ("caveman:caveman",          "full"),
    "caveman lite":             ("caveman:caveman",          "lite"),
    "caveman ultra":            ("caveman:caveman",          "ultra"),
    "claude-api":               ("claude-api",               None),
    "compose-skill":            ("compose-skill",            None),
    "security-review":          ("security-review",          None),
    "fewer-permission-prompts": ("fewer-permission-prompts", None),
}

INTENSITY_RANK = {"lite": 1, "full": 2, "ultra": 3}

def resolve_caveman(picks):
    cavemen = [p for p in picks if p.startswith("caveman ")]
    if len(cavemen) <= 1:
        return picks, None
    chosen = max(cavemen, key=lambda p: INTENSITY_RANK.get(p.split()[1], 0))
    dropped = [c for c in cavemen if c != chosen]
    kept = [p for p in picks if not p.startswith("caveman ") or p == chosen]
    note = ("Multiple caveman intensities were picked ("
            + ", ".join(c.split()[1] for c in cavemen)
            + "); using " + chosen.split()[1] + " only, ignoring "
            + ", ".join(c.split()[1] for c in dropped) + ".")
    return kept, note

def main():
    raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    m = re.search(r'"session_id"\s*:\s*"([^"]+)"', raw)
    if not m:
        sys.exit(0)
    sid = m.group(1)

    pending = os.path.join(CACHE_DIR, f"skills-pending-{sid}.txt")
    if not os.path.exists(pending):
        sys.exit(0)

    try:
        with open(pending) as f:
            picks = [l.strip() for l in f if l.strip()]
    except OSError:
        sys.exit(0)

    try:
        os.remove(pending)
    except OSError:
        pass

    if not picks:
        sys.exit(0)

    picks, note = resolve_caveman(picks)

    lines = []
    for p in picks:
        if p not in ACTIVATION_MAP:
            continue
        skill, arg = ACTIVATION_MAP[p]
        if arg:
            lines.append(f'- Skill "{skill}" with args "{arg}"')
        else:
            lines.append(f'- Skill "{skill}"')

    if not lines:
        sys.exit(0)

    msg = (
        "[STARTUP HOOK - Activate these skills now via the Skill tool, one "
        "invocation per item (parallel calls are fine), BEFORE responding to "
        "the user:\n"
        + "\n".join(lines)
    )
    if note:
        msg += "\n\nNote: " + note
    msg += "]"

    out = {
        "hookSpecificOutput": {
            "hookEventName":     "UserPromptSubmit",
            "additionalContext": msg,
        }
    }
    sys.stdout.write(json.dumps(out))
    sys.stdout.flush()
    sys.exit(0)

if __name__ == "__main__":
    main()
