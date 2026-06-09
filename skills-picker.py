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
DESC_MAX   = 72   # chars of description to show next to the checkbox

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
    desc = short_desc(entry.get("description"))
    if desc:
        return f"{entry['label']}  -  {desc}"
    return entry["label"]

# ── Output ────────────────────────────────────────────────────────────────────

def write_result(path, picks):
    """picks: list of (name, arg) where arg may be ''"""
    try:
        with open(path, "w", encoding="utf-8") as f:
            for name, arg in picks:
                f.write(f"{name}|{arg}\n")
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

def try_tkinter(pending, catalog):
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception:
        return False

    picks = []
    root = tk.Tk()
    root.title("Claude Code - Activate Skills")
    n = max(7, len(catalog))
    root.geometry(f"640x{120 + n * 30}")

    try:
        root.lift()
        root.attributes("-topmost", True)
        root.after(400, lambda: root.attributes("-topmost", False))
        root.after(50, lambda: _force_foreground_windows(root))
        root.focus_force()
    except Exception:
        pass

    outer = ttk.Frame(root, padding=14)
    outer.pack(fill="both", expand=True)

    ttk.Label(outer, text="Activate skills for this session:",
              font=("", 13, "bold")).pack(anchor="w", pady=(0, 8))

    rows = []
    for entry in catalog:
        row = ttk.Frame(outer)
        row.pack(anchor="w", fill="x", pady=1)

        v = tk.BooleanVar(value=False)
        ttk.Checkbutton(row, text=row_label(entry), variable=v).pack(side="left", anchor="w")

        combo_var = None
        if entry.get("args"):
            args = entry["args"]
            combo_var = tk.StringVar(value=args.get("default") or (args.get("choices") or [""])[0])
            ttk.Combobox(
                row,
                textvariable=combo_var,
                values=args.get("choices", []),
                state="readonly",
                width=10,
            ).pack(side="right", padx=(8, 0))

        rows.append((entry, v, combo_var))

    ttk.Label(outer, text=HINT, foreground="#666").pack(anchor="w", pady=(12, 4))

    btns = ttk.Frame(outer)
    btns.pack(fill="x", pady=(8, 0))

    def on_activate():
        for entry, v, cv in rows:
            if v.get():
                arg = cv.get() if cv is not None else ""
                picks.append((entry["name"], arg))
        root.destroy()

    def on_skip():
        root.destroy()

    ttk.Button(btns, text="Skip",     command=on_skip).pack(side="right", padx=4)
    ttk.Button(btns, text="Activate", command=on_activate).pack(side="right")

    root.bind("<Return>", lambda e: on_activate())
    root.bind("<Escape>", lambda e: on_skip())

    # Idle auto-close — prevents zombie pickers from accumulating across sessions.
    root.after(timeout_seconds() * 1000, root.destroy)

    root.mainloop()
    write_result(pending, picks)
    return True

# ── macOS JXA picker (primary) ────────────────────────────────────────────────

def try_jxa_mac(pending, catalog):
    if not shutil.which("osascript"):
        return False

    rows = []
    for entry in catalog:
        rows.append({
            "name":    entry["name"],
            "label":   row_label(entry),
            "choices": (entry.get("args") or {}).get("choices") or [],
            "default": (entry.get("args") or {}).get("default") or "",
        })

    payload = json.dumps(rows)
    timeout = timeout_seconds()

    script = """
ObjC.import('AppKit');
ObjC.import('Foundation');

var rows        = %s;
var timeoutSec  = %d;

var rowH = 30;
var w    = 640;
var h    = rows.length * rowH + 4;

var alert = $.NSAlert.alloc.init;
alert.messageText     = "Claude Code  -  Activate Skills";
alert.informativeText = "Tick any skills to activate for this session.\\n%s";
alert.addButtonWithTitle("Activate");
alert.addButtonWithTitle("Skip");

var view  = $.NSView.alloc.initWithFrame($.NSMakeRect(0, 0, w, h));
var widgets = [];

for (var i = 0; i < rows.length; i++) {
    var y = h - (i + 1) * rowH + 4;
    var r = rows[i];

    var hasArgs = r.choices && r.choices.length > 0;
    var checkW  = hasArgs ? 460 : w;

    var b = $.NSButton.alloc.initWithFrame($.NSMakeRect(0, y, checkW, 22));
    b.setButtonType($.NSSwitchButton);
    b.title = r.label;
    b.state = 0;
    view.addSubview(b);

    var popup = null;
    if (hasArgs) {
        popup = $.NSPopUpButton.alloc.initWithFrame($.NSMakeRect(checkW + 8, y - 2, 160, 26));
        for (var j = 0; j < r.choices.length; j++) {
            popup.addItemWithTitle(r.choices[j]);
        }
        if (r.default) {
            popup.selectItemWithTitle(r.default);
        }
        view.addSubview(popup);
    }

    widgets.push({checkbox: b, popup: popup, name: r.name});
}

alert.accessoryView = view;
$.NSApp.activateIgnoringOtherApps(true);

// Idle auto-close: abort the modal after timeoutSec so an unattended picker
// from a previous Claude Code session can't outlive its parent indefinitely.
if (timeoutSec > 0) {
    var mainQ   = $.dispatch_get_main_queue();
    var deadline = $.dispatch_time($.DISPATCH_TIME_NOW, Math.floor(timeoutSec * 1e9));
    $.dispatch_after(deadline, mainQ, function() {
        $.NSApp.abortModal;
    });
}

var rc = alert.runModal;

var out = [];
if (rc == 1000) {
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
""" % (payload, timeout, HINT.replace('"', '\\"'))

    try:
        r = subprocess.run(
            ["osascript", "-l", "JavaScript", "-e", script],
            capture_output=True, text=True, timeout=900,
        )
    except Exception:
        return False

    if r.returncode != 0:
        return False

    valid_names = {e["name"] for e in catalog}
    picks = []
    for line in r.stdout.splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        name, _, arg = line.partition("|")
        if name in valid_names:
            picks.append((name, arg))
    write_result(pending, picks)
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
        if try_jxa_mac(pending, catalog):
            return
        if try_osascript_mac(pending, catalog):
            return
        if tkinter_works() and try_tkinter(pending, catalog):
            return
        write_result(pending, [])
        return

    if sysname == "Windows":
        if tkinter_works() and try_tkinter(pending, catalog):
            return
        write_result(pending, [])
        return

    write_result(pending, [])

if __name__ == "__main__":
    main()
