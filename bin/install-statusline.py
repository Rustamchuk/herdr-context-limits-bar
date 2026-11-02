#!/usr/bin/env python3
"""Point Claude Code's statusLine at this plugin's statusline.py.

- No statusLine yet, or it already points here: writes it (backup first).
- Some other statusLine is set: changes nothing and prints how to switch.
Usage: python3 install-statusline.py [--force]   (--force replaces any statusLine)
"""
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SETTINGS = os.path.join(os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude"), "settings.json")
COMMAND = "python3 '%s'" % os.path.join(HERE, "statusline.py")
MARK = "context-limits-bar"


def main():
    force = "--force" in sys.argv
    try:
        with open(SETTINGS) as f:
            settings = json.load(f)
    except FileNotFoundError:
        settings = {}
    except ValueError:
        print("settings.json is not valid JSON; fix it first: %s" % SETTINGS)
        return 1

    current = (settings.get("statusLine") or {}).get("command", "")
    if current and MARK not in current and not force:
        print("statusLine is already set to another command, so it was left unchanged:")
        print("  " + current)
        print("Run the action again with --force to replace it.")
        return 0
    if current == COMMAND:
        print("statusLine already points here. Nothing to do.")
        return 0

    if os.path.exists(SETTINGS):
        shutil.copy(SETTINGS, "%s.bak-%d" % (SETTINGS, int(time.time())))
    settings["statusLine"] = {"type": "command", "command": COMMAND}
    os.makedirs(os.path.dirname(SETTINGS), exist_ok=True)
    with open(SETTINGS, "w") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print("statusLine set to: " + COMMAND)
    print("A backup of settings.json was written next to it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
