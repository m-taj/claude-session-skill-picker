#!/usr/bin/env python3
"""
Release helper — run before tagging a release:

    python3 gen_checksums.py

Writes CHECKSUMS.txt (sha256 of every file install.sh/install.ps1 actually
copies onto a user's machine) to the repo root. Commit it and attach it to
the GitHub Release alongside install.sh/install.ps1 — skills-update.py reads
it to flag files that were modified after install (see verify_checksums()).
"""

import hashlib
import os

REPO_DIR = os.path.dirname(os.path.abspath(__file__))

FILES = [
    "VERSION",
    "skills-launch.py",
    "skills-picker.py",
    "skills-inject.py",
    "skills-settings.py",
    "skills-suggest.py",
    "skills-update.py",
    "licensing.py",
    "images/skillpicker-logo.gif",
    "adapters/codex.py",
    "adapters/codex_inject.py",
    "adapters/opencode.py",
    "adapters/opencode.js",
]


def main():
    lines = []
    for relname in FILES:
        path = os.path.join(REPO_DIR, relname)
        if not os.path.isfile(path):
            print(f"  ~ skipping {relname} (not found)")
            continue
        with open(path, "rb") as f:
            digest = hashlib.sha256(f.read()).hexdigest()
        lines.append(f"{digest}  {relname}")

    out_path = os.path.join(REPO_DIR, "CHECKSUMS.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Wrote {out_path} ({len(lines)} files)")


if __name__ == "__main__":
    main()
