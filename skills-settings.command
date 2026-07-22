#!/bin/bash
# Double-click launcher for skills-settings.py — opens the skill picker
# straight to its Settings panel. No terminal knowledge required.
PY=$(command -v python3 || echo /usr/bin/python3)
"$PY" "$HOME/.claude/hooks/skills-settings.py"
