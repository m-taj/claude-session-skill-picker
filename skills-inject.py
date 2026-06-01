#!/usr/bin/env python3
"""
UserPromptSubmit hook.
If a pending skill selection file exists for this session, emit an
additionalContext block telling Claude to activate each picked skill via
the Skill tool. Pending file format: one `name|arg` line per pick, where
`arg` is empty for skills that take no arguments.
Fast path target: < 50 ms.
"""

import os
import re
import sys
import json

CACHE_DIR = os.path.expanduser("~/.claude/cache")

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
        with open(pending, "r", encoding="utf-8") as f:
            raw_lines = [l.strip() for l in f if l.strip()]
    except OSError:
        sys.exit(0)

    try:
        os.remove(pending)
    except OSError:
        pass

    if not raw_lines:
        sys.exit(0)

    lines = []
    for entry in raw_lines:
        if "|" in entry:
            name, _, arg = entry.partition("|")
        else:
            name, arg = entry, ""
        name = name.strip()
        arg  = arg.strip()
        if not name:
            continue
        if arg:
            lines.append(f'- Skill "{name}" with args "{arg}"')
        else:
            lines.append(f'- Skill "{name}"')

    if not lines:
        sys.exit(0)

    msg = (
        "[STARTUP HOOK - Activate these skills now via the Skill tool, one "
        "invocation per item (parallel calls are fine), BEFORE responding to "
        "the user:\n"
        + "\n".join(lines)
        + "]"
    )

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
