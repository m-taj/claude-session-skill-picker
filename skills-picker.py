#!/usr/bin/env python3
"""
Detached skill picker. Opens a GUI dialog in its own window (no terminal contact).

Per-platform strategy (first that works wins):
  macOS    -> JXA NSAlert with real checkbox accessory view (native, no install)
              fallback: 'choose from list' (Cmd-click multi-select)
              fallback: tkinter Checkbutton checklist
  Windows  -> tkinter Checkbutton checklist (ships with python.org Python)

Writes selected keys (one per line) to the path passed as argv[1].
"""

import os
import sys
import shutil
import platform
import subprocess

SKILLS = [
    ("caveman full",             "terse output (~75% fewer tokens)"),
    ("caveman lite",             "less verbose, full sentences"),
    ("caveman ultra",            "max compression, arrows/abbrev"),
    ("claude-api",               "Anthropic SDK / Claude API focus"),
    ("compose-skill",            "Jetpack Compose / KMP / CMP"),
    ("security-review",          "security audit mode"),
    ("fewer-permission-prompts", "reduce permission prompts"),
]

KEYS_ONLY = [k for k, _ in SKILLS]
LABELS    = [f"{k}  -  {d}" for k, d in SKILLS]

HINT = "Set CLAUDE_SKILLS_PICKER=off in your shell to disable this dialog."

def write_result(path, picks):
    try:
        with open(path, "w") as f:
            for p in picks:
                f.write(p + "\n")
    except OSError:
        pass

def label_to_key(label):
    return label.split("  -  ", 1)[0].strip()

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
    """Pull the tkinter window to the foreground on Windows."""
    if platform.system() != "Windows":
        return
    try:
        import ctypes
        hwnd = root.winfo_id()
        user32 = ctypes.windll.user32
        user32.ShowWindow(hwnd, 5)              # SW_SHOW
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
    except Exception:
        pass

def try_tkinter(pending):
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception:
        return False

    picks = []
    root = tk.Tk()
    root.title("Claude Code - Activate Skills")
    root.geometry("600x440")

    try:
        root.lift()
        root.attributes("-topmost", True)
        root.after(400, lambda: root.attributes("-topmost", False))
        root.after(50, lambda: _force_foreground_windows(root))
        root.focus_force()
    except Exception:
        pass

    frame = ttk.Frame(root, padding=14)
    frame.pack(fill="both", expand=True)

    ttk.Label(
        frame,
        text="Activate skills for this session:",
        font=("", 13, "bold"),
    ).pack(anchor="w", pady=(0, 8))

    vars_ = []
    for key, desc in SKILLS:
        v = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text=f"{key}  -  {desc}", variable=v).pack(
            anchor="w", pady=1
        )
        vars_.append((key, v))

    ttk.Label(frame, text=HINT, foreground="#666").pack(anchor="w", pady=(12, 4))

    btns = ttk.Frame(frame)
    btns.pack(fill="x", pady=(8, 0))

    def on_activate():
        picks.extend(k for k, v in vars_ if v.get())
        root.destroy()

    def on_skip():
        root.destroy()

    ttk.Button(btns, text="Skip",     command=on_skip).pack(side="right", padx=4)
    ttk.Button(btns, text="Activate", command=on_activate).pack(side="right")

    root.bind("<Return>", lambda e: on_activate())
    root.bind("<Escape>", lambda e: on_skip())

    root.mainloop()
    write_result(pending, picks)
    return True

def try_jxa_mac(pending):
    """Mac native NSAlert with real checkbox accessory view (JXA + Cocoa)."""
    if not shutil.which("osascript"):
        return False

    import json as _json
    items_js = _json.dumps(LABELS)

    script = """
ObjC.import('AppKit');
ObjC.import('Foundation');

var items = %s;
var rowH = 26;
var w    = 520;
var h    = items.length * rowH + 4;

var alert = $.NSAlert.alloc.init;
alert.messageText     = "Claude Code  -  Activate Skills";
alert.informativeText = "Tick any skills to activate for this session.\\n%s";
alert.addButtonWithTitle("Activate");
alert.addButtonWithTitle("Skip");

var view  = $.NSView.alloc.initWithFrame($.NSMakeRect(0, 0, w, h));
var boxes = [];
for (var i = 0; i < items.length; i++) {
    var y = h - (i + 1) * rowH;
    var b = $.NSButton.alloc.initWithFrame($.NSMakeRect(0, y, w, 22));
    b.setButtonType($.NSSwitchButton);
    b.title = items[i];
    b.state = 0;
    view.addSubview(b);
    boxes.push(b);
}
alert.accessoryView = view;

$.NSApp.activateIgnoringOtherApps(true);
var rc = alert.runModal;

var picks = [];
if (rc == 1000) {
    for (var j = 0; j < boxes.length; j++) {
        if (boxes[j].state == 1) picks.push(items[j]);
    }
}
picks.join("\\n");
""" % (items_js, HINT.replace('"', '\\"'))

    try:
        r = subprocess.run(
            ["osascript", "-l", "JavaScript", "-e", script],
            capture_output=True, text=True, timeout=900,
        )
    except Exception:
        return False

    if r.returncode != 0:
        return False

    picks = []
    for line in r.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        k = label_to_key(line)
        if k in KEYS_ONLY:
            picks.append(k)
    write_result(pending, picks)
    return True

def try_osascript_mac(pending):
    """Fallback Mac picker: 'choose from list' (Cmd-click multi-select)."""
    if not shutil.which("osascript"):
        return False

    items_lit = "{" + ", ".join('"' + l.replace('"', '\\"') + '"' for l in LABELS) + "}"
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
        r = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=900,
        )
    except Exception:
        return False

    if r.returncode != 0:
        write_result(pending, [])
        return True

    picks = []
    for line in r.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        k = label_to_key(line)
        if k in KEYS_ONLY:
            picks.append(k)
    write_result(pending, picks)
    return True

def main():
    if len(sys.argv) < 2:
        sys.exit(0)
    pending = sys.argv[1]

    sysname = platform.system()

    if sysname == "Darwin":
        if try_jxa_mac(pending):
            return
        if try_osascript_mac(pending):
            return
        if tkinter_works() and try_tkinter(pending):
            return
        write_result(pending, [])
        return

    if sysname == "Windows":
        if tkinter_works() and try_tkinter(pending):
            return
        write_result(pending, [])
        return

    # Unsupported OS — write empty result and exit cleanly.
    write_result(pending, [])

if __name__ == "__main__":
    main()
