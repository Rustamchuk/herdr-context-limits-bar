#!/usr/bin/env python3
"""Claude Code statusLine command.

Reads Claude Code's JSON from stdin, stores rate_limits for the bar, and prints
a short status line. Stdlib only.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import limits  # noqa: E402


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        data = {}
    rate_limits = data.get("rate_limits") or {}
    if rate_limits:
        try:
            limits.write_claude_cache(rate_limits)
        except OSError:
            pass
    parts = []
    for key, label in (("five_hour", "5h"), ("seven_day", "7d")):
        win = rate_limits.get(key) or {}
        if win.get("used_percentage") is not None:
            parts.append("%s %d%%" % (label, round(float(win["used_percentage"]))))
    print("  ·  ".join(parts))


if __name__ == "__main__":
    main()
