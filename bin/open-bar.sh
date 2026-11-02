#!/bin/bash
# Opens the bottom bar in the tab of the event (or the focused pane for the action).
# plugin pane open always targets the focused tab, so the bar is a split of
# HERDR_PANE_ID running bin/statusbar.py. Idempotent per tab.
set -uo pipefail

[[ -n "${HERDR_TAB_ID:-}" && -n "${HERDR_PANE_ID:-}" ]] || exit 0

HERDR_BIN="${HERDR_BIN_PATH:-herdr}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_DIR="${HERDR_PLUGIN_STATE_DIR:-$HOME/.local/state/herdr/plugins/context-limits-bar}"
mkdir -p "$STATE_DIR"

# Locate the usagebar plugin (limits source). Optional: the bar works without it.
USAGEBAR_BIN_PATH="${USAGEBAR_BIN:-}"
if [[ -z "$USAGEBAR_BIN_PATH" ]]; then
  USAGEBAR_ROOT="$(python3 - <<'PY'
import json, os
p = os.path.expanduser("~/.config/herdr/plugins.json")
try:
    for e in json.load(open(p)):
        if e.get("plugin_id") == "usagebar":
            print(e.get("plugin_root", ""))
            break
except Exception:
    pass
PY
)"
  [[ -n "$USAGEBAR_ROOT" ]] && USAGEBAR_BIN_PATH="$USAGEBAR_ROOT/bin/usagebar"
fi
[[ -x "$USAGEBAR_BIN_PATH" ]] || USAGEBAR_BIN_PATH=""

TAB_KEY="$(printf '%s' "$HERDR_TAB_ID" | tr ':/' '__')"
STATE_FILE="$STATE_DIR/bar-pane-$TAB_KEY"
LOCK_DIR="$STATE_DIR/open-$TAB_KEY.lock"
mkdir "$LOCK_DIR" 2>/dev/null || exit 0
trap 'rmdir "$LOCK_DIR" 2>/dev/null' EXIT

if [[ -s "$STATE_FILE" ]]; then
  existing="$(<"$STATE_FILE")"
  if "$HERDR_BIN" pane get "$existing" >/dev/null 2>&1; then
    exit 0
  fi
  rm -f "$STATE_FILE"
fi

response="$("$HERDR_BIN" pane split --pane "$HERDR_PANE_ID" --direction down --cwd "$SCRIPT_DIR/.." --no-focus 2>/dev/null)" || exit 0
pane_id="$(printf '%s' "$response" | sed -En 's/.*"pane_id"[[:space:]]*:[[:space:]]*"([^"]*)".*/\1/p' | head -1)"
[[ -n "$pane_id" ]] || exit 0
printf '%s' "$pane_id" > "$STATE_FILE"

cmd="$(printf 'clear; HERDR_TAB_ID=%q HERDR_BIN_PATH=%q USAGEBAR_BIN=%q HERDR_PLUGIN_STATE_DIR=%q python3 %q' \
  "$HERDR_TAB_ID" "$HERDR_BIN" "$USAGEBAR_BIN_PATH" "$STATE_DIR" "$SCRIPT_DIR/statusbar.py")"
"$HERDR_BIN" pane run "$pane_id" "$cmd" >/dev/null 2>&1 || exit 0
sleep 0.5
"$HERDR_BIN" pane resize --pane "$pane_id" --direction down --amount "${CONTEXT_LIMITS_BAR_RESIZE:-0.42}" >/dev/null 2>&1 || true
