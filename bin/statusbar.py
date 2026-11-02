#!/usr/bin/env python3
"""Bottom bar for one herdr tab.

Left:  context fill of agents in this tab (herdr `tokens.context`).
Right: subscription limit windows (usagebar `collect --all`, plus the fresher
       Claude statusLine cache), each with reset time and a pace warning.

Stdlib only. Config: $HERDR_PLUGIN_CONFIG_DIR/config.toml (optional).
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERDR = os.environ.get("HERDR_BIN_PATH") or "herdr"
CONFIG_DIR = os.environ.get("HERDR_PLUGIN_CONFIG_DIR") or os.path.expanduser(
    "~/.config/herdr/plugins/config/context-limits-bar")
STATE_DIR = os.environ.get("HERDR_PLUGIN_STATE_DIR") or os.path.expanduser(
    "~/.local/state/herdr/plugins/context-limits-bar")
USAGEBAR = os.environ.get("USAGEBAR_BIN") or ""
CLAUDE_DIR = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
SAMPLES = os.path.join(STATE_DIR, "samples.json")

DEFAULTS = {"context_window_tokens": 800000, "refresh_seconds": 15, "bar_cells": 5}
ICONS = {"claude": "✳", "codex": "◉", "opencode": "◆", "grok": "𝕏"}
WINDOW_LABEL = {300: "5h", 10080: "7d"}
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


def render_context(agents, cfg):
    window = cfg["context_window_tokens"]
    parts = []
    for a in agents:
        tokens = parse_tokens((a.get("tokens") or {}).get("context"))
        if tokens is None:
            continue
        percent = min(100, round(tokens / window * 100))
        icon = ICONS.get(a.get("agent", ""), "•")
        parts.append("%s %s %d%% %s" % (icon, colored_bar(percent, cfg["bar_cells"]), percent, fmt_tokens(tokens)))
    return "  ·  ".join(parts) if parts else "context: —"


# ---------- limits (right) ----------

def claude_cache_path():
    return os.path.join(CLAUDE_DIR, "herdr-usagebar", "claude-limits-latest.json")


def collect_limits():
    if not USAGEBAR:
        return None
    try:
        out = subprocess.run([USAGEBAR, "collect", "--all"], capture_output=True, text=True, timeout=20).stdout
        providers = json.loads(out).get("providers", [])
    except Exception:
        return None
    # usagebar prefers a stale ~/.claude.json value; use the statusLine cache when it is fresher.
    try:
        with open(claude_cache_path()) as f:
            cache = json.load(f)
        for p in providers:
            if (p.get("ProviderID") or "").lower().startswith("claude") and \
                    cache.get("fetchedAtMs", 0) > (p.get("FetchedAtMs") or 0):
                if cache.get("fiveHour"):
                    p["Primary"] = cache["fiveHour"]
                if cache.get("sevenDay"):
                    p["Secondary"] = cache["sevenDay"]
                p["Note"] = None
    except (OSError, ValueError):
        pass
    return providers


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


def render_limits(providers, samples, now):
    if providers is None:
        return "limits: usagebar not found"
    items = []
    for p in providers:
        pid = (p.get("ProviderID") or "").lower()
        icon = ICONS.get(next((k for k in ICONS if pid.startswith(k)), ""), "•")
        for slot in ("Primary", "Secondary", "Tertiary"):
            win = p.get(slot)
            if not win:
                continue
            resets = win.get("resetsAt")
            if resets and resets <= now:
                continue
            used = round(float(win.get("usedPercentage", 0)))
            label = WINDOW_LABEL.get(win.get("windowMinutes") or 0, "")
            key = "%s:%s" % (pid, slot)
            samples.setdefault(key, []).append([now, used])
            samples[key] = [s for s in samples[key] if now - s[0] <= PACE_KEEP_S]
            text = "%s%s %s %d%%" % (icon, label, colored_bar(used, 5), used)
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


def main():
    tab = os.environ.get("HERDR_TAB_ID", "")
    while True:
        cfg = load_config()
        now = time.time()
        samples = load_samples()
        left = render_context(agents_in_tab(tab), cfg)
        right = render_limits(collect_limits(), samples, now)
        save_samples(samples)
        width = shutil.get_terminal_size((120, 4)).columns
        sys.stdout.write("\x1b[2K\r" + compose(left, right, width - 1))
        sys.stdout.flush()
        time.sleep(max(5, cfg["refresh_seconds"]))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
