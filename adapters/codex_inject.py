#!/usr/bin/env python3
"""
Codex's UserPromptSubmit hook — NOT a copy of skills-inject.py.

Real bug found via live testing (2026-07-22): skills-inject.py tells the
model to "Activate these skills now via the Skill tool" — a tool that only
exists in Claude Code. Codex has no tool by that name, so the instruction
reached the model's context but it had nothing to call ("the actual
skill/tool wasn't available to load in this session", per Codex's own
response during testing). Codex also doesn't scan Claude Code's plugin
cache directories, so it can't resolve the skill by name even if it had an
equivalent invocation tool.

Fix: don't ask Codex to invoke anything by name. Read each picked skill's
actual SKILL.md content directly (path recorded in the catalog by
skills-launch.py) and inject the real instructions inline. Works regardless
of whether the target agent has any concept of a "Skill tool" at all.
"""

import os
import re
import sys
import json

CACHE_DIR    = os.path.expanduser("~/.claude/cache")
CATALOG_PATH = os.path.join(CACHE_DIR, "skills-catalog.json")


def _load_catalog():
    try:
        with open(CATALOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def _skill_body(entry):
    """Full SKILL.md content if we have a path on disk; falls back to just
    the catalog description for builtin entries (no backing file)."""
    path = entry.get("path")
    if path and os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                return f.read().strip()
        except OSError:
            pass
    return entry.get("description") or ""


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

    catalog = {e["name"]: e for e in _load_catalog()}

    blocks = []
    for entry in raw_lines:
        if "|" in entry:
            name, _, arg = entry.partition("|")
        else:
            name, arg = entry, ""
        name = name.strip()
        if not name or name not in catalog:
            continue
        body = _skill_body(catalog[name])
        if not body:
            continue
        header = f"### Skill: {name}" + (f" (arg: {arg})" if arg else "")
        blocks.append(header + "\n\n" + body)

    if not blocks:
        sys.exit(0)

    msg = (
        "[STARTUP HOOK - The user selected these skills for this session. "
        "Follow their instructions below as part of how you operate for the "
        "rest of this session, starting now:\n\n"
        + "\n\n---\n\n".join(blocks)
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
