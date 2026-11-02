<div align="center">

# 🎛️ Context & Limits Bar

**A live, colorful status bar for [herdr](https://herdr.dev): how full your agent's context is, and how close your subscription limits are.**

[![License: MIT](https://img.shields.io/badge/License-MIT-7c3aed.svg?style=for-the-badge)](LICENSE)
[![herdr](https://img.shields.io/badge/herdr-0.7.4%2B-6E56CF?style=for-the-badge)](https://herdr.dev)
[![Python](https://img.shields.io/badge/python-3.9%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org)
[![Platforms](https://img.shields.io/badge/macOS%20%7C%20Linux-111827?style=for-the-badge)](#)
[![No deps](https://img.shields.io/badge/dependencies-none-10b981?style=for-the-badge)](#)

<img src="assets/preview.svg" alt="Context and limits bar preview" width="100%">

</div>

---

## ✨ What you get

| | |
| --- | --- |
| 🧠 **Context fill** | Per agent in the tab: a mini bar, percent and tokens. Green → yellow → red as it fills. |
| ⏳ **Limit windows** | Your 5h / 7d subscription windows with time until reset. |
| 🔮 **Burn warning** | `⚠~3h` appears when your current pace hits 100% before the window resets. |
| 🪟 **Auto-open** | Appears at the bottom of a tab when an agent starts there. Once per tab. |
| 🧩 **Zero dependencies** | One Python file, standard library only. |

---

## 🚀 Quick start

**1. Install the plugin**

```bash
herdr plugin install Rustamchuk/context-limits-bar --yes
```

**2. (Optional, for limits) install the usage plugin**

```bash
herdr plugin install silverwolfdoc/herdr-usage-bar --yes
```

**3. Start an agent** in any herdr tab. The bar appears at the bottom. Done. 🎉

Check it is enabled any time with `herdr plugin list`.

---

## 🎮 Usage

| Action | How |
| --- | --- |
| 🤖 **Automatic** | Start Claude Code, Codex or another agent in a tab. |
| 🖐️ **Manual** | `herdr plugin action invoke context-limits-bar.open-bar` |
| ⌨️ **Keybinding** | See below. |

Add a shortcut to `~/.config/herdr/config.toml`:

```toml
[[keys.command]]
key = "ctrl+shift+b"
type = "plugin_action"
command = "context-limits-bar.open-bar"
description = "Context & limits bar in this tab"
```

Then run `herdr server reload-config`.

The bar is idempotent: opening it in a tab that already has one does nothing.

---

## 📊 Reading the bar

```
✳ █▌░░░░ 24% 193k          ✳5h ▏░░░░ 3% ↻4h  ·  ✳7d ▏░░░░ 2% ↻7h  ·  ◉7d ░░░░░ 1% ↻2d
│ │        │    │           │   │      │       │     │       │       │   │
│ │        │    └ tokens    │   │      │       │     │       │       │   └ resets in 2 days
│ │        └ context %      │   │      │       │     │       │       └ used 1 %
│ └ fill bar                │   │      │       │     │       └ 7-day Codex window
│                           │   │      │       │     └ resets in 7 hours
└ agent icon                │   │      │       └ used 2 %
                            │   │      └ resets in 4 hours
                            └ 5-hour Claude window
```

| Icon | Agent |
| :---: | --- |
| ✳ | Claude Code |
| ◉ | Codex |
| ◆ | OpenCode |
| 𝕏 | Grok |
| • | anything else |

**Bar colors:** 🟢 under 50 % · 🟡 50 – 79 % · 🔴 80 % and up.

**Warning:** `⚠~3h` means "at this pace you run out in about 3 hours, before the window resets."

---

## 🧠 Claude limits (5h / 7d)

Claude Code shares its limits through a status line hook. Add this to `~/.claude/settings.json`, using the path from `herdr plugin list` for the usage plugin:

```json
{
  "statusLine": {
    "type": "command",
    "command": "bash '/path/to/herdr-usage-bar/bin/run-statusline.sh'"
  }
}
```

Limits refresh while you use Claude Code. If you have not used Claude for a while, its percentages are old.

---

## ⚙️ Configuration

Optional. Copy the example into the plugin's config directory:

```bash
cp config.example.toml "$(herdr plugin config-dir context-limits-bar)/config.toml"
```

| Key | Default | What it does |
| --- | --- | --- |
| `context_window_tokens` | `800000` | Context size used for the percentage. Set it to your model's real window, e.g. `200000`. |
| `refresh_seconds` | `15` | How often the bar redraws (minimum 5). |
| `bar_cells` | `5` | Width of each mini bar. |

Environment overrides:

| Variable | Purpose |
| --- | --- |
| `USAGEBAR_BIN` | Path to the usage plugin's binary, if it is not found automatically. |
| `CLAUDE_CONFIG_DIR` | Claude config directory, if not `~/.claude`. |
| `CONTEXT_LIMITS_BAR_RESIZE` | Bar height as a split ratio (default `0.42`). |

---

## 🛠️ Troubleshooting

| You see | Cause | Fix |
| --- | --- | --- |
| No bar when an agent starts | Plugin disabled, or the event did not fire | `herdr plugin list`, then `herdr plugin log list --plugin context-limits-bar` |
| `context: —` | The agent does not report token counts. Today only Claude does. | Expected for other agents. |
| `limits: usagebar not found` | Usage plugin not installed | Install it, or set `USAGEBAR_BIN`. |
| `limits: no data` | No provider reports an active window | Run `usagebar collect --all` to check. |
| Claude numbers look old | Claude Code has not run recently | Use Claude Code once. |
| Bar is 4 rows tall | herdr's minimum height for a split pane | Not configurable. |

---

## 🗂️ How it works

```
herdr-plugin.toml      manifest: one event + one action
bin/open-bar.sh        opens the bar in a tab (event and action entry point)
bin/statusbar.py       draws the bar and refreshes it in place
config.example.toml    optional settings
assets/preview.svg     the picture above
```

1. herdr fires `pane.agent_detected` when an agent appears.
2. `open-bar.sh` splits that pane and runs `statusbar.py` in the new pane.
3. `statusbar.py` reads the tab's agents from `herdr agent list`, reads limits from the usage plugin, and redraws every 15 seconds.

Pace samples are kept for one hour in the plugin's state directory. The `⚠` warning needs about 5 minutes of samples before it can appear.

---

## 🚧 Known limits

- Context percentages are approximate until `context_window_tokens` matches your model.
- Only Claude reports context tokens to herdr today.
- Cursor, OpenCode and Grok limits are not shown yet (no usable data source).

---

## 🤝 Contributing

Issues and pull requests are welcome. Keep changes small and stdlib-only, so the plugin stays zero-dependency.

## 📄 License

[MIT](LICENSE) © Rustamchuk
