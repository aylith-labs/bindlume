# Omarchy Shortcuts

Persistent GTK4 shortcut browser for this machine. Launch **Omarchy Shortcuts** from the app launcher, or run `python app.py`.

- Search descriptions, key combinations and categories.
- Click a group heading to collapse or expand it.
- Click an action to execute it against the selected target window.
- Star favorites; the Favorites button filters to saved items.
- Refresh reloads installed bindings. The target window list refreshes automatically.

Favorites are stored in `~/.config/omarchy-shortcuts/favorites.json`.
The existing Super+K menu remains available.

Uses the functions from the installed `/usr/share/omarchy/bin/omarchy-menu-keybindings` script, without editing that script. If its interface changes, the adapter may need updating. Five custom Lua callbacks have no dispatch metadata in the installed menu and are shown disabled; mouse dragging must also use its actual shortcut.

Validation: Python compilation, live loading of 227 shortcuts, favorite save/reload/removal using temporary storage, one non-destructive live workspace dispatch, and visual inspection of the running window.

## Interface and saved state

**Expand All** and **Collapse All** affect every category, including filtered-out groups. Individual group toggles also persist across filtering and app restarts. State is stored in `~/.config/omarchy-shortcuts/ui-state.json` under `expanded_groups`; absent groups default to expanded.

The target defaults to **Current**, meaning the active workspace. App launches stay on that workspace; window actions choose the most recently focused other window on that workspace. Select a named window to pin that target. Search, the Favorites-only filter and the selected target are not saved.

**Info** explains architecture, shortcut discovery and execution, source/config/cache locations, favorites, group state, launch instructions and limitations. It calculates file and line counts from the project when opened (including comments/blank lines; excluding hidden files and Python caches). Buttons open the project and settings folders. The external desktop launcher is counted separately.

Run `python -m unittest -v` from this folder to check persistence, filtering, target selection and Info contents; it requires a GTK display. No extra dependencies are required beyond the installed Python / PyGObject / GTK4 and Omarchy.

## Search, hover, global activation and live keyboard

- Hover an action for its full description, category, dispatcher and arguments.
- `@w` matches the W key with any modifiers, not words containing W. `@ctrl+w` requires Ctrl but allows additional modifiers. Combine with text, e.g. `@w window`. `@enter`, `@esc`, and other aliases work.
- **Super+Shift+K** launches or focuses the app, returns to List, and focuses/selects the search input. It is defined in `~/.config/hypr/bindings.lua`. The original Super+K menu remains available.
- **List is the default view**. **Live Keyboard** is a separate tab. It renders a full-size ANSI keyboard with live XKB labels from the active Hyprland layout, including modifier layers and shortcut counts. Media/mouse/other keys appear below. The physical chassis is a full-size reference, not hardware detection of the laptop's exact key positions.
- Hold modifiers or click modifier buttons to inspect an exact layer. **All layers** shows all combinations. Clicking a key returns to the list filtered by that key and layer; editing search clears the layer restriction.
- Physical key presses/releases highlight while the Live Keyboard tab is open. Switching to List or closing disables capture. The bridge's ten-second lease expires if the app crashes. Numeric key events travel over Hyprland's local IPC socket; the app does not save key history or typed text.
- `input_bridge.lua` is loaded from the user's `bindings.lua`. To remove the integration, remove its `dofile(...)` and the Super+Shift+K binding, then reload Hyprland. Reloads clear bridge state; the running app renews its lease when appropriate.
- The palette follows `~/.local/state/omarchy/current/theme/colors.toml` within one second, with GTK fallback. The app does not alter the system theme.
- `shortcut_data.py` handles matching and hover details; `keyboard_view.py` implements XKB rendering and IPC input; `theme.py` follows colors. See `RESEARCH.md` for existing tools and primary sources consulted before implementation.

Validation now also covers base-key matching, modifier layers, alternate XKB layouts, full hover metadata, live-capture lease expiry and theme changes. View selection, selected keyboard layer, and transient key states are not saved.

End-to-end GUI validation also checks default List view, focused search on repeated activation, live IPC modifier and press/release updates, key-to-list navigation, and capture stopping when leaving the keyboard view.


## Rich Info and previews

Info is a modal with formatted, linked documentation and a separate preview pane. File links show source or formatted Markdown; folder links show clickable entries; image links show the image; web links load a readable preview asynchronously. Back/forward, Copy Link and Open Externally are available. Web previews omit scripts and interactive content, and reads are capped at 512 KiB. Other binary formats show metadata and an external-open option. Preview navigation stays in memory.

Hover tooltips now use aligned native GTK grids, with monospace dispatchers and arguments. The instructional hint line has been removed. Empty keyboard-filter notices stay hidden, and the default List view does not reserve the Keyboard page's height.


## Learned shortcuts

The ✓ toggle beside each bookmark marks a shortcut as learned. It is independent of Favorites and saves immediately to `~/.config/omarchy-shortcuts/learned.json` using the same stable shortcut IDs. Click again to unmark it.

Use the **All shortcuts / Learned / To learn** dropdown beside Favorites. It combines with search, favorites, and keyboard-selection filters. Learned marks survive restarts; the filter starts at All shortcuts. Info includes the storage location as a previewable link.

Learned state is visually explicit: **○** means not learned and **✓** means learned. Dropdown items share a consistent corner radius. Keyboard hover cards show descriptions/categories only; the action list retains full dispatcher and argument tooltips.

Info sizes itself in logical pixels to the parent window's monitor, accounting for display scaling and reserved panel space. It centers on that monitor after opening. Controls wrap and the two panes stack vertically on narrower displays; preview/document content remains scrollable. Verified at this display's 160% scaling: the 1060×601 dialog fits inside the 1200×649 usable area.

## Repository and setup

The first commit preserves the original 207-line `app.py` exactly as saved before the Info/state enhancements. The following commit contains the current application, tests, documentation and desktop launcher. These commits were created from saved versions when the project was first published; they do not pretend to be the original development timestamps.

This is a personal project for Omarchy's Lua-based Hyprland setup. It uses system-installed Python 3.11+, PyGObject, GTK4, Pycairo, libxkbcommon, Bash, Lua and the installed Omarchy menu adapter. Run `python app.py` inside the checkout.

For launcher integration, copy `omarchy-shortcuts.desktop` to `~/.local/share/applications/` and update its `Exec` path if the checkout is somewhere other than `/home/stevenp/Work/omarchy-shortcuts`. Add these entries to your personal `~/.config/hypr/bindings.lua`, adjusting the paths if needed:

```lua
o.bind("SUPER + SHIFT + K", "Omarchy Shortcuts", "python /home/stevenp/Work/omarchy-shortcuts/app.py")
dofile("/home/stevenp/Work/omarchy-shortcuts/input_bridge.lua")
```

Check for an existing binding before adding it, then run `hyprctl reload` and `hyprctl configerrors`. The current machine already has these entries. User favorites, learned marks, and expanded-group state remain outside the repository in `~/.config/omarchy-shortcuts/`.

Press **Escape** to close Info. A **Show in Folder** button appears for local-file previews and selects the file in Nautilus; its tooltip shows the containing directory. For a file that has not been created yet, it opens the existing parent folder instead.

Preview commands are grouped in the **Actions** menu. Local resources offer **Copy Path** (a pasteable filesystem path) and **Copy File URI** (a `file://` reference); web pages offer **Copy URL**. **Open Externally** and **Show in Folder** appear where applicable. Copy uses `wl-copy` with an explicit UTF-8 plain-text MIME type and survives closing Info. Omarchy clipboard history can recognize file URIs as file references; use Copy Path for ordinary text fields.
