#!/usr/bin/env python3
"""
Codex adapter — wires the existing skill picker into Codex's own hooks.json.
SessionStart reuses skills-launch.py verbatim (catalog building is agent-
neutral). UserPromptSubmit does NOT reuse skills-inject.py — see
codex_inject.py in this same directory for why.

Confirmed live against a real Codex install (codex-cli 0.145.0-alpha.27,
`codex features list` shows hooks: stable) rather than docs alone:
- stdin payload to a hook command includes "session_id", same field
  skills-launch.py already regexes out of Claude Code's payload — no
  changes needed there.
- UserPromptSubmit hooks support the exact same JSON output shape Claude
  Code uses ({"hookSpecificOutput": {"hookEventName": ..., "additionalContext": ...}}).
- SessionStart hooks are NOT async yet ("parsed but skipped" per Codex's own
  docs) — omit the async flag entirely rather than setting it true, or Codex
  drops the hook.
- New hooks require one-time manual approval via `/hooks` inside Codex
  (trust is recorded against the hook's content hash) — this script cannot
  and does not try to bypass that.
- hooks.json's top-level schema is {"hooks": {"SessionStart": [...], ...}},
  NOT flat event names at the root — confirmed via Codex's own parser error
  ("unknown field `SessionStart`, expected `description` or `hooks`"), which
  contradicts the flat example shown on the public docs page.
- skills-inject.py's "Activate these skills now via the Skill tool" message
  is Claude-Code-specific — Codex has no tool called "Skill" and doesn't
  scan Claude Code's plugin cache dirs, so that message reached the model
  with nothing it could act on (confirmed live: Codex reported "the actual
  skill/tool wasn't available to load"). codex_inject.py instead embeds each
  picked skill's real SKILL.md content directly.

Usage:
    python3 adapters/codex.py install
    python3 adapters/codex.py uninstall
    python3 adapters/codex.py status
"""

import os
import sys
import json
import shutil

HOME             = os.path.expanduser("~")
CODEX_HOME       = os.path.join(HOME, ".codex")
HOOKS_JSON       = os.path.join(CODEX_HOME, "hooks.json")
ADAPTER_DIR      = os.path.dirname(os.path.abspath(__file__))
CLAUDE_HOOKS_DIR = os.path.join(HOME, ".claude", "hooks")
LAUNCH_SCRIPT    = os.path.join(CLAUDE_HOOKS_DIR, "skills-launch.py")
INJECT_SRC       = os.path.join(ADAPTER_DIR, "codex_inject.py")
INJECT_SCRIPT    = os.path.join(CLAUDE_HOOKS_DIR, "codex_inject.py")

CODEX_APP_BUNDLE = "/Applications/ChatGPT.app/Contents/Resources/codex"


def is_installed():
    """Best-effort detection: bare `codex` on PATH, an existing $CODEX_HOME,
    or the ChatGPT desktop app's bundled binary (confirmed present this way
    on at least one real machine — Codex ships inside ChatGPT.app there,
    not as a standalone PATH entry)."""
    if shutil.which("codex"):
        return True
    if os.path.isfile(os.path.join(CODEX_HOME, "config.toml")):
        return True
    if os.path.exists(CODEX_APP_BUNDLE):
        return True
    return False


