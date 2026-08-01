#!/usr/bin/env python3
"""
Detached skill picker. Opens a GUI dialog in its own window (no terminal contact).

Reads a catalog JSON file (built by skills-launch.py) describing skills to offer.
Writes selections to the pending file (argv[1]) as `name|arg` lines, where `arg`
is empty if the skill has no args.

Strategy (first that works wins, same on both platforms):
  1. pywebview  -> one HTML/CSS/JS UI rendered in a native webview (WKWebView on
                   macOS, WebView2 on Windows). Primary UI when the optional
                   `pywebview` package is installed.
  2. macOS      -> JXA NSAlert: checkbox per skill + popup dropdown when skill has args
                   fallback: 'choose from list' (Cmd-click multi-select, no arg picker)
                   fallback: tkinter checklist
     Windows    -> tkinter ttk.Checkbutton + ttk.Combobox per row

Part of claude-session-skill-picker — github.com/m-taj/claude-session-skill-picker
"""

import os
import re
import sys
import time
import json
import html
import shutil
import hashlib
import pathlib
import platform
import threading
import subprocess
import webbrowser
from string import Template

HINT       = "Set CLAUDE_SKILLS_PICKER=off in your shell to disable this dialog."
DESC_MAX   = 72   # chars of description to show next to the checkbox, fallback path only

# ── Theme: ctOS / Watch_Dogs-inspired hacker terminal ──────────────────────────
BG        = "#11161c"   # dark slate (lighter than near-black, keeps some translucency feel)
FG        = "#d4e8ec"   # cool off-white
DIM       = "#5a7278"   # muted cyan-gray
ACCENT    = "#00e5ff"   # primary neon — cyan
ACCENT2   = "#ff2d78"   # secondary neon — magenta (activate / emphasis)
SURFACE   = "#171d24"   # buttons, combobox fields — one step lighter than BG
MONO      = "Consolas" if platform.system() == "Windows" else "Menlo"

PICKER_DIR     = os.path.dirname(os.path.abspath(__file__))
LOGO_GIF_PATH  = os.path.join(PICKER_DIR, "images", "skillpicker-logo.gif")
UNINSTALL_SH   = os.path.join(PICKER_DIR, "uninstall.sh")
UNINSTALL_PS1  = os.path.join(PICKER_DIR, "uninstall.ps1")
ADAPTERS_DIR   = os.path.join(PICKER_DIR, "adapters")
VERSION_PATH   = os.path.join(PICKER_DIR, "VERSION")
CHECKSUMS_PATH = os.path.join(PICKER_DIR, "CHECKSUMS.txt")

# claude-session-skill-picker — github.com/m-taj/claude-session-skill-picker
# Shown in the Settings > Updates tab; stripping it to rebrand a fork is a
# deliberate act, not an accident of a casual copy-paste.
REPO_URL     = "https://github.com/m-taj/claude-session-skill-picker.git"
PROJECT_LINE = "claude-session-skill-picker — github.com/m-taj/claude-session-skill-picker"

def get_local_version():
    try:
        with open(VERSION_PATH, "r", encoding="utf-8") as f:
            return f.read().strip() or "0.0.0"
    except OSError:
        return "0.0.0"

# No accounts/billing system exists yet (see project plan) — these are placeholder
# strings so the Settings panel's layout is already right when that ships.
ACCOUNT_LINE      = "Account: Not signed in"
SUBSCRIPTION_LINE = "Subscription: Free (beta) — accounts & billing are coming in a future update."

# ── Connected agents (Codex, OpenCode, ...) ───────────────────────────────────
# Claude Code isn't in this list — this picker only ever runs as ITS hook, so
# it's always "connected" and never something the user can toggle off here.
_AGENTS = {
    "codex":    {"label": "Codex",    "adapter": os.path.join(ADAPTERS_DIR, "codex.py")},
    "opencode": {"label": "OpenCode", "adapter": os.path.join(ADAPTERS_DIR, "opencode.py")},
}

CONNECTED_AGENTS_FILENAME = "skills-connected-agents.json"

def _connected_agents_path(catalog_path):
    return os.path.join(os.path.dirname(os.path.abspath(catalog_path)), CONNECTED_AGENTS_FILENAME)

def load_connected_agents(catalog_path):
    try:
        with open(_connected_agents_path(catalog_path), "r", encoding="utf-8") as f:
            return dict(json.load(f))
    except (OSError, ValueError):
        return {}

