"""Subscription limit windows for Claude Code and Codex.

Sources, freshest wins per provider:
  Claude: the cache written by statusline.py while Claude Code runs, and the
          `cachedUsageUtilization` block in ~/.claude.json.
  Codex:  `rate_limits` records in the newest rollout files under ~/.codex/sessions.

A window is {"used": int percent, "resets_at": epoch seconds, "window_minutes": int}.
Stdlib only.
"""
import glob
import json
import os
import time
from datetime import datetime

HOME = os.path.expanduser("~")
CLAUDE_DIR = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(HOME, ".claude")
CLAUDE_JSON = os.environ.get("CLAUDE_JSON_PATH") or os.path.join(HOME, ".claude.json")
CODEX_HOME = os.environ.get("CODEX_HOME") or os.path.join(HOME, ".codex")
CACHE_DIR = os.path.join(CLAUDE_DIR, "context-limits-bar")
CACHE_FILE = os.path.join(CACHE_DIR, "claude-limits.json")

FIVE_HOUR = 300
SEVEN_DAY = 10080


def _epoch(value):
    """Epoch seconds from an int, a numeric string, or an ISO 8601 string."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    try:
        return int(float(value))
    except (TypeError, ValueError):
        pass
    try:
        return int(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


def _window(used, resets_at, minutes):
    if used is None:
        return None
    return {"used": int(round(float(used))), "resets_at": _epoch(resets_at), "window_minutes": minutes}


def write_claude_cache(rate_limits, now=None):
    """Store the statusLine rate_limits block. Called by statusline.py."""
    now = now or time.time()
    payload = {"fetched_at": int(now)}
    five = rate_limits.get("five_hour") or {}
    seven = rate_limits.get("seven_day") or {}
    if five.get("used_percentage") is not None:
        payload["five_hour"] = _window(five["used_percentage"], five.get("resets_at"), FIVE_HOUR)
    if seven.get("used_percentage") is not None:
        payload["seven_day"] = _window(seven["used_percentage"], seven.get("resets_at"), SEVEN_DAY)
    os.makedirs(CACHE_DIR, exist_ok=True)
    tmp = CACHE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(payload, f)
    os.replace(tmp, CACHE_FILE)


def _claude_from_cache():
    try:
        with open(CACHE_FILE) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}, 0
    windows = {}
    if data.get("five_hour"):
        windows["5h"] = data["five_hour"]
    if data.get("seven_day"):
        windows["7d"] = data["seven_day"]
    return windows, data.get("fetched_at", 0)


def _claude_from_claude_json():
    try:
        with open(CLAUDE_JSON) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}, 0
    cached = data.get("cachedUsageUtilization") or {}
    util = cached.get("utilization") or {}
    windows = {}
    if util.get("five_hour"):
        w = util["five_hour"]
        windows["5h"] = _window(w.get("utilization"), w.get("resets_at"), FIVE_HOUR)
    if util.get("seven_day"):
        w = util["seven_day"]
        windows["7d"] = _window(w.get("utilization"), w.get("resets_at"), SEVEN_DAY)
    return windows, int((cached.get("fetchedAtMs") or 0) / 1000)


def claude_limits(now):
    cache, cache_t = _claude_from_cache()
    fallback, fallback_t = _claude_from_claude_json()
    chosen = cache if cache_t >= fallback_t else fallback
    return {k: w for k, w in chosen.items() if w and (not w["resets_at"] or w["resets_at"] > now)}


def _find_rate_limits(obj):
    if isinstance(obj, dict):
        rl = obj.get("rate_limits")
        if isinstance(rl, dict):
            return rl
        for v in obj.values():
            found = _find_rate_limits(v)
            if found:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _find_rate_limits(v)
            if found:
                return found
    return None


def codex_limits(now, max_files=3, max_age_days=8):
    files = glob.glob(os.path.join(CODEX_HOME, "sessions", "**", "rollout-*.jsonl"), recursive=True)
    files = [f for f in files if now - os.path.getmtime(f) < max_age_days * 86400]
    files.sort(key=os.path.getmtime, reverse=True)
    for path in files[:max_files]:
        found = None
        try:
            with open(path, errors="replace") as f:
                for line in f:
                    if "rate_limits" not in line:
                        continue
                    try:
                        rl = _find_rate_limits(json.loads(line))
                    except ValueError:
                        continue
                    if rl and rl.get("primary"):
                        found = rl
        except OSError:
            continue
        if not found:
            continue
        p = found["primary"]
        minutes = p.get("window_minutes") or SEVEN_DAY
        resets = _epoch(p.get("resets_at"))
        if resets and resets <= now:
            continue
        label = {FIVE_HOUR: "5h", SEVEN_DAY: "7d"}.get(minutes, "%dm" % minutes)
        return {label: _window(p.get("used_percent"), resets, minutes)}
    return {}


def all_limits(now=None):
    """{"claude": {"5h": window, ...}, "codex": {...}} for live windows only."""
    now = now or time.time()
    result = {}
    claude = claude_limits(now)
    if claude:
        result["claude"] = claude
    codex = codex_limits(now)
    if codex:
        result["codex"] = codex
    return result


def _rollout_cwd(path):
    """cwd from the session_meta record (first line of a rollout)."""
    try:
        with open(path, errors="replace") as f:
            first = f.readline()
        meta = json.loads(first).get("payload") or {}
        return meta.get("cwd")
    except (OSError, ValueError, AttributeError):
        return None


def codex_session_for_cwd(cwd, now=None, max_files=50, max_age_days=3):
    """Context of the most recent Codex session started in `cwd`.

    herdr does not report Codex session ids, so the rollout is matched by the
    working directory. Returns {"input": tokens, "window": tokens} or None.
    """
    now = now or time.time()
    if not cwd:
        return None
    files = glob.glob(os.path.join(CODEX_HOME, "sessions", "**", "rollout-*.jsonl"), recursive=True)
    files = [f for f in files if now - os.path.getmtime(f) < max_age_days * 86400]
    files.sort(key=os.path.getmtime, reverse=True)
    target = os.path.realpath(cwd)
    for path in files[:max_files]:
        meta_cwd = _rollout_cwd(path)
        if not meta_cwd or os.path.realpath(meta_cwd) != target:
            continue
        return _codex_last_usage(path)
    return None


def _codex_last_usage(path):
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            if size > 512 * 1024:
                f.seek(size - 512 * 1024)
                f.readline()
            lines = f.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        if '"token_count"' not in line:
            continue
        try:
            info = json.loads(line)["payload"]["info"]
        except (ValueError, KeyError, TypeError):
            continue
        if not info or not info.get("last_token_usage"):
            continue
        return {
            "input": info["last_token_usage"].get("input_tokens", 0),
            "window": info.get("model_context_window"),
        }
    return None
