#!/usr/bin/env python3
"""
Standalone launcher: opens the skill picker straight to the Settings panel,
so connected agents (Codex, OpenCode, ...) can be toggled back on without
waiting for a new Claude Code session to start — the picker only launches
automatically on SessionStart and auto-closes after an idle timeout, which
made re-enabling a just-disconnected agent awkward mid-test.

Usage:
    python3 skills-settings.py
"""

import os
import sys
import subprocess

HOME       = os.path.expanduser("~")
CACHE_DIR  = os.path.join(HOME, ".claude", "cache")
PICKER_DIR = os.path.dirname(os.path.abspath(__file__))
PICKER     = os.path.join(PICKER_DIR, "skills-picker.py")

os.makedirs(CACHE_DIR, exist_ok=True)
catalog_path = os.path.join(CACHE_DIR, "skills-catalog.json")
pending      = os.path.join(CACHE_DIR, "skills-pending-settings.txt")

if not os.path.isfile(catalog_path):
    sys.exit("No skills catalog found yet — start a Claude Code session once first.")

env = os.environ.copy()
env["CLAUDE_SKILLS_PICKER_OPEN_SETTINGS"] = "1"
env.setdefault("CLAUDE_SKILLS_PICKER_TIMEOUT", "600")

subprocess.run([sys.executable or "python3", PICKER, pending, catalog_path], env=env)