def _load_hooks_json():
    if not os.path.isfile(HOOKS_JSON):
        return {}
    try:
        with open(HOOKS_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _filter_out(entries, needle):
    """Drop any hook-list entry whose commands mention `needle`, same
    de-dup-by-substring pattern install.sh already uses for settings.json."""
    kept = []
    for entry in entries or []:
        commands = [h.get("command", "") for h in (entry.get("hooks") or [])]
        if any(needle in cmd for cmd in commands):
            continue
        kept.append(entry)
    return kept


def _py():
    return sys.executable or "python3"


def install():
    if not is_installed():
        print("  ~ Codex not detected on this machine — skipping.")
        return False
    if not os.path.isfile(LAUNCH_SCRIPT):
        print(f"  x {LAUNCH_SCRIPT} not found — run this project's install.sh "
              f"first (the Codex adapter reuses skills-launch.py rather than "
              f"duplicating it).")
        return False
    if not os.path.isfile(INJECT_SRC):
        print(f"  x {INJECT_SRC} missing from the repo checkout.")
        return False

    shutil.copy(INJECT_SRC, INJECT_SCRIPT)
    print(f"  + Installed {INJECT_SCRIPT}")

    cfg = _load_hooks_json()
    # Self-heal: an earlier version of this adapter wrote SessionStart/
    # UserPromptSubmit at the top level, which Codex's parser rejects
    # (valid top-level fields are only "description"/"hooks"). Strip any
    # such stale keys rather than leaving them alongside the correct ones.
    cfg.pop("SessionStart", None)
    cfg.pop("UserPromptSubmit", None)
    cfg.setdefault("hooks", {})
    hooks = cfg["hooks"]
    hooks.setdefault("SessionStart", [])
    hooks.setdefault("UserPromptSubmit", [])

    hooks["SessionStart"] = _filter_out(hooks["SessionStart"], "skills-launch.py") + [{
        "matcher": "startup|resume",
        "hooks": [{"type": "command", "command": f'{_py()} "{LAUNCH_SCRIPT}"'}],
    }]
    # Filter on both names: "skills-inject.py" cleans up entries from the
    # earlier (buggy) version of this adapter that pointed at Claude Code's
    # own inject script directly.
    upsubmit = _filter_out(hooks["UserPromptSubmit"], "skills-inject.py")
    upsubmit = _filter_out(upsubmit, "codex_inject.py")
    hooks["UserPromptSubmit"] = upsubmit + [{
        "hooks": [{"type": "command", "command": f'{_py()} "{INJECT_SCRIPT}"'}],
    }]

    os.makedirs(CODEX_HOME, exist_ok=True)
    with open(HOOKS_JSON, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

    print(f"  + Wrote {HOOKS_JSON}")
    print("  ! One manual step required, in a real Terminal (not the ChatGPT")
    print("    desktop app's chat box — /hooks there just answers in prose,")
    print("    it doesn't open the real review UI, confirmed by direct test):")
    print(f'      "{CODEX_APP_BUNDLE}"   # or plain `codex` if it is on PATH')
    print("    then type /hooks and trust the new SessionStart/UserPromptSubmit")
    print("    entries. Codex won't run an unapproved hook, by design, and this")
    print("    installer does not use --dangerously-bypass-hook-trust to skip it.")
    return True


def uninstall():
    cfg = _load_hooks_json()
    if not cfg or not cfg.get("hooks"):
        print("  ~ No hooks.json found — nothing to remove.")
        return True

    hooks = cfg["hooks"]
    hooks["SessionStart"] = _filter_out(hooks.get("SessionStart"), "skills-launch.py")
    upsubmit = _filter_out(hooks.get("UserPromptSubmit"), "skills-inject.py")
    upsubmit = _filter_out(upsubmit, "codex_inject.py")
    hooks["UserPromptSubmit"] = upsubmit

    with open(HOOKS_JSON, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

    try:
        os.remove(INJECT_SCRIPT)
    except OSError:
        pass

    print(f"  + Removed skill-picker entries from {HOOKS_JSON}")
    return True


def status():
    print(f"Codex detected: {is_installed()}")
    cfg = _load_hooks_json()
    hooks = cfg.get("hooks", {})
    has_launch = any("skills-launch.py" in h.get("command", "")
                      for e in hooks.get("SessionStart", []) for h in e.get("hooks", []))
    has_inject = any("codex_inject.py" in h.get("command", "")
                      for e in hooks.get("UserPromptSubmit", []) for h in e.get("hooks", []))
    print(f"SessionStart hook present: {has_launch}")
    print(f"UserPromptSubmit hook present: {has_inject}")
    return has_launch and has_inject


def _self_test():
    """Merge logic must be idempotent and must never clobber unrelated hook
    entries — verified against a temp hooks.json, not the real one."""
    import tempfile
    global HOOKS_JSON, CODEX_HOME
    orig_hooks_json, orig_codex_home = HOOKS_JSON, CODEX_HOME
    tmpdir = tempfile.mkdtemp()
    try:
        CODEX_HOME = tmpdir
        HOOKS_JSON = os.path.join(tmpdir, "hooks.json")
        with open(HOOKS_JSON, "w") as f:
            json.dump({
                "hooks": {
                    "SessionStart": [{"matcher": "startup", "hooks": [
                        {"type": "command", "command": "echo unrelated-hook"}]}],
                },
            }, f)

        global is_installed
        real_is_installed = is_installed
        is_installed = lambda: True  # noqa: E731 — force-install path for the test
        try:
            assert install() is True
            cfg = _load_hooks_json()
            assert len(cfg["hooks"]["SessionStart"]) == 2, "unrelated hook was clobbered"
            assert any("echo unrelated-hook" in h["command"]
                       for e in cfg["hooks"]["SessionStart"] for h in e["hooks"])
            assert status() is True

            install()  # re-install must not duplicate our own entry
            cfg = _load_hooks_json()
            assert len(cfg["hooks"]["SessionStart"]) == 2, "re-install duplicated our own entry"

            uninstall()
            cfg = _load_hooks_json()
            assert len(cfg["hooks"]["SessionStart"]) == 1, "uninstall didn't remove our entry"
            assert not any("skills-launch.py" in h["command"]
                           for e in cfg["hooks"]["SessionStart"] for h in e["hooks"])
            assert status() is False
        finally:
            is_installed = real_is_installed
        print("self-test OK")
    finally:
        HOOKS_JSON, CODEX_HOME = orig_hooks_json, orig_codex_home
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "install":
        sys.exit(0 if install() else 1)
    elif cmd == "uninstall":
        sys.exit(0 if uninstall() else 1)
    elif cmd == "status":
        sys.exit(0 if status() else 1)
    elif cmd == "self-test":
        _self_test()
    else:
        print(__doc__)
        sys.exit(1)
