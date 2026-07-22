#!/usr/bin/env python3
"""
OpenCode adapter — installs opencode.js (this same directory) as a global
OpenCode plugin at ~/.config/opencode/plugins/skill-picker.js.

Confirmed live against the actually-installed @opencode-ai/plugin package on
this machine (v1.14.19 in ~/.config/opencode/node_modules, checked directly
rather than trusting the public docs page, which describes a plugin export
shape that turned out to still be accurate — but only verified against the
real package's own type definitions and example plugin, since a second,
newer "v2" API also ships in the same package and is NOT what's used here).

Unlike Codex, OpenCode's extensibility is a real JS/TS plugin module, not a
shell-command hook config — there is no equivalent trust-approval gate to
navigate here (OpenCode loads plugins from ~/.config/opencode/plugins/
directly; no separate approval step is documented or was hit during
`adapters/codex.py`-style testing).

Usage:
    python3 adapters/opencode.py install
    python3 adapters/opencode.py uninstall
    python3 adapters/opencode.py status
"""

import os
import sys
import shutil

HOME              = os.path.expanduser("~")
OPENCODE_CONFIG   = os.path.join(HOME, ".config", "opencode")
PLUGINS_DIR       = os.path.join(OPENCODE_CONFIG, "plugins")
PLUGIN_DEST       = os.path.join(PLUGINS_DIR, "skill-picker.js")
ADAPTER_DIR       = os.path.dirname(os.path.abspath(__file__))
PLUGIN_SRC        = os.path.join(ADAPTER_DIR, "opencode.js")
CLAUDE_HOOKS_DIR  = os.path.join(HOME, ".claude", "hooks")
LAUNCH_SCRIPT     = os.path.join(CLAUDE_HOOKS_DIR, "skills-launch.py")

OPENCODE_APP_BUNDLE = "/Applications/OpenCode.app"


def is_installed():
    """Best-effort detection: bare `opencode` on PATH, an existing
    ~/.config/opencode/, or the desktop app bundle (confirmed present this
    way on at least one real machine)."""
    if shutil.which("opencode"):
        return True
    if os.path.isdir(OPENCODE_CONFIG):
        return True
    if os.path.exists(OPENCODE_APP_BUNDLE):
        return True
    return False


def install():
    if not is_installed():
        print("  ~ OpenCode not detected on this machine — skipping.")
        return False
    if not os.path.isfile(LAUNCH_SCRIPT):
        print(f"  x {LAUNCH_SCRIPT} not found — run this project's install.sh "
              f"first (the OpenCode adapter reuses skills-launch.py rather "
              f"than duplicating it).")
        return False
    if not os.path.isfile(PLUGIN_SRC):
        print(f"  x {PLUGIN_SRC} missing from the repo checkout.")
        return False

    os.makedirs(PLUGINS_DIR, exist_ok=True)
    shutil.copy(PLUGIN_SRC, PLUGIN_DEST)
    print(f"  + Installed {PLUGIN_DEST}")
    print("  ! Restart OpenCode (fully quit, not just close the window) for "
          "the new plugin to load, same as any other OpenCode plugin change.")
    return True


def uninstall():
    if os.path.isfile(PLUGIN_DEST):
        try:
            os.remove(PLUGIN_DEST)
            print(f"  + Removed {PLUGIN_DEST}")
        except OSError as e:
            print(f"  x Could not remove {PLUGIN_DEST}: {e}")
            return False
    else:
        print("  ~ No installed plugin found — nothing to remove.")
    return True


def status():
    installed = is_installed()
    present = os.path.isfile(PLUGIN_DEST)
    print(f"OpenCode detected: {installed}")
    print(f"Plugin installed: {present}")
    return installed and present


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "install":
        sys.exit(0 if install() else 1)
    elif cmd == "uninstall":
        sys.exit(0 if uninstall() else 1)
    elif cmd == "status":
        sys.exit(0 if status() else 1)
    else:
        print(__doc__)
        sys.exit(1)
