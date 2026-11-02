#!/usr/bin/env python3
"""Bottom bar for one herdr tab.

Left:  context fill of agents in this tab (herdr `tokens.context`).
Right: subscription limit windows (Claude, Codex) with reset time and a pace warning.

Stdlib only. Config: $HERDR_PLUGIN_CONFIG_DIR/config.toml (optional).
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import limits  # noqa: E402

HERDR = os.environ.get("HERDR_BIN_PATH") or "herdr"
CONFIG_DIR = os.environ.get("HERDR_PLUGIN_CONFIG_DIR") or os.path.expanduser(
    "~/.config/herdr/plugins/config/context-limits-bar")
STATE_DIR = os.environ.get("HERDR_PLUGIN_STATE_DIR") or os.path.expanduser(
    "~/.local/state/herdr/plugins/context-limits-bar")
SAMPLES = os.path.join(STATE_DIR, "samples.json")

DEFAULTS = {"context_window_tokens": 800000, "refresh_seconds": 15, "bar_cells": 5}
ICONS = {"claude": "✳", "codex": "◉", "opencode": "◆", "grok": "𝕏"}
PACE_MIN_SPAN_S = 300   # projection needs >= 5 min of samples
PACE_KEEP_S = 3600      # samples kept for 1 h
ANSI = {"ok": "32", "warn": "33", "high": "31"}


def load_config():
    cfg = dict(DEFAULTS)
    try:
        with open(os.path.join(CONFIG_DIR, "config.toml")) as f:
            for line in f:
                line = line.split("#", 1)[0].strip()
                m = re.match(r"^(\w+)\s*=\s*(\d+)$", line)
                if m and m.group(1) in cfg:
                    cfg[m.group(1)] = int(m.group(2))
    except OSError:
        pass
    return cfg


def parse_tokens(text):
    m = re.search(r"([\d.]+)\s*([kKmM]?)", text or "")
    if not m:
        return None
    mult = {"k": 1_000, "m": 1_000_000}.get(m.group(2).lower(), 1)
    return int(float(m.group(1)) * mult)


def fmt_tokens(n):
    if n < 1000:
        return str(n)
    if n < 1_000_000:
        return "%dk" % round(n / 1000)
    return "%.1fM" % (n / 1_000_000)


def fmt_dur(seconds):
    s = max(0, int(seconds))
    if s >= 86400:
        return "%dd" % (s // 86400)
    if s >= 3600:
        return "%dh" % (s // 3600)
    return "%dm" % (s // 60)


def bar(percent, cells):
    eighths = ["", "▏", "▎", "▍", "▌", "▋", "▊", "▉"]
    total = int(round(max(0.0, min(100.0, percent)) / 100 * cells * 8))
    full, rem = divmod(total, 8)
    part = eighths[rem] if full < cells else ""
    filled = full + (1 if part else 0)
    return "█" * min(full, cells) + part + "░" * max(0, cells - filled)


def colored_bar(percent, cells):
    tone = "high" if percent >= 80 else "warn" if percent >= 50 else "ok"
    return "\x1b[%sm%s\x1b[0m" % (ANSI[tone], bar(percent, cells))


def visible_len(text):
    return len(re.sub(r"\x1b\[[0-9;]*m", "", text))


# ---------- context (left) ----------

def agents_in_tab(tab_id):
    try:
        out = subprocess.run([HERDR, "agent", "list"], capture_output=True, text=True, timeout=10).stdout
        agents = json.loads(out)["result"]["agents"]
    except Exception:
        return []
    return [a for a in agents if a.get("tab_id") == tab_id]


SUPPORTED = ("claude", "codex")


def render_context(agents, cfg):
    parts = []
    for a in agents:
        if a.get("agent") not in SUPPORTED:
            continue
        tokens_map = a.get("tokens") or {}
        tokens = parse_tokens(tokens_map.get("context"))
        if tokens is None:
            continue
        window = int(tokens_map["window"]) if str(tokens_map.get("window", "")).isdigit() else cfg["context_window_tokens"]
        percent = min(100, round(tokens / window * 100))
        icon = ICONS.get(a.get("agent", ""), "•")
        parts.append("%s %s %d%% %s" % (icon, colored_bar(percent, cfg["bar_cells"]), percent, fmt_tokens(tokens)))
    return "  ·  ".join(parts) if parts else "context: —"


# ---------- limits (right) ----------

def load_samples():
    try:
        with open(SAMPLES) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_samples(samples):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(SAMPLES, "w") as f:
            json.dump(samples, f)
    except OSError:
        pass


def minutes_to_full(samples, key, used, now):
    pts = [p for p in samples.get(key, []) if now - p[0] <= PACE_KEEP_S]
    if len(pts) < 2 or pts[-1][0] - pts[0][0] < PACE_MIN_SPAN_S:
        return None
    du = pts[-1][1] - pts[0][1]
    if du <= 0:
        return None
    rate = du / (pts[-1][0] - pts[0][0])  # percent per second
    return (100 - used) / rate / 60


def render_limits(data, samples, now, providers):
    items = []
    for provider in SUPPORTED:
        if provider not in providers:
            continue
        for label in ("5h", "7d"):
            win = data.get(provider, {}).get(label)
            if not win:
                continue
            used = win["used"]
            resets = win["resets_at"]
            key = "%s:%s" % (provider, label)
            samples.setdefault(key, []).append([now, used])
            samples[key] = [s for s in samples[key] if now - s[0] <= PACE_KEEP_S]
            text = "%s%s %s %d%%" % (ICONS[provider], label, colored_bar(used, 5), used)
            if resets:
                text += " ↻%s" % fmt_dur(resets - now)
                to_full = minutes_to_full(samples, key, used, now)
                if to_full is not None and to_full * 60 < resets - now:
                    text += " ⚠~%s" % fmt_dur(to_full * 60)
            items.append(text)
    return "  ·  ".join(items) if items else "limits: no data"


# ---------- layout ----------

def compose(left, right, width):
    gap = width - visible_len(left) - visible_len(right)
    return left + " " * gap + right if gap >= 2 else left + "  ·  " + right


def pane_has_agent(pane_id):
    """True/False when herdr knows the pane; None when the query failed."""
    try:
        out = subprocess.run([HERDR, "pane", "get", pane_id], capture_output=True, text=True, timeout=10)
        if out.returncode != 0:
            return False  # pane is gone
        pane = json.loads(out.stdout)["result"]["pane"]
    except (OSError, subprocess.SubprocessError, ValueError, KeyError):
        return None
    return bool(pane.get("agent"))


def close_self():
    bar = os.environ.get("HERDR_BAR_PANE", "")
    if bar:
        subprocess.run([HERDR, "pane", "close", bar], capture_output=True, timeout=10)


def main():
    tab = os.environ.get("HERDR_TAB_ID", "")
    anchor = os.environ.get("HERDR_ANCHOR_PANE", "")
    misses = 0
    next_draw = 0.0
    cfg = load_config()
    while True:
        if anchor:
            # The bar belongs to the agent: when it exits (e.g. Ctrl+C), the bar closes.
            has = pane_has_agent(anchor)
            if has is False:
                misses += 1
                if misses >= 2:
                    close_self()
                    return
            elif has:
                misses = 0
        now = time.time()
        if now >= next_draw:
            cfg = load_config()
            samples = load_samples()
            agents = agents_in_tab(tab)
            left = render_context(agents, cfg)
            data = limits.all_limits(now)
            providers = {a.get("agent") for a in agents if a.get("agent") in SUPPORTED}
            right = render_limits(data, samples, now, providers)
            save_samples(samples)
            width = shutil.get_terminal_size((120, 4)).columns
            sys.stdout.write("\x1b[2K\r" + compose(left, right, width - 1))
            sys.stdout.flush()
            next_draw = now + max(5, cfg["refresh_seconds"])
        time.sleep(2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
