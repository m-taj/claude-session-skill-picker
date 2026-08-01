#!/usr/bin/env python3
"""
Background worker: computes skill suggestions from local usage history via
the Gemini API (free tier), caching the result for at most once per day.

Never blocks a Claude Code session — always spawned as a fully detached
subprocess from skills-launch.py, same pattern as the picker itself.

Privacy: only skill names and pick timestamps ever leave the machine (via
skills-usage-history.json), never raw conversation/prompt text. If
GEMINI_API_KEY isn't set, this script exits immediately and does nothing —
no network call, no error, no nagging.

Get a free key (no credit card required): https://aistudio.google.com/apikey

Part of claude-session-skill-picker — github.com/m-taj/claude-session-skill-picker
"""

import os
import sys
import json
import urllib.request
import urllib.error
from datetime import date, datetime, timedelta, timezone

HOME       = os.path.expanduser("~")
CACHE_DIR  = os.path.join(HOME, ".claude", "cache")
HISTORY    = os.path.join(CACHE_DIR, "skills-usage-history.json")
CATALOG    = os.path.join(CACHE_DIR, "skills-catalog.json")
CACHE_FILE = os.path.join(CACHE_DIR, "skills-suggestions-cache.json")
PREFS_FILE = os.path.join(CACHE_DIR, "skills-picker-prefs.json")

GEMINI_MODEL = "gemini-flash-latest"
GEMINI_URL   = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
MAX_SUGGESTIONS  = 3
HISTORY_LOOKBACK = timedelta(days=30)


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def already_fresh():
    cache = load_json(CACHE_FILE, {})
    return cache.get("date") == date.today().isoformat()


def build_prompt(history, catalog):
    cutoff = datetime.now(timezone.utc) - HISTORY_LOOKBACK
    recent_picks = []
    for entry in history:
        try:
            ts = datetime.fromisoformat(entry.get("ts", ""))
        except ValueError:
            continue
        if ts >= cutoff:
            recent_picks.extend(entry.get("picks") or [])

    if not recent_picks:
        return None

    counts = {}
    for name in recent_picks:
        counts[name] = counts.get(name, 0) + 1
    usage_lines = "\n".join(f"- {name}: picked {n} time(s)" for name, n in sorted(counts.items(), key=lambda kv: -kv[1]))

    used_names = set(counts)
    available = [e for e in catalog if e.get("name") not in used_names]
    if not available:
        return None
    catalog_lines = "\n".join(f"- {e['name']}: {e.get('description', '')}" for e in available[:60])

    return (
        "You are suggesting Claude Code skills a developer might want to enable, "
        "based on their recent usage pattern. Never invent skill names that aren't "
        "in the available list.\n\n"
        f"Recently used skills (last 30 days):\n{usage_lines}\n\n"
        f"Available skills not yet used:\n{catalog_lines}\n\n"
        f"Suggest at most {MAX_SUGGESTIONS} skills from the available list that "
        "would likely be useful given the usage pattern above. Respond with ONLY "
        "a JSON array, no markdown fences, no other text, in this exact shape:\n"
        '[{"name": "<exact skill name from the available list>", "reason": "<one short sentence>"}]\n'
        "If nothing available is a good fit, respond with an empty array []."
    )


def call_gemini(api_key, prompt):
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
    req = urllib.request.Request(
        f"{GEMINI_URL}?key={api_key}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["candidates"][0]["content"]["parts"][0]["text"]


def parse_suggestions(text, catalog):
    valid_names = {e["name"] for e in catalog}
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        items = json.loads(text[start:end + 1])
    except ValueError:
        return []
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if name not in valid_names:
            continue
        out.append({"name": name, "reason": str(item.get("reason", ""))[:200]})
    return out[:MAX_SUGGESTIONS]


def resolve_api_key(prefs):
    """Env var wins if set (scripting/CI); otherwise the key pasted into
    Settings, stored in skills-picker-prefs.json."""
    return os.environ.get("GEMINI_API_KEY") or prefs.get("gemini_api_key") or None


def main():
    prefs = load_json(PREFS_FILE, {})
    if not prefs.get("suggestions_enabled", True):
        return
    api_key = resolve_api_key(prefs)
    if not api_key:
        return
    if already_fresh():
        return

    history = load_json(HISTORY, [])
    catalog = load_json(CATALOG, [])
    if not catalog:
        return

    prompt = build_prompt(history, catalog)
    if not prompt:
        # Nothing to base a suggestion on yet — still mark today as checked
        # so we don't retry every session until there's real history.
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump({"date": date.today().isoformat(), "suggestions": [], "seen": True}, f, indent=2)
        except OSError:
            pass
        return

    try:
        text = call_gemini(api_key, prompt)
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError):
        return

    suggestions = parse_suggestions(text, catalog)
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "date": date.today().isoformat(),
                "suggestions": suggestions,
                "seen": len(suggestions) == 0,
            }, f, indent=2)
    except OSError:
        pass


if __name__ == "__main__":
    main()
