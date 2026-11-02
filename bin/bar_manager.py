#!/usr/bin/env python3
"""Opens and closes the bottom bar, keeping each bar tied to its agent pane.

  bar_manager.py open    open a bar in this tab if it has an agent and no live bar
  bar_manager.py closed  a pane closed: close the bars anchored to it, forget closed bars

Bars are recorded in $HERDR_PLUGIN_STATE_DIR/bars.json as
  {"<bar pane>": {"tab": "<tab id>", "anchor": "<agent pane id>"}}
Stdlib only.
"""
import json
import os
import shlex
import subprocess
import sys
import time

HERDR = os.environ.get("HERDR_BIN_PATH") or "herdr"
PLUGIN_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STATE_DIR = os.environ.get("HERDR_PLUGIN_STATE_DIR") or os.path.expanduser(
    "~/.local/state/herdr/plugins/context-limits-bar")
BARS = os.path.join(STATE_DIR, "bars.json")
RESIZE = os.environ.get("CONTEXT_LIMITS_BAR_RESIZE", "0.42")


def herdr(*args):
    try:
        out = subprocess.run([HERDR] + list(args), capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    try:
        return json.loads(out.stdout)["result"]
    except (ValueError, KeyError):
        return None


def load_bars():
    try:
        with open(BARS) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_bars(bars):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(BARS, "w") as f:
        json.dump(bars, f)


def pane_alive(pane_id):
    return herdr("pane", "get", pane_id) is not None


SUPPORTED = ("claude", "codex")


def agent_panes_in_tab(tab_id):
    """Panes of supported agents (Claude Code, Codex) in the tab."""
    result = herdr("agent", "list") or {}
    return [a["pane_id"] for a in result.get("agents", [])
            if a.get("tab_id") == tab_id and a.get("pane_id") and a.get("agent") in SUPPORTED]


def open_bar():
    tab = os.environ.get("HERDR_TAB_ID", "")
    if not tab:
        return
    agents = agent_panes_in_tab(tab)
    if not agents:  # plain terminal tab, or an agent we do not support: no bar
        return
    bars = load_bars()
    # Forget bars whose panes are gone, then stop if this tab already has a live bar.
    for bar in list(bars):
        if not pane_alive(bar):
            del bars[bar]
    if any(info.get("tab") == tab for info in bars.values()):
        save_bars(bars)
        return

    event_pane = os.environ.get("HERDR_PANE_ID", "")
    anchor = event_pane if event_pane in agents else agents[0]
    split = herdr("pane", "split", "--pane", anchor, "--direction", "down",
                  "--cwd", PLUGIN_ROOT, "--no-focus")
    bar = ((split or {}).get("pane") or {}).get("pane_id")
    if not bar:
        save_bars(bars)
        return
    bars[bar] = {"tab": tab, "anchor": anchor}
    save_bars(bars)

    cmd = ("clear; HERDR_TAB_ID=%s HERDR_ANCHOR_PANE=%s HERDR_BAR_PANE=%s HERDR_BIN_PATH=%s "
           "HERDR_PLUGIN_STATE_DIR=%s python3 %s") % (
        shlex.quote(tab), shlex.quote(anchor), shlex.quote(bar), shlex.quote(HERDR), shlex.quote(STATE_DIR),
        shlex.quote(os.path.join(PLUGIN_ROOT, "bin", "statusbar.py")))
    subprocess.run([HERDR, "pane", "run", bar, cmd], capture_output=True, timeout=15)
    time.sleep(0.5)
    subprocess.run([HERDR, "pane", "resize", "--pane", bar, "--direction", "down", "--amount", RESIZE],
                   capture_output=True, timeout=15)


def on_closed():
    closed = os.environ.get("HERDR_PANE_ID", "")
    if not closed:
        return
    bars = load_bars()
    bars.pop(closed, None)  # the bar itself was closed
    for bar, info in list(bars.items()):
        if info.get("anchor") == closed:
            if pane_alive(bar):
                subprocess.run([HERDR, "pane", "close", bar], capture_output=True, timeout=15)
            del bars[bar]
    save_bars(bars)


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    if action == "open":
        open_bar()
    elif action == "closed":
        on_closed()
    else:
        print("usage: bar_manager.py open|closed", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
