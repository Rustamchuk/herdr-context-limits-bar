#!/usr/bin/env python3
"""Publishes sidebar tokens for every agent pane: context, provider, limit.

Runs on agent events. Sidebar rows use the tokens:
  context  "⛁ 269k"   tokens in the current session context (Claude, Codex)
  provider "claude"    agent name
  limit    "5h 3%"     used percent of the most relevant subscription window
  window   "258400"    context window size in tokens (Codex; read by the bar)
Only changed values are sent. Stdlib only.
"""
import glob
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import limits  # noqa: E402

HERDR = os.environ.get("HERDR_BIN_PATH") or "herdr"
SOURCE = "context-limits-bar"
STATE_DIR = os.environ.get("HERDR_PLUGIN_STATE_DIR") or os.path.expanduser(
    "~/.local/state/herdr/plugins/context-limits-bar")
STATE = os.path.join(STATE_DIR, "sidebar-state.json")
TAIL_BYTES = 512 * 1024
CONTEXT_KEY = "context"
LIMIT_KEY = "limit"
PROVIDER_KEY = "provider"
WINDOW_KEY = "window"


def herdr_json(*args):
    out = subprocess.run([HERDR] + list(args), capture_output=True, text=True, timeout=15).stdout
    return json.loads(out)["result"]


def fmt_tokens(n):
    if n < 1000:
        return str(n)
    if n < 1_000_000:
        return "%dk" % round(n / 1000)
    return "%.1fM" % (n / 1_000_000)


def tail_lines(path, nbytes=TAIL_BYTES):
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        if size > nbytes:
            f.seek(size - nbytes)
            f.readline()  # drop the partial first line
        data = f.read()
    return data.decode("utf-8", errors="replace").splitlines()


def claude_transcript(cwd, session_id):
    # Claude names project folders by replacing every non-alphanumeric character with "-".
    slug = re.sub(r"[^A-Za-z0-9]", "-", cwd)
    path = os.path.expanduser("~/.claude/projects/%s/%s.jsonl" % (slug, session_id))
    return path if os.path.exists(path) else None


def claude_context(cwd, session_id):
    path = claude_transcript(cwd, session_id)
    if not path:
        return None
    for line in reversed(tail_lines(path)):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        msg = d.get("message") or {}
        usage = msg.get("usage")
        if d.get("type") == "assistant" and isinstance(usage, dict):
            return (usage.get("input_tokens", 0) + usage.get("cache_read_input_tokens", 0)
                    + usage.get("cache_creation_input_tokens", 0))
    return None


def limit_text(provider_limits):
    for label in ("5h", "7d"):
        win = (provider_limits or {}).get(label)
        if win:
            return "%s %d%%" % (label, win["used"])
    return None


SUPPORTED = ("claude", "codex")


def desired_tokens(agent, live):
    """Token values for one agent pane; an empty dict clears them all."""
    name = agent.get("agent", "")
    if name not in SUPPORTED:
        return {}
    session = agent.get("agent_session") or {}
    session_id = session.get("value") if session.get("kind") == "id" else None
    cwd = agent.get("cwd") or ""
    tokens = {PROVIDER_KEY: name}
    if name == "claude" and session_id:
        ctx = claude_context(cwd, session_id)
        window = None
    else:
        usage = limits.codex_session_for_cwd(cwd) if name == "codex" else None
        ctx = usage["input"] if usage else None
        window = usage.get("window") if usage else None
    if ctx is not None:
        tokens[CONTEXT_KEY] = "⛁ %s" % fmt_tokens(ctx)
    if window:
        tokens[WINDOW_KEY] = str(window)
    lim = limit_text(live.get(name))
    if lim:
        tokens[LIMIT_KEY] = lim
    return tokens


def report(pane_id, tokens, previous):
    changed = False
    args = []
    for key in (CONTEXT_KEY, LIMIT_KEY, PROVIDER_KEY, WINDOW_KEY):
        if key in tokens:
            if previous.get(key) != tokens[key]:
                args += ["--token", "%s=%s" % (key, tokens[key])]
                changed = True
        elif key in previous:
            args += ["--clear-token", key]
            changed = True
    if changed:
        subprocess.run([HERDR, "pane", "report-metadata", pane_id, "--source", SOURCE] + args,
                       capture_output=True, timeout=15)
    return {k: tokens[k] for k in tokens}


def main():
    now = time.time()
    live = limits.all_limits(now)
    try:
        with open(STATE) as f:
            state = json.load(f)
    except (OSError, ValueError):
        state = {}
    agents = herdr_json("agent", "list").get("agents", [])
    seen = {}
    for agent in agents:
        pane = agent.get("pane_id")
        if not pane:
            continue
        tokens = desired_tokens(agent, live)
        seen[pane] = report(pane, tokens, state.get(pane, {}))
    # Panes that had our tokens but no longer run an agent: clear them.
    for pane, previous in state.items():
        if pane not in seen and previous:
            report(pane, {}, previous)
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(STATE, "w") as f:
        json.dump(seen, f)


if __name__ == "__main__":
    try:
        main()
    except (OSError, subprocess.SubprocessError, ValueError):
        sys.exit(0)
