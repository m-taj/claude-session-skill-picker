#!/usr/bin/env python3
"""
SessionStart hook (async:true).
1. Scan installed Claude Code skills (user + enabled plugins).
2. Merge with user overrides.
3. Write a fresh catalog file.
4. Spawn the picker GUI as a detached subprocess.
Returns in <100 ms; never blocks the Claude Code TUI.
"""

import os
import re
import sys
import json
import time
import platform
import subprocess

HOME       = os.path.expanduser("~")
CLAUDE_DIR = os.path.join(HOME, ".claude")
CACHE_DIR  = os.path.join(CLAUDE_DIR, "cache")
HOOK_DIR   = os.path.dirname(os.path.abspath(__file__))
PICKER     = os.path.join(HOOK_DIR, "skills-picker.py")
OVERRIDES  = os.path.join(HOOK_DIR, "skills-picker-overrides.json")
SETTINGS   = os.path.join(CLAUDE_DIR, "settings.json")
STALE_AGE  = 24 * 3600

# ── Scanning ──────────────────────────────────────────────────────────────────

def _parse_frontmatter(text):
    """
    Parse the YAML frontmatter of a SKILL.md file. Handles simple `key: value` lines
    and YAML folded/literal scalars (`key: >` or `key: |` followed by indented lines).
    Not a real YAML parser — only the subset SKILL.md actually uses.
    """
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    lines = m.group(1).splitlines()

    out = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or ":" not in line:
            i += 1
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()

        if val in (">", "|", ">-", "|-"):
            # Folded/literal multi-line scalar: consume indented continuation lines.
            i += 1
            chunks = []
            while i < len(lines):
                nxt = lines[i]
                if nxt.strip() == "":
                    chunks.append("")
                    i += 1
                    continue
                if nxt.startswith(" ") or nxt.startswith("\t"):
                    chunks.append(nxt.strip())
                    i += 1
                    continue
                break
            sep = "\n" if val.startswith("|") else " "
            out[key] = sep.join(c for c in chunks if c is not None).strip()
            continue

        out[key] = val.strip('"').strip("'")
        i += 1
    return out

def _read_skill_md(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return _parse_frontmatter(f.read())
    except OSError:
        return {}

def scan_user_skills():
    """~/.claude/skills/<name>/SKILL.md → invoke as <name>"""
    root = os.path.join(CLAUDE_DIR, "skills")
    skills = []
    if not os.path.isdir(root):
        return skills
    for name in os.listdir(root):
        sub = os.path.join(root, name)
        md  = os.path.join(sub, "SKILL.md")
        if os.path.isfile(md):
            fm = _read_skill_md(md)
            skills.append({
                "name":        fm.get("name", name),
                "description": fm.get("description", "user skill"),
                "source":      "user",
            })
    return skills

def _enabled_plugin_owners():
    """Read settings.json enabledPlugins → list of (owner, plugin) tuples for enabled plugins."""
    try:
        with open(SETTINGS, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        return []
    out = []
    for key, val in (cfg.get("enabledPlugins") or {}).items():
        if not val:
            continue
        # format is "<plugin>@<owner>"
        if "@" in key:
            plugin, owner = key.split("@", 1)
            out.append((owner, plugin))
    return out

def scan_plugin_skills():
    """~/.claude/plugins/cache/<owner>/<plugin>/<hash>/skills/<skill>/SKILL.md
       → invoke as <plugin>:<skill>"""
    cache = os.path.join(CLAUDE_DIR, "plugins", "cache")
    skills = []
    if not os.path.isdir(cache):
        return skills

    for owner, plugin in _enabled_plugin_owners():
        owner_plugin = os.path.join(cache, owner, plugin)
        if not os.path.isdir(owner_plugin):
            continue
        for hash_dir in os.listdir(owner_plugin):
            skills_root = os.path.join(owner_plugin, hash_dir, "skills")
            if not os.path.isdir(skills_root):
                continue
            for name in os.listdir(skills_root):
                # Skip IDE-specific reroots (.cursor / .windsurf live one level deeper anyway)
                if name.startswith("."):
                    continue
                sub = os.path.join(skills_root, name)
                md  = os.path.join(sub, "SKILL.md")
                if os.path.isfile(md):
                    fm = _read_skill_md(md)
                    skills.append({
                        "name":        f"{plugin}:{fm.get('name', name)}",
                        "description": fm.get("description", "plugin skill"),
                        "source":      f"plugin:{plugin}",
                    })
    return skills

# ── Overrides + catalog assembly ──────────────────────────────────────────────

def load_overrides():
    if not os.path.isfile(OVERRIDES):
        return {}
    try:
        with open(OVERRIDES, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}

def build_catalog():
    overrides = load_overrides()

    discovered = []
    discovered.extend(scan_user_skills())
    discovered.extend(scan_plugin_skills())

    for entry in overrides.get("include_builtins", []) or []:
        if entry.get("name"):
            discovered.append({
                "name":        entry["name"],
                "description": entry.get("description", "builtin"),
                "source":      "builtin",
            })

    seen = set()
    deduped = []
    for s in discovered:
        if s["name"] in seen:
            continue
        seen.add(s["name"])
        deduped.append(s)

    hide = set(overrides.get("hide", []) or [])
    labels = overrides.get("labels", {}) or {}
    args_map = overrides.get("args", {}) or {}

    catalog = []
    for s in deduped:
        if s["name"] in hide:
            continue
        catalog.append({
            "name":        s["name"],
            "label":       labels.get(s["name"], s["name"]),
            "description": s["description"],
            "args":        args_map.get(s["name"]) or None,
            "source":      s["source"],
        })

    catalog.sort(key=lambda e: (e["source"] != "builtin", e["name"].lower()))
    return catalog

# ── Spawn ─────────────────────────────────────────────────────────────────────

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

    catalog_path = os.path.join(CACHE_DIR, "skills-catalog.json")
    try:
        catalog = build_catalog()
        with open(catalog_path, "w", encoding="utf-8") as f:
            json.dump(catalog, f, indent=2)
    except Exception:
        catalog_path = ""

    if not catalog_path or not catalog:
        sys.exit(0)

    pending = os.path.join(CACHE_DIR, f"skills-pending-{sid}.txt")
    log     = os.path.join(CACHE_DIR, f"skills-picker-{sid}.log")
    py      = sys.executable or "python3"

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
        subprocess.Popen([py, PICKER, pending, catalog_path], **kwargs)
    except Exception:
        pass

    sys.exit(0)

if __name__ == "__main__":
    main()
