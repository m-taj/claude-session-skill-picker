#!/usr/bin/env python3
"""
Detached skill picker. Opens a GUI dialog in its own window (no terminal contact).

Reads a catalog JSON file (built by skills-launch.py) describing skills to offer.
Writes selections to the pending file (argv[1]) as `name|arg` lines, where `arg`
is empty if the skill has no args.

Per-platform strategy (first that works wins):
  macOS    -> JXA NSAlert: checkbox per skill + popup dropdown when skill has args
              fallback: 'choose from list' (Cmd-click multi-select, no arg picker)
              fallback: tkinter checklist
  Windows  -> tkinter ttk.Checkbutton + ttk.Combobox per row
"""

import os
import sys
import json
import shutil
import platform
import subprocess

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

PICKER_DIR    = os.path.dirname(os.path.abspath(__file__))
LOGO_GIF_PATH = os.path.join(PICKER_DIR, "images", "skillpicker-logo.gif")

def timeout_seconds():
    """Idle auto-close timeout. Prevents zombie pickers from prior sessions
    living forever in the background. Override with CLAUDE_SKILLS_PICKER_TIMEOUT."""
    raw = os.environ.get("CLAUDE_SKILLS_PICKER_TIMEOUT", "60")
    try:
        v = int(raw)
        return v if v > 0 else 60
    except ValueError:
        return 60

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
        from tkinter import ttk
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

    btns = ttk.Frame(outer)
    btns.pack(fill="x", pady=(8, 0))

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
    root.after(timeout_seconds() * 1000, root.destroy)

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
    timeout = timeout_seconds()

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

    valid_names = {e["name"] for e in catalog}
    remember = None
    picks = []
    for line in r.stdout.splitlines():
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

# ── macOS fallback: plain choose-from-list ────────────────────────────────────

def try_osascript_mac(pending, catalog):
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

    sysname = platform.system()

    if sysname == "Darwin":
        if try_jxa_mac(pending, catalog, catalog_path):
            return
        if try_osascript_mac(pending, catalog):
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
