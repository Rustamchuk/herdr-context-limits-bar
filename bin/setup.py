#!/usr/bin/env python3
"""One-step setup: connects everything the bar needs. Safe to run again.

1. Claude Code statusLine -> this plugin (via install-statusline.py).
2. herdr sidebar rows for the provider, limit and context tokens.
3. Hotkey ctrl+shift+b to bring the bar back.
Existing user settings are never overwritten: if a row table or a key is taken,
the step is reported and left alone.
Stdlib only.
"""
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
HERDR = os.environ.get("HERDR_BIN_PATH") or "herdr"
CONFIG = os.environ.get("HERDR_CONFIG_PATH") or os.path.expanduser("~/.config/herdr/config.toml")
HOTKEY = "ctrl+shift+b"
COMMAND = "context-limits-bar.open-bar"

SIDEBAR_BLOCK = """
# Context & Limits Bar: sidebar rows (added by the plugin's setup action)
[ui.sidebar.agents]
row_gap = 0
rows = [
  ["state_icon", "tab", "pane"],
  ["$provider", "$limit"],
  ["$context"],
]
"""

HOTKEY_BLOCK = """
# Context & Limits Bar: bring the bar back in this tab (added by the plugin's setup action)
[[keys.command]]
key = "%s"
type = "plugin_action"
command = "%s"
description = "Context & limits bar: open in this tab"
""" % (HOTKEY, COMMAND)


def step_statusline():
    out = subprocess.run([sys.executable, os.path.join(HERE, "install-statusline.py")],
                         capture_output=True, text=True)
    lines = out.stdout.strip().splitlines()
    return lines[0] if lines else "statusLine: unchanged"


def step_config():
    report = []
    try:
        with open(CONFIG) as f:
            text = f.read()
    except FileNotFoundError:
        text = ""
    additions = ""

    if re.search(r"^\[ui\.sidebar\.agents\]", text, flags=re.M):
        report.append("sidebar rows: already configured, left unchanged")
    else:
        additions += SIDEBAR_BLOCK
        report.append("sidebar rows: added")

    if COMMAND in text:
        report.append("hotkey: already configured, left unchanged")
    elif re.search(r'^\s*key\s*=\s*"%s"' % re.escape(HOTKEY), text, flags=re.M):
        report.append("hotkey: %s is taken by another command, not changed" % HOTKEY)
    else:
        additions += HOTKEY_BLOCK
        report.append("hotkey: %s added" % HOTKEY)

    if additions:
        os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
        if text:
            shutil.copy(CONFIG, "%s.bak-%d" % (CONFIG, int(time.time())))
        with open(CONFIG, "a") as f:
            f.write(additions)
        subprocess.run([HERDR, "server", "reload-config"], capture_output=True, text=True)
    return report


def main():
    print("Context & Limits Bar setup")
    print("  " + step_statusline())
    for line in step_config():
        print("  " + line)
    print("Done. Start an agent in any tab to see the bar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