def save_connected_agents(catalog_path, state):
    try:
        with open(_connected_agents_path(catalog_path), "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except OSError:
        pass

# ── Picker options (disable / timeout) ────────────────────────────────────────
# UI-editable equivalent of the CLAUDE_SKILLS_PICKER / CLAUDE_SKILLS_PICKER_TIMEOUT
# env vars, for users who'd rather not touch their shell profile. Env vars still
# win if set, so scripting/CI use is unaffected.
PICKER_PREFS_FILENAME = "skills-picker-prefs.json"
DEFAULT_TIMEOUT = 60

def _picker_prefs_path(catalog_path):
    return os.path.join(os.path.dirname(os.path.abspath(catalog_path)), PICKER_PREFS_FILENAME)

def load_picker_prefs(catalog_path):
    try:
        with open(_picker_prefs_path(catalog_path), "r", encoding="utf-8") as f:
            data = dict(json.load(f))
    except (OSError, ValueError):
        data = {}
    data.setdefault("disabled", False)
    data.setdefault("timeout", DEFAULT_TIMEOUT)
    data.setdefault("gemini_api_key", "")
    data.setdefault("suggestions_enabled", True)
    data.setdefault("update_check_enabled", True)
    return data

def save_picker_prefs(catalog_path, prefs):
    try:
        with open(_picker_prefs_path(catalog_path), "w", encoding="utf-8") as f:
            json.dump(prefs, f, indent=2)
    except OSError:
        pass

# ── Skill suggestions (Gemini, free tier, once/day) ───────────────────────────
# Computed out-of-process by skills-suggest.py; the picker only ever reads the
# cache file it writes and marks it seen. See skills-suggest.py for the
# GEMINI_API_KEY gating and privacy notes.
SUGGESTIONS_CACHE_FILENAME = "skills-suggestions-cache.json"

def _suggestions_cache_path(catalog_path):
    return os.path.join(os.path.dirname(os.path.abspath(catalog_path)), SUGGESTIONS_CACHE_FILENAME)

def load_suggestions_cache(catalog_path):
    try:
        with open(_suggestions_cache_path(catalog_path), "r", encoding="utf-8") as f:
            data = dict(json.load(f))
    except (OSError, ValueError):
        data = {}
    data.setdefault("suggestions", [])
    data.setdefault("seen", True)
    return data

def save_suggestions_cache(catalog_path, data):
    try:
        with open(_suggestions_cache_path(catalog_path), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass

# ── Update / integrity check (GitHub Releases, once/day) ──────────────────────
# Computed out-of-process by skills-update.py; the picker only ever reads the
# cache file it writes, marks it seen, and (on explicit user click) performs
# the actual update. See skills-update.py for the version-check and checksum
# logic shared with run_update() below.
UPDATE_CACHE_FILENAME = "skills-update-cache.json"

def _update_cache_path(catalog_path):
    return os.path.join(os.path.dirname(os.path.abspath(catalog_path)), UPDATE_CACHE_FILENAME)

def load_update_cache(catalog_path):
    try:
        with open(_update_cache_path(catalog_path), "r", encoding="utf-8") as f:
            data = dict(json.load(f))
    except (OSError, ValueError):
        data = {}
    data.setdefault("current_version", get_local_version())
    data.setdefault("latest_version", get_local_version())
    data.setdefault("update_available", False)
    data.setdefault("tampered_files", [])
    data.setdefault("seen", True)
    return data

def save_update_cache(catalog_path, data):
    try:
        with open(_update_cache_path(catalog_path), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass

def _verify_checksums_at(base_dir):
    """Same logic as skills-update.py's verify_checksums(), duplicated per
    this project's no-cross-file-imports convention for standalone hook
    scripts — used here to sanity-check a freshly cloned release before
    installing it (see run_update())."""
    checksums_file = os.path.join(base_dir, "CHECKSUMS.txt")
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

def _load_adapter_module(path):
    """Load an adapter script (adapters/codex.py, adapters/opencode.py — plain
    standalone scripts, not a package) as a Python module by file path."""
    if not os.path.isfile(path):
        return None
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(os.path.basename(path)[:-3], path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None

def agent_detected(agent_id):
    info = _AGENTS.get(agent_id)
    if not info:
        return False
    mod = _load_adapter_module(info["adapter"])
    if mod is None:
        return False
    try:
        return bool(mod.is_installed())
    except Exception:
        return False

def run_agent_action(agent_id, action):
    """action: 'install' | 'uninstall'. Returns (ok: bool, message: str) — the
    message is whatever the adapter printed, same text an interactive install
    would show, just captured instead of going to a terminal no one's watching."""
    info = _AGENTS.get(agent_id)
    if not info:
        return False, "Unknown agent."
    mod = _load_adapter_module(info["adapter"])
    if mod is None:
        return False, f"{info['label']} adapter not found — reinstall this project."

    import io
    import contextlib
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            ok = mod.install() if action == "install" else mod.uninstall()
    except Exception as e:
        return False, f"Error: {e}"
    message = buf.getvalue().strip() or ("Done." if ok else "Failed.")
    return bool(ok), message

def run_uninstaller():
    """Best-effort: run the platform uninstaller if it was installed alongside this
    script. Returns True if it ran, False if the uninstaller file wasn't found."""
    if platform.system() == "Windows":
        if not os.path.isfile(UNINSTALL_PS1):
            return False
        subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File", UNINSTALL_PS1],
            timeout=30, capture_output=True,
        )
        return True
    if not os.path.isfile(UNINSTALL_SH):
        return False
    subprocess.run(["bash", UNINSTALL_SH], timeout=30, capture_output=True)
    return True

def timeout_seconds(catalog_path=None):
    """Idle auto-close timeout. Prevents zombie pickers from prior sessions
    living forever in the background. CLAUDE_SKILLS_PICKER_TIMEOUT wins if set
    (for scripting/CI); otherwise falls back to the Settings-panel value."""
    raw = os.environ.get("CLAUDE_SKILLS_PICKER_TIMEOUT")
    if raw is None and catalog_path:
        raw = load_picker_prefs(catalog_path).get("timeout")
    try:
        v = int(raw)
        return v if v > 0 else DEFAULT_TIMEOUT
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT

# ── Catalog loading ───────────────────────────────────────────────────────────

def load_catalog(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []

def short_desc(d):
    d = (d or "").strip().splitlines()
    d = d[0] if d else ""
    if len(d) > DESC_MAX:
        d = d[:DESC_MAX - 1].rstrip() + "…"
    return d

def row_label(entry):
    """Checkbox row text: label + the pre-summarized one-liner from the catalog
    (skills-launch.py's summarize()). Falls back to a blunt truncation if a
    catalog built by an older launch script has no `summary` field yet."""
    desc = entry.get("summary")
    if desc is None:
        desc = short_desc(entry.get("description"))
    if desc:
        return f"> {entry['label']}  ::  {desc}"
    return f"> {entry['label']}"

def group_headers(catalog):
    """Index -> group name, for every row where the group differs from the row before it."""
    headers = {}
    prev = None
    for i, entry in enumerate(catalog):
        g = entry.get("group")
        if g and g != prev:
            headers[i] = g
        prev = g
    return headers

# ── Output ────────────────────────────────────────────────────────────────────

def write_result(path, picks):
    """picks: list of (name, arg) where arg may be ''"""
    try:
        with open(path, "w", encoding="utf-8") as f:
            for name, arg in picks:
                f.write(f"{name}|{arg}\n")
    except OSError:
        pass

# ── Remembered picks (auto-select next session) ───────────────────────────────
# Deliberately not named skills-picker-*/skills-pending-*/skills-spawned-* — those
# prefixes get swept by skills-launch.py's 24h stale-file cleanup, which would
# silently reset this toggle on any day with no session.
STATE_FILENAME = "skills-remembered-picks.json"

def _state_path(catalog_path):
    return os.path.join(os.path.dirname(os.path.abspath(catalog_path)), STATE_FILENAME)

def load_state(catalog_path):
    """-> (remember: bool, picks: {name: arg})"""
    try:
        with open(_state_path(catalog_path), "r", encoding="utf-8") as f:
            data = json.load(f)
        return bool(data.get("remember")), dict(data.get("picks") or {})
    except (OSError, ValueError):
        return False, {}

def save_state(catalog_path, remember, picks):
    """Only call this on Activate — Skip should leave prior state untouched."""
    try:
        data = {"remember": bool(remember), "picks": dict(picks) if remember else {}}
        with open(_state_path(catalog_path), "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError:
        pass

# ── User-added GitHub-repo skill sources ──────────────────────────────────────
# Owned here (not imported from skills-launch.py — these are two independent
# hook scripts by design, same "no cross-file imports" convention as the
# remembered-picks state above) since the Settings panel needs to add/remove/
# refresh sources; skills-launch.py owns the matching scan-into-catalog side.
REPO_SOURCES_FILENAME = "skills-repo-sources.json"

def _repo_sources_path(catalog_path):
    return os.path.join(os.path.dirname(os.path.abspath(catalog_path)), REPO_SOURCES_FILENAME)

def load_repo_sources(catalog_path):
    try:
        with open(_repo_sources_path(catalog_path), "r", encoding="utf-8") as f:
            return list(json.load(f).get("repos") or [])
    except (OSError, ValueError):
        return []

def save_repo_sources(catalog_path, repos):
    try:
        with open(_repo_sources_path(catalog_path), "w", encoding="utf-8") as f:
            json.dump({"repos": list(repos)}, f, indent=2)
    except OSError:
        pass

def _repo_cache_dir(catalog_path, url):
    cache_dir = os.path.dirname(os.path.abspath(catalog_path))
    h = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return os.path.join(cache_dir, "skill-repos", h)

def fetch_repo(catalog_path, url, refresh=False):
    """Best-effort shallow clone (or `git pull` if refresh=True and already
    cloned). Never raises — matches skills-launch.py's identical helper."""
    if not shutil.which("git"):
        return
    dest = _repo_cache_dir(catalog_path, url)
    try:
        if os.path.isdir(os.path.join(dest, ".git")):
            if refresh:
                subprocess.run(["git", "-C", dest, "pull", "--ff-only"],
                               capture_output=True, timeout=30)
        else:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            subprocess.run(["git", "clone", "--depth", "1", url, dest],
                           capture_output=True, timeout=30)
    except Exception:
        pass

# ── Probes ────────────────────────────────────────────────────────────────────

def tkinter_works():
    code = "import tkinter; r=tkinter.Tk(); r.update(); r.destroy()"
    try:
        r = subprocess.run(
            [sys.executable or "python3", "-c", code],
            capture_output=True, timeout=5,
        )
        return r.returncode == 0
    except Exception:
        return False

def _force_foreground_windows(root):
    if platform.system() != "Windows":
        return
    try:
        import ctypes
        hwnd = root.winfo_id()
        u32 = ctypes.windll.user32
        u32.ShowWindow(hwnd, 5)
        u32.SetForegroundWindow(hwnd)
        u32.BringWindowToTop(hwnd)
    except Exception:
        pass

# ── tkinter picker (Windows primary, Mac last-ditch) ──────────────────────────

def _apply_dark_theme(root):
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass
    root.configure(bg=BG, highlightbackground=ACCENT, highlightcolor=ACCENT, highlightthickness=1)
    style.configure(".", background=BG, foreground=FG)
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=FG, font=(MONO, 11))
    style.configure("Title.TLabel", background=BG, foreground=ACCENT, font=(MONO, 14, "bold"))
    style.configure("Hint.TLabel", background=BG, foreground=DIM, font=(MONO, 9))
    style.configure("Header.TLabel", background=BG, foreground=ACCENT, font=(MONO, 10, "bold"))
    style.configure("TCheckbutton", background=BG, foreground=FG, font=(MONO, 11))
    style.map("TCheckbutton", background=[("active", BG)], foreground=[("active", ACCENT)])
    style.configure("TButton", background=SURFACE, foreground=FG,
                    font=(MONO, 10, "bold"), borderwidth=1, relief="solid",
                    bordercolor=DIM, focusthickness=0, padding=6)
    style.map("TButton", background=[("active", "#161b1e")])
    style.configure("Accent.TButton", background=SURFACE, foreground=ACCENT2,
                    font=(MONO, 10, "bold"), borderwidth=1, relief="solid",
                    bordercolor=ACCENT2, padding=6)
    style.map("Accent.TButton", background=[("active", "#1a0a10")])
    style.configure("TCombobox", fieldbackground=SURFACE, background=SURFACE, foreground=FG,
                    bordercolor=DIM, arrowcolor=ACCENT)
    style.configure("Vertical.TScrollbar", background=SURFACE, troughcolor=BG, borderwidth=0)

def try_tkinter(pending, catalog, catalog_path):
    try:
        import tkinter as tk
        from tkinter import ttk, messagebox
    except Exception:
        return False

    remember_prev, prior_picks = load_state(catalog_path)

    picks = []
    root = tk.Tk()
    root.title("Claude Code — Activate Skills")
    _apply_dark_theme(root)

    # Cap window height so it never overflows the screen, no matter how many
    # skills the user has installed. Anything past max_rows_visible scrolls.
    ROW_H            = 30
    MAX_ROWS_VISIBLE = 12
    visible_rows     = min(len(catalog), MAX_ROWS_VISIBLE)
    win_h            = 195 + visible_rows * ROW_H
    root.geometry(f"640x{win_h}")

    try:
        root.lift()
        root.attributes("-topmost", True)
        root.after(400, lambda: root.attributes("-topmost", False))
        root.after(50, lambda: _force_foreground_windows(root))
        root.focus_force()
    except Exception:
        pass

    outer = ttk.Frame(root, padding=16)
    outer.pack(fill="both", expand=True)

    ttk.Label(outer, text=">> SKILL_ACCESS.SYS", style="Title.TLabel").pack(anchor="w")
    ttk.Label(outer, text="[ SELECT MODULES FOR THIS SESSION · ENTER=ACTIVATE · ESC=SKIP ]",
              style="Hint.TLabel").pack(anchor="w", pady=(2, 10))

    # Scrollable region: Canvas + inner Frame + vertical Scrollbar.
    list_wrap = ttk.Frame(outer)
    list_wrap.pack(fill="both", expand=True)
    canvas    = tk.Canvas(list_wrap, borderwidth=0, highlightthickness=0, background=BG)
    vscroll   = ttk.Scrollbar(list_wrap, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=vscroll.set)
    canvas.pack(side="left",  fill="both", expand=True)
    vscroll.pack(side="right", fill="y")

    inner = ttk.Frame(canvas)
    canvas.create_window((0, 0), window=inner, anchor="nw")

    headers = group_headers(catalog)
    rows = []
    for i, entry in enumerate(catalog):
        if i in headers:
            ttk.Label(inner, text=f"[ {headers[i].upper()} ]", style="Header.TLabel").pack(
                anchor="w", pady=(8 if i else 0, 2))

        row = ttk.Frame(inner)
        row.pack(anchor="w", fill="x", pady=1)

        v = tk.BooleanVar(value=entry["name"] in prior_picks)
        ttk.Checkbutton(row, text=row_label(entry), variable=v).pack(side="left", anchor="w")

        combo_var = None
        if entry.get("args"):
            args = entry["args"]
            default_arg = prior_picks.get(entry["name"]) or args.get("default") or (args.get("choices") or [""])[0]
            combo_var = tk.StringVar(value=default_arg)
            ttk.Combobox(
                row,
                textvariable=combo_var,
                values=args.get("choices", []),
                state="readonly",
                width=10,
            ).pack(side="right", padx=(8, 0))

        rows.append((entry, v, combo_var))

    def _on_inner_configure(_):
        canvas.configure(scrollregion=canvas.bbox("all"))
    inner.bind("<Configure>", _on_inner_configure)

    def _on_mousewheel(e):
        canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
    canvas.bind_all("<MouseWheel>", _on_mousewheel)            # Win + Mac
    canvas.bind_all("<Button-4>",   lambda e: canvas.yview_scroll(-1, "units"))  # Linux
    canvas.bind_all("<Button-5>",   lambda e: canvas.yview_scroll( 1, "units"))

    remember_var = tk.BooleanVar(value=remember_prev)
    ttk.Checkbutton(outer, text="Auto-select these picks next session",
                    variable=remember_var).pack(anchor="w", pady=(12, 0))

    ttk.Label(outer, text=HINT, style="Hint.TLabel").pack(anchor="w", pady=(8, 4))

    def open_settings():
        win = tk.Toplevel(root)
        win.title("Settings")
        win.configure(bg=BG, highlightbackground=ACCENT, highlightthickness=1)
        win.transient(root)
        pane = ttk.Frame(win, padding=16)
        pane.pack(fill="both", expand=True)

        ttk.Label(pane, text="[ SETTINGS ]", style="Header.TLabel").pack(anchor="w")
        ttk.Label(pane, text=ACCOUNT_LINE).pack(anchor="w", pady=(10, 2))
        ttk.Label(pane, text=SUBSCRIPTION_LINE, wraplength=360, justify="left").pack(anchor="w")

        def do_uninstall():
            if not messagebox.askyesno(
                "Uninstall Skill Picker?",
                "This removes the picker hooks from this machine. Continue?",
            ):
                return
            ran = run_uninstaller()
            if ran:
                messagebox.showinfo("Skill Picker", "Uninstalled. Restart Claude Code to complete.")
            else:
                messagebox.showwarning("Skill Picker", "Uninstaller script not found next to this picker.")
            win.destroy()
            root.destroy()

        action_row = ttk.Frame(pane)
        action_row.pack(fill="x", pady=(16, 0))
        ttk.Button(action_row, text="Uninstall…", command=do_uninstall,
                   style="Accent.TButton").pack(side="left")
        ttk.Button(action_row, text="Close", command=win.destroy).pack(side="left", padx=(8, 0))

    btns = ttk.Frame(outer)
    btns.pack(fill="x", pady=(8, 0))
    ttk.Button(btns, text="⚙", width=3, command=open_settings).pack(side="left")

    def on_activate():
        for entry, v, cv in rows:
            if v.get():
                arg = cv.get() if cv is not None else ""
                picks.append((entry["name"], arg))
        save_state(catalog_path, remember_var.get(), picks)
        root.destroy()

    def on_skip():
        root.destroy()

    ttk.Button(btns, text="Skip",     command=on_skip).pack(side="right", padx=4)
    ttk.Button(btns, text="Activate", command=on_activate, style="Accent.TButton").pack(side="right")

    root.bind("<Return>", lambda e: on_activate())
    root.bind("<Escape>", lambda e: on_skip())

    # Idle auto-close — prevents zombie pickers from accumulating across sessions.
    root.after(timeout_seconds(catalog_path) * 1000, root.destroy)

    root.mainloop()
    write_result(pending, picks)
    return True

# ── macOS JXA picker (primary) ────────────────────────────────────────────────

def try_jxa_mac(pending, catalog, catalog_path):
    if not shutil.which("osascript"):
        return False

    remember_prev, prior_picks = load_state(catalog_path)

    rows = []
    headers = group_headers(catalog)
    for i, entry in enumerate(catalog):
        if i in headers:
            rows.append({"type": "header", "text": headers[i].upper()})
        args = entry.get("args") or {}
        prior_arg = prior_picks.get(entry["name"])
        rows.append({
            "type":    "skill",
            "name":    entry["name"],
            "label":   row_label(entry),
            "choices": args.get("choices") or [],
            "default": prior_arg if prior_arg is not None else (args.get("default") or ""),
            "checked": entry["name"] in prior_picks,
        })

    payload = json.dumps(rows)

    script = """
ObjC.import('AppKit');
ObjC.import('Foundation');

var rows = %s;

// Layout: content view holds all rows; if total height exceeds maxViewH the
// content goes inside an NSScrollView so the dialog stays a reasonable size
// no matter how many skills are installed.
var rowH       = 26;
var w          = 720;
var titleH     = 110;
var contentH   = rows.length * rowH + 4;
var maxViewH   = 420;
var viewH      = Math.min(contentH, maxViewH);
var needScroll = contentH > maxViewH;
// Reserve room for the vertical scroll bar so checkbox labels don't get clipped.
var innerW     = needScroll ? (w - 18) : w;

var mono     = $.NSFont.fontWithNameSize("Menlo", 12);
var monoBold = $.NSFont.fontWithNameSize("Menlo-Bold", 12);

var cyan    = $.NSColor.colorWithSRGBRedGreenBlueAlpha(0.0,  0.90, 1.0,  1.0);
var darkBG  = $.NSColor.colorWithSRGBRedGreenBlueAlpha(0.067, 0.086, 0.11, 0.88);

var alert = $.NSAlert.alloc.init;
alert.messageText     = "";
alert.informativeText = "%s";
alert.addButtonWithTitle("Activate");
alert.addButtonWithTitle("Skip");
alert.addButtonWithTitle("⚙ Settings");
// Blank out the default app/warning icon — the logo image below replaces it.
alert.icon = $.NSImage.alloc.initWithSize($.NSMakeSize(1, 1));
// Native "remember this choice" affordance — no custom widget needed.
alert.showsSuppressionButton = true;
alert.suppressionButton.title = "Auto-select these picks next session";
alert.suppressionButton.state = %s;
// Dark, monospace, terminal-inspired look — native controls (checkboxes,
// popups, buttons) pick up dark rendering automatically from the appearance.
alert.window.appearance = $.NSAppearance.appearanceNamed('NSAppearanceNameDarkAqua');

// Outer wrapper: animated logo GIF on top, skill list below. A pre-rendered
// GIF (NSImageView animates it natively) is far more reliable across macOS
// versions than a hand-rolled NSTimer/custom-font animation in JXA.
var outer = $.NSView.alloc.initWithFrame($.NSMakeRect(0, 0, w, titleH + viewH));

var logoImage = $.NSImage.alloc.initWithContentsOfFile("%s");
if (logoImage) {
    var logoW = 470, logoH = 106;
    var logoX = (w - logoW) / 2;
    var logoY = viewH + (titleH - logoH) / 2;
    var logoView = $.NSImageView.alloc.initWithFrame($.NSMakeRect(logoX, logoY, logoW, logoH));
    logoView.image         = logoImage;
    logoView.imageScaling  = $.NSImageScaleProportionallyUpOrDown;
    logoView.animates      = true;
    outer.addSubview(logoView);
}

var content = $.NSView.alloc.initWithFrame($.NSMakeRect(0, 0, innerW, contentH));
content.wantsLayer = true;
content.layer.backgroundColor = darkBG.CGColor;
content.layer.borderWidth     = 1;
content.layer.borderColor     = cyan.CGColor;
var widgets = [];

for (var i = 0; i < rows.length; i++) {
    var y = contentH - (i + 1) * rowH + 4;
    var r = rows[i];

    if (r.type === "header") {
        var h = $.NSTextField.alloc.initWithFrame($.NSMakeRect(8, y + 2, innerW - 8, 18));
        h.stringValue     = "[ " + r.text + " ]";
        h.editable        = false;
        h.bezeled         = false;
        h.drawsBackground = false;
        h.font            = monoBold;
        h.textColor       = cyan;
        content.addSubview(h);
        continue;
    }

    var hasArgs = r.choices && r.choices.length > 0;
    var checkW  = hasArgs ? (innerW - 180) : innerW;

    var b = $.NSButton.alloc.initWithFrame($.NSMakeRect(8, y, checkW - 8, 22));
    b.setButtonType($.NSSwitchButton);
    b.title = r.label;
    b.font  = mono;
    b.state = r.checked ? 1 : 0;
    content.addSubview(b);

    var popup = null;
    if (hasArgs) {
        popup = $.NSPopUpButton.alloc.initWithFrame($.NSMakeRect(checkW + 8, y - 2, 160, 26));
        popup.font = mono;
        for (var j = 0; j < r.choices.length; j++) {
            popup.addItemWithTitle(r.choices[j]);
        }
        if (r.default) {
            popup.selectItemWithTitle(r.default);
        }
        content.addSubview(popup);
    }

    widgets.push({checkbox: b, popup: popup, name: r.name});
}

var accessory;
if (needScroll) {
    var scroll = $.NSScrollView.alloc.initWithFrame($.NSMakeRect(0, 0, w, viewH));
    scroll.hasVerticalScroller   = true;
    scroll.hasHorizontalScroller = false;
    scroll.autohidesScrollers    = false;
    scroll.borderType            = 0;   // NSNoBorder — the dark content bg is the visual edge
    scroll.drawsBackground       = true;
    scroll.backgroundColor       = darkBG;
    scroll.documentView          = content;
    // Scroll the content to the top so item 0 is visible on open.
    scroll.documentView.scrollPoint($.NSMakePoint(0, contentH));
    accessory = scroll;
} else {
    accessory = content;
}
outer.addSubview(accessory);

alert.accessoryView = outer;
$.NSApp.activateIgnoringOtherApps(true);

var rc = alert.runModal;

var out = [];
if (rc == 1000) {
    out.push("__REMEMBER__|" + (alert.suppressionButton.state == 1 ? 1 : 0));
    for (var k = 0; k < widgets.length; k++) {
        var wgt = widgets[k];
        if (wgt.checkbox.state == 1) {
            var arg = "";
            if (wgt.popup) {
                var sel = wgt.popup.titleOfSelectedItem;
                if (sel) arg = ObjC.unwrap(sel);
            }
            out.push(wgt.name + "|" + arg);
        }
    }
} else if (rc == 1002) {
    out.push("__SETTINGS__");
}
out.join("\\n");
""" % (
        payload,
        f"[ SELECT MODULES FOR THIS SESSION ]\\n{HINT}".replace('"', '\\"'),
        1 if remember_prev else 0,
        LOGO_GIF_PATH.replace("\\", "\\\\").replace('"', '\\"'),
    )

    # Idle auto-close: Python kills the osascript subprocess after the timeout,
    # closing the dialog window. Prevents pickers from prior sessions living
    # forever in the background.
    timeout = timeout_seconds(catalog_path)

    try:
        r = subprocess.run(
            ["osascript", "-l", "JavaScript", "-e", script],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        # User didn't engage in time — treat as Skip.
        write_result(pending, [])
        return True
    except Exception:
        return False

    if r.returncode != 0:
        return False

    lines = r.stdout.splitlines()
    if any(line.strip() == "__SETTINGS__" for line in lines):
        open_settings_mac()
        write_result(pending, [])
        return True

    valid_names = {e["name"] for e in catalog}
    remember = None
    picks = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("__REMEMBER__|"):
            remember = line.split("|", 1)[1] == "1"
            continue
        if "|" not in line:
            continue
        name, _, arg = line.partition("|")
        if name in valid_names:
            picks.append((name, arg))
    write_result(pending, picks)
    if remember is not None:
        save_state(catalog_path, remember, dict(picks))
    return True

def _mac_alert(message_text, informative_text, buttons, timeout=120):
    """Run a plain NSAlert (no accessory view) with the given buttons.
    Returns the button title clicked, or None on error/timeout."""
    btn_calls = "".join(f'alert.addButtonWithTitle("{b}");\n' for b in buttons)
    script = """
ObjC.import('AppKit');
var alert = $.NSAlert.alloc.init;
alert.messageText = "%s";
alert.informativeText = "%s";
%s
alert.window.appearance = $.NSAppearance.appearanceNamed('NSAppearanceNameDarkAqua');
$.NSApp.activateIgnoringOtherApps(true);
var rc = alert.runModal;
(rc - 1000);
""" % (
        message_text.replace('"', '\\"'),
        informative_text.replace('"', '\\"'),
        btn_calls,
    )
    try:
        r = subprocess.run(["osascript", "-l", "JavaScript", "-e", script],
                           capture_output=True, text=True, timeout=timeout)
    except Exception:
        return None
    try:
        idx = int(r.stdout.strip())
    except ValueError:
        return None
    if 0 <= idx < len(buttons):
        return buttons[idx]
    return None

def open_settings_mac():
    """Settings > Uninstall flow as a short sequence of native alerts — simpler and
    more reliable than wiring live click handlers into the same modal session."""
    choice = _mac_alert(
        "Skill Picker — Settings",
        f"{ACCOUNT_LINE}\\n{SUBSCRIPTION_LINE}",
        ["Uninstall…", "Close"],
    )
    if choice != "Uninstall…":
        return
    confirm = _mac_alert(
        "Uninstall Skill Picker?",
        "This removes the picker hooks from this machine. This can't be undone from here.",
        ["Uninstall", "Cancel"],
    )
    if confirm != "Uninstall":
        return
    ran = run_uninstaller()
    if ran:
        _mac_alert("Skill Picker", "Uninstalled. Restart Claude Code to complete.", ["OK"])
    else:
        _mac_alert("Skill Picker", "Uninstaller script not found next to this picker.", ["OK"])

# ── macOS fallback: plain choose-from-list ────────────────────────────────────

def try_osascript_mac(pending, catalog, catalog_path=None):
    """Fallback Mac picker — Cmd-click multi-select. Ignores arg dropdowns;
    arg-having skills use their default."""
    if not shutil.which("osascript"):
        return False

    label_to_name = {row_label(e): e["name"] for e in catalog}
    default_arg   = {e["name"]: (e.get("args") or {}).get("default", "") for e in catalog}
    items_lit = "{" + ", ".join('"' + l.replace('"', '\\"') + '"' for l in label_to_name.keys()) + "}"
    script = f'''
set picks to choose from list {items_lit} ¬
    with title "Claude Code" ¬
    with prompt "Activate skills (Cmd-click selects multiple).
{HINT}" ¬
    OK button name "Activate" ¬
    cancel button name "Skip" ¬
    multiple selections allowed true
if picks is false then
    return ""
else
    set AppleScript's text item delimiters to linefeed
    return picks as text
end if
'''
    try:
        r = subprocess.run(["osascript", "-e", script],
                           capture_output=True, text=True, timeout=900)
    except Exception:
        return False
    if r.returncode != 0:
        write_result(pending, [])
        return True
    picks = []
    for line in r.stdout.splitlines():
        line = line.strip()
        if line in label_to_name:
            name = label_to_name[line]
            picks.append((name, default_arg.get(name, "")))
    write_result(pending, picks)
    return True

# ── pywebview picker (prototype — one HTML/CSS/JS UI, both platforms) ────────
# Renders the dialog as real HTML/CSS in a native webview (WKWebView on macOS,
# WebView2 on Windows) instead of NSAlert/tkinter widgets. Full design control
# (fonts, layout, in-page settings panel) from one shared implementation instead
# of maintaining separate JXA and tkinter code paths. Optional dependency —
# falls back automatically to the existing pickers if `webview` isn't installed
# or the platform webview runtime isn't available (e.g. WebView2 missing).

_PAGE_TEMPLATE = Template("""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 20px;
    background: $bg; color: $fg;
    font-family: $mono, monospace;
    -webkit-user-select: none; user-select: none;
    overflow: hidden;
  }
  .logo-wrap { text-align: center; margin-bottom: 8px; }
  .logo-wrap img { max-width: 380px; }
  h1 {
    color: $accent; font-size: 15px; letter-spacing: 1px;
    margin: 0 0 4px 0;
  }
  .hint { color: $dim; font-size: 11px; margin: 0 0 14px 0; }
  .list {
    background: rgba(0,0,0,0.25); border: 1px solid $accent;
    border-radius: 4px; padding: 10px 12px;
    max-height: 340px; overflow-y: auto;
  }
  .hdr {
    color: $accent; font-weight: bold; font-size: 12px;
    margin: 10px 0 4px 0;
  }
  .hdr:first-child { margin-top: 0; }
  label.row {
    display: flex; align-items: center; gap: 8px;
    padding: 4px 2px; cursor: pointer; font-size: 13px;
  }
  label.row:hover { color: $accent; }
  .rowlabel { flex: 1; }
  .dim { color: $dim; }
  select {
    background: $surface; color: $fg; border: 1px solid $dim;
    border-radius: 3px; font-family: $mono, monospace; font-size: 12px;
  }
  .remember {
    margin-top: 12px; font-size: 12px; display: flex; align-items: center; gap: 6px;
    cursor: pointer;
  }
  .btnrow { display: flex; justify-content: space-between; align-items: center; margin-top: 14px; }
  button {
    font-family: $mono, monospace; font-weight: bold; font-size: 12px;
    background: $surface; color: $fg; border: 1px solid $dim;
    border-radius: 4px; padding: 7px 14px; cursor: pointer;
  }
  button.accent { color: $accent2; border-color: $accent2; }
  button.gear { padding: 7px 10px; }
  #settingsPanel {
    display: none; position: fixed; inset: 0; background: rgba(10,12,15,0.96);
    padding: 24px; color: $fg;
  }
  #settingsPanel.open { display: block; }
  #settingsPanel h2 { color: $accent; font-size: 14px; margin-top: 18px; }
  #settingsPanel h2:first-child { margin-top: 0; }
  #settingsPanel p { font-size: 12px; color: $fg; }
  #settingsPanel .sub { color: $dim; }
  .repo-add { display: flex; gap: 6px; margin: 6px 0 10px 0; }
  .repo-add input {
    flex: 1; background: $surface; color: $fg; border: 1px solid $dim;
    border-radius: 3px; font-family: $mono, monospace; font-size: 12px; padding: 6px 8px;
  }
  .repo-list { max-height: 120px; overflow-y: auto; }
  .repo-row {
    display: flex; justify-content: space-between; align-items: center;
    font-size: 12px; padding: 4px 0; border-bottom: 1px solid rgba(255,255,255,0.08);
  }
  .repo-row button { padding: 3px 8px; font-size: 11px; }
  .repo-msg { font-size: 11px; color: $dim; min-height: 14px; margin-top: 4px; }
  .agent-row {
    display: flex; justify-content: space-between; align-items: center;
    font-size: 12px; padding: 5px 0; border-bottom: 1px solid rgba(255,255,255,0.08);
  }
  .agent-row label { display: flex; align-items: center; gap: 8px; cursor: pointer; }
  .agent-row .dim { font-size: 11px; }
  .agent-msg { font-size: 11px; color: $dim; min-height: 14px; margin-top: 4px; }
  .icon-btn { position: relative; margin-left: 6px; }
  .badge {
    display: none; position: absolute; top: -6px; right: -6px;
    background: $accent2; color: $bg; border-radius: 8px;
    font-size: 9px; line-height: 14px; min-width: 14px; text-align: center;
    padding: 0 3px;
  }
  .badge.show { display: block; }
  #suggestPanel {
    display: none; position: fixed; inset: 0; background: rgba(10,12,15,0.96);
    padding: 24px; color: $fg;
  }
  #suggestPanel.open { display: block; }
  #suggestPanel h2 { color: $accent; font-size: 14px; margin-top: 0; }
  #suggestPanel .sub { color: $dim; font-size: 12px; }
  .suggest-row {
    padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.08);
    display: flex; justify-content: space-between; align-items: center; gap: 10px;
  }
  .suggest-row .name { font-size: 13px; }
  .suggest-row .reason { font-size: 11px; color: $dim; }
  .suggest-row button { padding: 4px 10px; font-size: 11px; }
  .suggest-empty { font-size: 12px; color: $dim; }
  ol.tutorial { margin: 6px 0 10px 0; padding-left: 20px; font-size: 12px; color: $fg; }
  ol.tutorial li { margin-bottom: 4px; }
  ol.tutorial button { padding: 3px 8px; font-size: 11px; }
  .repo-add input[type="password"] {
    flex: 1; background: $surface; color: $fg; border: 1px solid $dim;
    border-radius: 3px; font-family: $mono, monospace; font-size: 12px; padding: 6px 8px;
  }
  .switch { position: relative; display: inline-block; width: 38px; height: 20px; flex-shrink: 0; cursor: pointer; }
  .switch input { opacity: 0; width: 0; height: 0; }
  .switch .slider {
    position: absolute; inset: 0; background: $surface; border: 1px solid $dim;
    border-radius: 20px; transition: .15s;
  }
  .switch .slider::before {
    content: ""; position: absolute; height: 14px; width: 14px; left: 2px; top: 2px;
    background: $dim; border-radius: 50%; transition: .15s;
  }
  .switch input:checked + .slider { background: rgba(0,229,255,0.15); border-color: $accent; }
  .switch input:checked + .slider::before { transform: translateX(18px); background: $accent; }
  .switch-row {
    display: flex; justify-content: space-between; align-items: center;
    font-size: 12px; padding: 6px 0;
  }
  .tabs { display: flex; gap: 4px; margin: 12px 0 16px 0; border-bottom: 1px solid $dim; }
  .tab-btn {
    background: none; border: none; border-radius: 0; color: $dim;
    font-family: $mono, monospace; font-size: 12px; font-weight: bold;
    padding: 6px 10px; cursor: pointer; border-bottom: 2px solid transparent;
  }
  .tab-btn.active { color: $accent; border-bottom-color: $accent; }
  .tab-content { display: none; }
  .tab-content.active { display: block; }
</style>
</head>
<body>
  <div class="logo-wrap"><img src="$logo_uri"></div>
  <h1>&gt;&gt; SKILL_ACCESS.SYS</h1>
  <p class="hint">[ SELECT MODULES FOR THIS SESSION ]  ·  $hint</p>

  <div class="list">$rows</div>

  <label class="remember">
    <input type="checkbox" id="rememberChk" $remember_checked>
    Auto-select these picks next session
  </label>

  <div class="btnrow">
    <div>
      <button class="gear icon-btn" id="settingsBtn">&#9881;<span class="badge" id="updateBadge"></span></button>
      <button class="gear icon-btn" id="suggestBtn" style="display:none;">&#128161;<span class="badge" id="suggestBadge"></span></button>
    </div>
    <div>
      <button id="skipBtn">Skip</button>
      <button class="accent" id="activateBtn">Activate</button>
    </div>
  </div>

  <div id="suggestPanel">
    <h2>[ SUGGESTED SKILLS ]</h2>
    <p class="sub">Based on your usage over the last 30 days, refreshed at most once a day.</p>
    <div id="suggestList"></div>
    <div class="btnrow">
      <div></div>
      <button id="suggestCloseBtn">Close</button>
    </div>
  </div>

  <div id="settingsPanel">
    <h2>[ SETTINGS ]</h2>

    <div class="tabs">
      <button class="tab-btn active" data-tab="general">General</button>
      <button class="tab-btn" data-tab="agents">Agents</button>
      <button class="tab-btn" data-tab="suggestions">Suggestions</button>
      <button class="tab-btn" data-tab="repos">Repos</button>
      <button class="tab-btn" data-tab="updates">Updates</button>
    </div>

    <div class="tab-content active" data-tab-content="general">
      <p>$account</p>
      <p class="sub">$subscription</p>

      <label class="switch-row">
        <span>Disable this dialog at session start</span>
        <label class="switch"><input type="checkbox" id="disablePickerChk"><span class="slider"></span></label>
      </label>
      <p class="sub" style="margin-top:8px;">Auto-close after (seconds) — applies next time this dialog opens:</p>
      <div class="repo-add">
        <input type="text" id="timeoutInput" style="max-width:80px; flex:none;">
        <button id="timeoutSaveBtn">Save</button>
      </div>
      <p class="sub">Re-enable any time from this same Settings panel — open it via the "Skill Picker Settings" desktop shortcut even while the dialog is disabled.</p>
      <div class="agent-msg" id="pickerOptsMsg"></div>

      <div class="btnrow">
        <div></div>
        <button class="accent" id="uninstallBtn">Uninstall&hellip;</button>
      </div>
    </div>

    <div class="tab-content" data-tab-content="agents">
      <p class="sub">Skills picked here also activate in any connected agent. Only agents detected on this machine can be connected.</p>
      <div id="agentList"></div>
      <div class="agent-msg" id="agentMsg"></div>
    </div>

    <div class="tab-content" data-tab-content="suggestions">
      <p class="sub">Free, based on your usage over time (last 30 days), refreshed at most once a day. Only skill names and pick counts ever leave this machine — never your conversation or prompt text.</p>
      <ol class="tutorial">
        <li>Get a free key (no credit card) — <button id="geminiSignupBtn">Open aistudio.google.com/apikey&hellip;</button></li>
        <li>Paste it below and click Save.</li>
        <li>That's it — a &#128161; badge appears next to the gear icon when a suggestion is ready.</li>
      </ol>
      <div class="repo-add">
        <input type="password" id="geminiKeyInput" placeholder="Paste your Gemini API key">
        <button id="geminiKeySaveBtn">Save</button>
      </div>
      <label class="switch-row" style="margin-top:10px;">
        <span>Enable AI skill suggestions</span>
        <label class="switch"><input type="checkbox" id="suggestionsEnabledChk"><span class="slider"></span></label>
      </label>
      <div class="agent-msg" id="suggestSettingsMsg"></div>
    </div>

    <div class="tab-content" data-tab-content="repos">
      <p class="sub">Add a GitHub repo URL to pull in its skills (SKILL.md at the repo root or a skills/ subdir). Fetched once on add; use Refresh to pull updates.</p>
      <div class="repo-add">
        <input type="text" id="repoUrlInput" placeholder="https://github.com/owner/repo">
        <button id="repoAddBtn">Add</button>
      </div>
      <div class="repo-list" id="repoList"></div>
      <div class="repo-msg" id="repoMsg"></div>
      <div class="btnrow">
        <button id="repoRefreshBtn">Refresh repos</button>
        <div></div>
      </div>
    </div>

    <div class="tab-content" data-tab-content="updates">
      <p class="sub">Current version: <span id="curVersion">$version</span></p>
      <p class="sub" id="updateStatusMsg">Checking&hellip;</p>
      <div class="btnrow">
        <div></div>
        <button class="accent" id="updateNowBtn" style="display:none;">Update now</button>
      </div>
      <div class="agent-msg" id="updateMsg"></div>
      <label class="switch-row" style="margin-top:10px;">
        <span>Check for updates automatically</span>
        <label class="switch"><input type="checkbox" id="updateCheckChk"><span class="slider"></span></label>
      </label>
      <p class="sub" style="margin-top:16px; opacity:0.7;">$project_line</p>
    </div>

    <div class="btnrow">
      <div></div>
      <button id="settingsCloseBtn">Close</button>
    </div>
  </div>

<script>
function collectPicks() {
  const picks = [];
  document.querySelectorAll('.row input[type=checkbox]').forEach(cb => {
    if (cb.checked) {
      const name = cb.dataset.name;
      const sel = document.querySelector('select[data-name="' + name + '"]');
      picks.push({name: name, arg: sel ? sel.value : ""});
    }
  });
  return picks;
}
document.getElementById('activateBtn').addEventListener('click', () => {
  const remember = document.getElementById('rememberChk').checked;
  window.pywebview.api.activate(collectPicks(), remember);
});
document.getElementById('skipBtn').addEventListener('click', () => {
  window.pywebview.api.skip();
});
function renderPickerOptions() {
  window.pywebview.api.get_picker_prefs().then(prefs => {
    document.getElementById('disablePickerChk').checked = !!prefs.disabled;
    document.getElementById('timeoutInput').value = prefs.timeout;
  });
}
function renderSuggestSettings() {
  window.pywebview.api.get_suggestion_settings().then(s => {
    const keyInput = document.getElementById('geminiKeyInput');
    keyInput.value = '';
    keyInput.placeholder = s.has_env_key
      ? 'Using GEMINI_API_KEY from your environment'
      : (s.has_ui_key ? 'Key saved (hidden) — paste a new one to replace it' : 'Paste your Gemini API key');
    keyInput.disabled = s.has_env_key;
    document.getElementById('suggestionsEnabledChk').checked = s.enabled;
  });
}
function renderUpdateSettings() {
  window.pywebview.api.get_update_status().then(s => {
    document.getElementById('curVersion').textContent = s.current_version;
    document.getElementById('updateCheckChk').checked = true;
    const msg = document.getElementById('updateStatusMsg');
    const btn = document.getElementById('updateNowBtn');
    let text = s.update_available ? ('v' + s.latest_version + ' is available.') : 'Up to date.';
    if (s.tampered_files && s.tampered_files.length) {
      text += ' ' + s.tampered_files.length + ' installed file(s) differ from the release (modified locally).';
    }
    msg.textContent = text;
    btn.style.display = s.update_available ? 'inline-block' : 'none';
  });
  window.pywebview.api.get_picker_prefs().then(prefs => {
    document.getElementById('updateCheckChk').checked = prefs.update_check_enabled !== false;
  });
}
function refreshSettingsPanels() {
  renderRepos();
  renderAgents();
  renderPickerOptions();
  renderSuggestSettings();
  renderUpdateSettings();
  window.pywebview.api.get_update_status().then(s => {
    const flagged = s.update_available || (s.tampered_files && s.tampered_files.length);
    document.getElementById('updateBadge').classList.remove('show');
    if (flagged && !s.seen) {
      document.querySelector('.tab-btn[data-tab="updates"]').click();
      window.pywebview.api.mark_update_seen();
    }
  });
}
function openSettings() {
  document.getElementById('settingsPanel').classList.add('open');
  refreshSettingsPanels();
}
document.getElementById('settingsBtn').addEventListener('click', () => {
  document.getElementById('settingsPanel').classList.toggle('open');
  refreshSettingsPanels();
});
document.getElementById('updateNowBtn').addEventListener('click', () => {
  const btn = document.getElementById('updateNowBtn');
  btn.disabled = true;
  document.getElementById('updateMsg').textContent = 'Updating…';
  window.pywebview.api.run_update().then(res => {
    btn.disabled = false;
    document.getElementById('updateMsg').textContent = res.message;
    renderUpdateSettings();
  });
});
document.getElementById('updateCheckChk').addEventListener('change', (e) => {
  window.pywebview.api.set_update_check_enabled(e.target.checked);
});
document.getElementById('geminiSignupBtn').addEventListener('click', () => {
  window.pywebview.api.open_gemini_signup();
});
document.getElementById('geminiKeySaveBtn').addEventListener('click', () => {
  const key = document.getElementById('geminiKeyInput').value;
  if (!key) { return; }
  window.pywebview.api.set_gemini_key(key).then(() => {
    document.getElementById('suggestSettingsMsg').textContent = 'Key saved.';
    renderSuggestSettings();
  });
});
document.getElementById('suggestionsEnabledChk').addEventListener('change', (e) => {
  window.pywebview.api.set_suggestions_enabled(e.target.checked).then(() => {
    document.getElementById('suggestSettingsMsg').textContent = e.target.checked
      ? 'Suggestions enabled.' : 'Suggestions disabled.';
  });
});
document.getElementById('disablePickerChk').addEventListener('change', (e) => {
  window.pywebview.api.set_picker_disabled(e.target.checked).then(() => {
    document.getElementById('pickerOptsMsg').textContent = e.target.checked
      ? 'Dialog disabled — use the desktop shortcut to reopen Settings.'
      : 'Dialog enabled.';
  });
});
document.getElementById('timeoutSaveBtn').addEventListener('click', () => {
  const seconds = document.getElementById('timeoutInput').value;
  window.pywebview.api.set_picker_timeout(seconds).then(prefs => {
    document.getElementById('timeoutInput').value = prefs.timeout;
    document.getElementById('pickerOptsMsg').textContent = 'Saved.';
  });
});
if ($open_settings) { window.addEventListener('pywebviewready', openSettings); }
document.getElementById('settingsCloseBtn').addEventListener('click', () => {
  document.getElementById('settingsPanel').classList.remove('open');
});
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    btn.classList.add('active');
    document.querySelector('.tab-content[data-tab-content="' + btn.dataset.tab + '"]').classList.add('active');
  });
});

function checkSuggestions() {
  window.pywebview.api.get_suggestions().then(res => {
    const btn   = document.getElementById('suggestBtn');
    const badge = document.getElementById('suggestBadge');
    if (!res.items || res.items.length === 0) {
      btn.style.display = 'none';
      return;
    }
    btn.style.display = 'inline-block';
    if (res.unseen) {
      badge.textContent = String(res.items.length);
      badge.classList.add('show');
    } else {
      badge.classList.remove('show');
    }
  });
}
function renderSuggestions() {
  window.pywebview.api.get_suggestions().then(res => {
    const list = document.getElementById('suggestList');
    list.innerHTML = '';
    if (!res.items || res.items.length === 0) {
      list.innerHTML = '<p class="suggest-empty">No suggestions right now — check back after a bit more usage.</p>';
      return;
    }
    res.items.forEach(item => {
      const row = document.createElement('div');
      row.className = 'suggest-row';
      row.innerHTML =
        '<div><div class="name">' + item.name + '</div>' +
        '<div class="reason">' + (item.reason || '') + '</div></div>' +
        '<button data-name="' + item.name + '">Add</button>';
      row.querySelector('button').addEventListener('click', (e) => {
        const cb = document.querySelector('.row input[type=checkbox][data-name="' + item.name + '"]');
        if (cb) {
          cb.checked = true;
          cb.closest('label.row').scrollIntoView({behavior: 'smooth', block: 'center'});
        }
        e.target.textContent = 'Added';
        e.target.disabled = true;
      });
      list.appendChild(row);
    });
  });
}
document.getElementById('suggestBtn').addEventListener('click', () => {
  document.getElementById('suggestPanel').classList.add('open');
  renderSuggestions();
  window.pywebview.api.mark_suggestions_seen().then(() => {
    document.getElementById('suggestBadge').classList.remove('show');
  });
});
document.getElementById('suggestCloseBtn').addEventListener('click', () => {
  document.getElementById('suggestPanel').classList.remove('open');
});
window.addEventListener('pywebviewready', checkSuggestions);
function checkUpdates() {
  window.pywebview.api.get_update_status().then(s => {
    const badge = document.getElementById('updateBadge');
    const flagged = s.update_available || (s.tampered_files && s.tampered_files.length);
    if (flagged && !s.seen) {
      badge.textContent = '!';
      badge.classList.add('show');
    } else {
      badge.classList.remove('show');
    }
  });
}
window.addEventListener('pywebviewready', checkUpdates);
document.getElementById('uninstallBtn').addEventListener('click', () => {
  if (confirm('This removes the picker hooks from this machine. Continue?')) {
    window.pywebview.api.uninstall().then(msg => {
      alert(msg);
      window.pywebview.api.close_window();
    });
  }
});

function renderAgents() {
  window.pywebview.api.list_agents().then(agents => {
    const list = document.getElementById('agentList');
    list.innerHTML = '';
    agents.forEach(agent => {
      const row = document.createElement('div');
      row.className = 'agent-row';

      const left = document.createElement('div');
      const text = document.createElement('span');
      text.textContent = agent.label;
      const status = document.createElement('span');
      status.className = 'dim';
      status.textContent = agent.locked ? '  always on'
        : (agent.detected ? '' : '  not detected on this machine');
      left.appendChild(text);
      left.appendChild(status);

      const sw = document.createElement('label');
      sw.className = 'switch';
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = agent.connected;
      cb.disabled = agent.locked || !agent.detected;
      const slider = document.createElement('span');
      slider.className = 'slider';
      sw.appendChild(cb);
      sw.appendChild(slider);

      if (!agent.locked && agent.detected) {
        cb.addEventListener('change', () => {
          cb.disabled = true;
          document.getElementById('agentMsg').textContent = 'Working…';
          window.pywebview.api.set_agent_connected(agent.id, cb.checked).then(res => {
            cb.disabled = false;
            cb.checked = res.connected;
            document.getElementById('agentMsg').textContent = res.message || '';
          });
        });
      }

      row.appendChild(left);
      row.appendChild(sw);
      list.appendChild(row);
    });
  });
}

function renderRepos() {
  window.pywebview.api.list_repos().then(repos => {
    const list = document.getElementById('repoList');
    list.innerHTML = '';
    repos.forEach(url => {
      const row = document.createElement('div');
      row.className = 'repo-row';
      const label = document.createElement('span');
      label.textContent = url;
      const removeBtn = document.createElement('button');
      removeBtn.textContent = 'Remove';
      removeBtn.addEventListener('click', () => {
        window.pywebview.api.remove_repo(url).then(res => {
          renderRepos();
          document.getElementById('repoMsg').textContent = 'Removed. Takes effect next session.';
        });
      });
      row.appendChild(label);
      row.appendChild(removeBtn);
      list.appendChild(row);
    });
  });
}
document.getElementById('repoAddBtn').addEventListener('click', () => {
  const input = document.getElementById('repoUrlInput');
  window.pywebview.api.add_repo(input.value).then(res => {
    document.getElementById('repoMsg').textContent = res.message || '';
    if (res.ok) input.value = '';
    renderRepos();
  });
});
document.getElementById('repoRefreshBtn').addEventListener('click', () => {
  document.getElementById('repoMsg').textContent = 'Refreshing…';
  window.pywebview.api.refresh_repos().then(res => {
    document.getElementById('repoMsg').textContent = res.message || 'Done.';
  });
});
</script>
</body>
</html>
""")

def _file_uri(path):
    try:
        return pathlib.Path(path).as_uri()
    except Exception:
        return ""

def _safe_destroy(window):
    try:
        window.destroy()
    except Exception:
        pass

class _PickerApi:
    """Exposed to the page as window.pywebview.api.<method>(...)."""
    def __init__(self, catalog, pending, catalog_path):
        self.catalog      = catalog
        self.pending      = pending
        self.catalog_path = catalog_path
        self.done         = False
        self.window       = None

    def activate(self, picks, remember):
        valid_names = {e["name"] for e in self.catalog}
        clean = [(p.get("name"), p.get("arg") or "") for p in (picks or []) if p.get("name") in valid_names]
        write_result(self.pending, clean)
        save_state(self.catalog_path, bool(remember), dict(clean))
        self.done = True
        _safe_destroy(self.window)
        return "ok"

    def skip(self):
        write_result(self.pending, [])
        self.done = True
        _safe_destroy(self.window)
        return "ok"

    def uninstall(self):
        ran = run_uninstaller()
        if ran:
            return "Uninstalled. Restart Claude Code to complete."
        return "Uninstaller script not found next to this picker."

    def list_repos(self):
        return load_repo_sources(self.catalog_path)

    def add_repo(self, url):
        url = (url or "").strip()
        if not url:
            return {"ok": False, "message": "Enter a repo URL first.", "repos": self.list_repos()}
        repos = load_repo_sources(self.catalog_path)
        if url in repos:
            return {"ok": False, "message": "Already added.", "repos": repos}
        repos.append(url)
        save_repo_sources(self.catalog_path, repos)
        fetch_repo(self.catalog_path, url)
        return {"ok": True, "message": "Added — skills from it appear next session.", "repos": repos}

    def remove_repo(self, url):
        repos = [r for r in load_repo_sources(self.catalog_path) if r != url]
        save_repo_sources(self.catalog_path, repos)
        return {"ok": True, "repos": repos}

    def refresh_repos(self):
        repos = load_repo_sources(self.catalog_path)
        for url in repos:
            fetch_repo(self.catalog_path, url, refresh=True)
        return {"ok": True, "message": f"Refreshed {len(repos)} repo(s)."}

    def list_agents(self):
        connected = load_connected_agents(self.catalog_path)
        agents = [{
            "id": "claude", "label": "Claude Code",
            "detected": True, "connected": True, "locked": True,
        }]
        for agent_id, info in _AGENTS.items():
            detected = agent_detected(agent_id)
            agents.append({
                "id": agent_id,
                "label": info["label"],
                "detected": detected,
                "connected": bool(connected.get(agent_id)) if detected else False,
                "locked": False,
            })
        return agents

    def set_agent_connected(self, agent_id, connected):
        if agent_id not in _AGENTS:
            return {"ok": False, "message": "Unknown agent."}
        ok, message = run_agent_action(agent_id, "install" if connected else "uninstall")
        state = load_connected_agents(self.catalog_path)
        state[agent_id] = bool(connected) if ok else state.get(agent_id, False)
        save_connected_agents(self.catalog_path, state)
        return {"ok": ok, "message": message, "connected": state[agent_id]}

    def get_picker_prefs(self):
        return load_picker_prefs(self.catalog_path)

    def set_picker_disabled(self, disabled):
        prefs = load_picker_prefs(self.catalog_path)
        prefs["disabled"] = bool(disabled)
        save_picker_prefs(self.catalog_path, prefs)
        return prefs

    def set_picker_timeout(self, seconds):
        prefs = load_picker_prefs(self.catalog_path)
        try:
            seconds = int(seconds)
        except (TypeError, ValueError):
            seconds = DEFAULT_TIMEOUT
        prefs["timeout"] = seconds if seconds > 0 else DEFAULT_TIMEOUT
        save_picker_prefs(self.catalog_path, prefs)
        return prefs

    def set_update_check_enabled(self, enabled):
        prefs = load_picker_prefs(self.catalog_path)
        prefs["update_check_enabled"] = bool(enabled)
        save_picker_prefs(self.catalog_path, prefs)
        return prefs

    def get_suggestions(self):
        data = load_suggestions_cache(self.catalog_path)
        valid_names = {e["name"] for e in self.catalog}
        items = [s for s in data["suggestions"] if s.get("name") in valid_names]
        return {"items": items, "unseen": (not data["seen"]) and bool(items)}

    def mark_suggestions_seen(self):
        data = load_suggestions_cache(self.catalog_path)
        data["seen"] = True
        save_suggestions_cache(self.catalog_path, data)
        return "ok"

    def get_suggestion_settings(self):
        prefs = load_picker_prefs(self.catalog_path)
        env_key = os.environ.get("GEMINI_API_KEY", "")
        return {
            "has_env_key":  bool(env_key),
            "has_ui_key":   bool(prefs.get("gemini_api_key")),
            "enabled":      bool(prefs.get("suggestions_enabled", True)),
        }

    def set_gemini_key(self, key):
        prefs = load_picker_prefs(self.catalog_path)
        prefs["gemini_api_key"] = (key or "").strip()
        save_picker_prefs(self.catalog_path, prefs)
        return self.get_suggestion_settings()

    def set_suggestions_enabled(self, enabled):
        prefs = load_picker_prefs(self.catalog_path)
        prefs["suggestions_enabled"] = bool(enabled)
        save_picker_prefs(self.catalog_path, prefs)
        return self.get_suggestion_settings()

    def open_gemini_signup(self):
        try:
            webbrowser.open("https://aistudio.google.com/apikey")
        except Exception:
            pass
        return "ok"

    def get_version(self):
        return get_local_version()

    def get_update_status(self):
        return load_update_cache(self.catalog_path)

    def mark_update_seen(self):
        data = load_update_cache(self.catalog_path)
        data["seen"] = True
        save_update_cache(self.catalog_path, data)
        return "ok"

    def run_update(self):
        """One-click update, triggered only by an explicit click — never
        automatic. Backs up the installed hooks dir, clones the target
        release's git TAG (never a floating branch), verifies its checksums,
        then reuses install.sh/install.ps1 verbatim to apply it. Any failure
        rolls back to the pre-update backup and leaves the existing install
        untouched — this must never brick a user's setup."""
        status = load_update_cache(self.catalog_path)
        target = status.get("latest_version")
        if not target or not status.get("update_available"):
            return {"ok": False, "message": "No update available."}
        if not shutil.which("git"):
            return {"ok": False, "message": "git is required to update — install it and try again."}

        work_root   = os.path.join(os.path.dirname(os.path.abspath(self.catalog_path)), "self-update")
        backup_dir  = os.path.join(work_root, f"backup-{get_local_version()}-{int(time.time())}")
        scratch_dir = os.path.join(work_root, "src")

        try:
            shutil.rmtree(scratch_dir, ignore_errors=True)
            os.makedirs(work_root, exist_ok=True)
            shutil.copytree(PICKER_DIR, backup_dir)
        except Exception as e:
            return {"ok": False, "message": f"Backup failed, aborted (nothing changed): {e}"}

        def _rollback():
            try:
                for name in os.listdir(backup_dir):
                    src, dst = os.path.join(backup_dir, name), os.path.join(PICKER_DIR, name)
                    if os.path.isdir(src):
                        shutil.rmtree(dst, ignore_errors=True)
                        shutil.copytree(src, dst)
                    else:
                        shutil.copy2(src, dst)
            except Exception:
                pass

        try:
            r = subprocess.run(
                ["git", "clone", "--depth", "1", "--branch", target, REPO_URL, scratch_dir],
                capture_output=True, timeout=60, text=True,
            )
            if r.returncode != 0:
                return {"ok": False, "message": f"Could not fetch {target} — aborted, nothing changed."}

            mismatches = _verify_checksums_at(scratch_dir)
            if mismatches:
                return {"ok": False, "message": f"{len(mismatches)} file(s) in the release failed checksum verification — aborted, nothing changed."}

            installer_name = "install.ps1" if platform.system() == "Windows" else "install.sh"
            installer = os.path.join(scratch_dir, installer_name)
            if not os.path.isfile(installer):
                return {"ok": False, "message": "Installer script missing from the release — aborted."}

            if platform.system() == "Windows":
                r2 = subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", installer],
                                     capture_output=True, timeout=180, text=True)
            else:
                r2 = subprocess.run(["bash", installer], capture_output=True, timeout=180, text=True)
            if r2.returncode != 0:
                raise RuntimeError("install script failed")
        except Exception:
            _rollback()
            return {"ok": False, "message": "Update failed — rolled back, your prior install is untouched."}
        finally:
            shutil.rmtree(scratch_dir, ignore_errors=True)

        # Prune old backups, keep the 2 most recent.
        try:
            backups = sorted(
                (d for d in os.listdir(work_root) if d.startswith("backup-")),
                key=lambda d: os.path.getmtime(os.path.join(work_root, d)),
            )
            for d in backups[:-2]:
                shutil.rmtree(os.path.join(work_root, d), ignore_errors=True)
        except OSError:
            pass

        save_update_cache(self.catalog_path, {
            "current_version": target, "latest_version": target,
            "update_available": False, "tampered_files": [], "seen": True,
        })
        return {"ok": True, "message": f"Updated to {target} — restart your session to pick it up."}

    def close_window(self):
        _safe_destroy(self.window)
        return "ok"

def _pywebview_row_html(entry, prior_picks):
    args        = entry.get("args") or {}
    choices     = args.get("choices") or []
    prior_arg   = prior_picks.get(entry["name"])
    default_arg = prior_arg if prior_arg is not None else (args.get("default") or (choices[0] if choices else ""))
    checked     = "checked" if entry["name"] in prior_picks else ""
    desc        = entry.get("summary") or short_desc(entry.get("description"))
    name_esc    = html.escape(entry["name"])

    select_html = ""
    if choices:
        opts = "".join(
            '<option value="%s" %s>%s</option>' % (
                html.escape(c), "selected" if c == default_arg else "", html.escape(c),
            )
            for c in choices
        )
        select_html = '<select data-name="%s">%s</select>' % (name_esc, opts)

    return (
        '<label class="row">'
        '<input type="checkbox" data-name="%s" %s>'
        '<span class="rowlabel">&gt; %s <span class="dim">::</span> %s</span>'
        '%s'
        '</label>'
    ) % (name_esc, checked, html.escape(entry["label"]), html.escape(desc), select_html)

def try_pywebview(pending, catalog, catalog_path):
    try:
        import webview
    except Exception:
        return False

    remember_prev, prior_picks = load_state(catalog_path)
    headers = group_headers(catalog)

    parts = []
    for i, entry in enumerate(catalog):
        if i in headers:
            parts.append('<div class="hdr">[ %s ]</div>' % html.escape(headers[i].upper()))
        parts.append(_pywebview_row_html(entry, prior_picks))

    page = _PAGE_TEMPLATE.substitute(
        bg=BG, fg=FG, dim=DIM, accent=ACCENT, accent2=ACCENT2, surface=SURFACE, mono=MONO,
        logo_uri=_file_uri(LOGO_GIF_PATH),
        hint=html.escape(HINT),
        rows="".join(parts),
        remember_checked="checked" if remember_prev else "",
        account=html.escape(ACCOUNT_LINE),
        subscription=html.escape(SUBSCRIPTION_LINE),
        version=html.escape(get_local_version()),
        project_line=html.escape(PROJECT_LINE),
        open_settings="true" if os.environ.get("CLAUDE_SKILLS_PICKER_OPEN_SETTINGS") == "1" else "false",
    )

    api = _PickerApi(catalog, pending, catalog_path)

    try:
        window = webview.create_window(
            "Claude Code — Activate Skills",
            html=page,
            js_api=api,
            width=760, height=640,
            background_color=BG,
        )
        api.window = window

        timer = threading.Timer(timeout_seconds(catalog_path), lambda: _safe_destroy(window))
        timer.daemon = True
        timer.start()

        webview.start()
        timer.cancel()
    except Exception:
        return False

    if not api.done:
        write_result(pending, [])
    return True

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 3:
        sys.exit(0)
    pending      = sys.argv[1]
    catalog_path = sys.argv[2]

    catalog = load_catalog(catalog_path)
    if not catalog:
        write_result(pending, [])
        return

    if try_pywebview(pending, catalog, catalog_path):
        return

    sysname = platform.system()

    if sysname == "Darwin":
        if try_jxa_mac(pending, catalog, catalog_path):
            return
        if try_osascript_mac(pending, catalog, catalog_path):
            return
        if tkinter_works() and try_tkinter(pending, catalog, catalog_path):
            return
        write_result(pending, [])
        return

    if sysname == "Windows":
        if tkinter_works() and try_tkinter(pending, catalog, catalog_path):
            return
        write_result(pending, [])
        return

    write_result(pending, [])

if __name__ == "__main__":
    main()
    # pywebview's Cocoa/WebKit backend can leave native helper threads alive
    # after the window closes, which hangs CPython's normal interpreter
    # teardown (Py_FinalizeEx joins them) forever. os._exit skips that join
    # entirely — the result file is already written by this point.
    os._exit(0)
