#!/usr/bin/env python3
"""
SessionStart hook (async:true).
Spawn detached picker GUI, return immediately. Does not touch terminal.
"""

import os
import re
import sys
import time
import platform
import subprocess

CACHE_DIR   = os.path.expanduser("~/.claude/cache")
PICKER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skills-picker.py")
STALE_AGE   = 24 * 3600

def cleanup_stale():
    try:
        now = time.time()
        for name in os.listdir(CACHE_DIR):
            if not (name.startswith("skills-spawned-") or
                    name.startswith("skills-pending-") or
                    name.startswith("skills-picker-")):
                continue
            path = os.path.join(CACHE_DIR, name)
            try:
                if now - os.path.getmtime(path) > STALE_AGE:
                    os.remove(path)
            except OSError:
                pass
    except OSError:
        pass

def main():
    if os.environ.get("CLAUDE_SKILLS_PICKER", "").lower() in ("off", "0", "false", "no"):
        sys.exit(0)

    raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    m = re.search(r'"session_id"\s*:\s*"([^"]+)"', raw)
    if not m:
        sys.exit(0)
    sid = m.group(1)

    os.makedirs(CACHE_DIR, exist_ok=True)
    cleanup_stale()

    marker = os.path.join(CACHE_DIR, f"skills-spawned-{sid}.txt")
    if os.path.exists(marker):
        sys.exit(0)
    try:
        open(marker, "w").close()
    except OSError:
        sys.exit(0)

    pending = os.path.join(CACHE_DIR, f"skills-pending-{sid}.txt")
    log     = os.path.join(CACHE_DIR, f"skills-picker-{sid}.log")

    py = sys.executable or "python3"

    kwargs = {
        "stdin":     subprocess.DEVNULL,
        "stdout":    open(log, "w"),
        "stderr":    subprocess.STDOUT,
        "close_fds": True,
    }
    if platform.system() == "Windows":
        DETACHED_PROCESS         = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        kwargs["creationflags"] = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True

    try:
        subprocess.Popen([py, PICKER_PATH, pending], **kwargs)
    except Exception:
        pass

    sys.exit(0)

if __name__ == "__main__":
    main()
