#!/usr/bin/env python3
"""
Background worker: checks GitHub Releases for a newer tagged version, and
verifies installed file checksums against CHECKSUMS.txt (if the current
release shipped one), at most once per day. Same detached-subprocess,
once-daily-cache pattern as skills-suggest.py — never blocks a session.

Update detection only ever reads GitHub's public Releases API (a small JSON
manifest); it never executes anything fetched here. Applying an update is a
separate, explicit action the user triggers from Settings (see run_update()
in skills-picker.py), pinned to a released git tag, never a floating branch.

Checksum verification is a support/debug signal only — it flags files that
differ from the release so a mismatch is visible, never overwrites a user's
local edits automatically.
"""

import os
import sys
import json
import hashlib
import urllib.request
import urllib.error
from datetime import date

HOOK_DIR       = os.path.dirname(os.path.abspath(__file__))
HOME           = os.path.expanduser("~")
CACHE_DIR      = os.path.join(HOME, ".claude", "cache")
VERSION_FILE   = os.path.join(HOOK_DIR, "VERSION")
CHECKSUMS_FILE = os.path.join(HOOK_DIR, "CHECKSUMS.txt")
CACHE_FILE     = os.path.join(CACHE_DIR, "skills-update-cache.json")
PREFS_FILE     = os.path.join(CACHE_DIR, "skills-picker-prefs.json")

GITHUB_RELEASES_API = "https://api.github.com/repos/m-taj/claude-session-skill-picker/releases/latest"


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def already_fresh():
    cache = load_json(CACHE_FILE, {})
    return cache.get("date") == date.today().isoformat()


def local_version():
    try:
        with open(VERSION_FILE, "r", encoding="utf-8") as f:
            return f.read().strip() or "0.0.0"
    except OSError:
        return "0.0.0"


def version_tuple(v):
    parts = []
    for p in v.lstrip("v").split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    parts += [0, 0, 0]
    return tuple(parts[:3])


def fetch_latest_tag():
    """Latest published GitHub Release's tag name, or None on any failure
    (no network, rate-limited, no releases yet, etc.) — always a soft no-op."""
    req = urllib.request.Request(
        GITHUB_RELEASES_API,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "claude-session-skill-picker"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return (data.get("tag_name") or "").strip() or None
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError):
        return None


def verify_checksums(base_dir=HOOK_DIR, checksums_file=CHECKSUMS_FILE):
    """sha256 each file listed in CHECKSUMS.txt against base_dir; returns the
    list of relative paths that are missing or don't match. [] if there's no
    CHECKSUMS.txt yet (pre-first-release installs) — not treated as tampering."""
    if not os.path.isfile(checksums_file):
        return []
    try:
        with open(checksums_file, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return []

    mismatches = []
    for line in lines:
        line = line.strip()
        if not line or "  " not in line:
            continue
        expected, _, relname = line.partition("  ")
        path = os.path.join(base_dir, relname)
        try:
            with open(path, "rb") as f:
                actual = hashlib.sha256(f.read()).hexdigest()
        except OSError:
            mismatches.append(relname)
            continue
        if actual != expected:
            mismatches.append(relname)
    return mismatches


def main():
    prefs = load_json(PREFS_FILE, {})
    if not prefs.get("update_check_enabled", True):
        return
    if already_fresh():
        return

    current  = local_version()
    latest   = fetch_latest_tag()
    tampered = verify_checksums()

    update_available = bool(latest) and version_tuple(latest) > version_tuple(current)
    result = {
        "date":              date.today().isoformat(),
        "current_version":   current,
        "latest_version":    latest or current,
        "update_available":  update_available,
        "tampered_files":    tampered,
        "seen":              not (update_available or tampered),
    }
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
    except OSError:
        pass


if __name__ == "__main__":
    main()
