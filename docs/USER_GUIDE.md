# Bindlume

**illuminating your bindings**

Shortcut discovery and an optional agent companion, with optional mouse gestures and controller actions. Repository: https://github.com/aylith-labs/bindlume. See [release readiness](../RELEASE_READINESS.md) for verification and open release gates.

## Development build

Persistent GTK4 shortcut browser for this machine. Launch **Bindlume** from the app launcher, or run `python app.py`.

- Search descriptions, key combinations and categories.
- Click a group heading to collapse or expand it.
- Click an action to execute it against the selected target window.
- Bookmark shortcuts; the Bookmarks button filters to saved items.
- Refresh reloads installed bindings. The target window list refreshes automatically.

Bookmarks are stored in `~/.config/bindlume/favorites.json`.
The existing Super+K menu remains available.

Uses the functions from the installed `/usr/share/omarchy/bin/omarchy-menu-keybindings` script, without editing that script. If its interface changes, the adapter may need updating. Five custom Lua callbacks have no dispatch metadata in the installed menu and are shown disabled; mouse dragging must also use its actual shortcut.

Validation: Python compilation, live loading of 227 shortcuts, favorite save/reload/removal using temporary storage, one non-destructive live workspace dispatch, and visual inspection of the running window.

## Interface and saved state

**Expand All** and **Collapse All** affect every category, including filtered-out groups. Individual group toggles also persist across filtering and app restarts. While search contains non-whitespace text, matching groups auto-expand. Accordion toggles and Expand All / Collapse All during search are temporary; clearing search restores the saved group state. State is stored in `~/.config/bindlume/ui-state.json` under `expanded_groups`; absent groups default to expanded.

The target defaults to **Current**, meaning the active workspace. App launches stay on that workspace; window actions choose the most recently focused other window on that workspace. Select a named window to pin that target. Search text, the Bookmarks-only filter, learned-status filter and selected key/modifier filter are saved immediately in `ui-state.json` and restored on restart. The selected target window is not saved.

**Info** explains architecture, shortcut discovery and execution, source/config/cache locations, favorites, group state, launch instructions and limitations. It calculates file and line counts from the project when opened (including comments/blank lines; excluding hidden files and Python caches). Buttons open the project and settings folders. The external desktop launcher is counted separately.

Run `make test` from this folder. GTK tests use a private Broadway display, so no test windows appear on your desktop. Requires Python / PyGObject / GTK4 (including gtk4-broadwayd), Lua and Qt QML test tools.

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

Validation now also covers base-key matching, modifier layers, alternate XKB layouts, full hover metadata, live-capture lease expiry and theme changes. View selection and transient key states are not saved. The key/modifier filter applied to the list is saved.

End-to-end GUI validation also checks default List view, focused search on repeated activation, live IPC modifier and press/release updates, key-to-list navigation, and capture stopping when leaving the keyboard view.


## Rich Info and previews

Info is a modal with formatted, linked documentation and a separate preview pane. File links show source or formatted Markdown; folder links show clickable entries; image links show the image; web links load a readable preview asynchronously. Back/forward, Copy Link and Open Externally are available. Web previews omit scripts and interactive content, and reads are capped at 512 KiB. Other binary formats show metadata and an external-open option. Preview navigation stays in memory.

Hover tooltips now use aligned native GTK grids, with monospace dispatchers and arguments. The instructional hint line has been removed. Empty keyboard-filter notices stay hidden, and the default List view does not reserve the Keyboard page's height.


## Learned shortcuts

The ✓ toggle beside each bookmark marks a shortcut as learned. It is independent of Bookmarks and saves immediately to `~/.config/bindlume/learned.json` using the same stable shortcut IDs. Click again to unmark it.

Use the **Learned status** dropdown in Settings (F10), or open it directly with Alt+L. It combines with search, favorites, and keyboard-selection filters. Learned marks survive restarts; the filter is restored on restart (All shortcuts on first use). Info includes the storage location as a previewable link.

Learned state is visually explicit: **○** means not learned and **✓** means learned. Dropdown items share a consistent corner radius. Keyboard hover cards show descriptions/categories only; the action list retains full dispatcher and argument tooltips.

Info sizes itself in logical pixels to the parent window's monitor, accounting for display scaling and reserved panel space. It centers on that monitor after opening. Controls wrap and the two panes stack vertically on narrower displays; preview/document content remains scrollable. Verified at this display's 160% scaling: the 1060×601 dialog fits inside the 1200×649 usable area.

## Repository and setup

The first commit preserves the original 207-line `app.py` exactly as saved before the Info/state enhancements. The following commit contains the current application, tests, documentation and desktop launcher. These commits were created from saved versions when the project was first published; they do not pretend to be the original development timestamps.

This is a personal project for Omarchy's Lua-based Hyprland setup. It uses system-installed Python 3.11+, PyGObject, GTK4, Pycairo, libxkbcommon, Bash, Lua and the installed Omarchy menu adapter. Run `python app.py` inside the checkout.

Install for the current user (no sudo):

```sh
make install
```

This copies the app and documentation to `~/.local/share/bindlume/`, creates
one executable launcher at `~/.local/bin/bindlume`, and installs the desktop
entry. It backs up and updates the app's entries in `~/.config/hypr/bindings.lua`,
then reloads Hyprland and checks configuration errors. Super+Shift+K launches the
installed app; Super+K keeps its original behavior. The live keyboard bridge is
also copied into the installation. Existing unrelated bindings are preserved.

After installation you can move or delete the checkout. Launch from any directory
with `~/.local/bin/bindlume` or the desktop launcher. To update, run
`make install` from an updated checkout and restart the app. Reinstallation does
not duplicate the hotkey or change saved preferences.

To remove the installation, use `make uninstall`, or, after deleting the checkout:

```sh
/usr/bin/python ~/.local/share/bindlume/install.py uninstall
```

Uninstall removes the application, desktop launcher and managed Hyprland block.
Bookmarks, learned marks and expanded-group state remain in
`~/.config/bindlume/`. The app still requires the system dependencies
listed above. Run `make test` to execute application and isolated installer tests.

Press **Escape** to close Info. A **Show in Folder** button appears for local-file previews and selects the file in Nautilus; its tooltip shows the containing directory. For a file that has not been created yet, it opens the existing parent folder instead.

Preview commands are grouped in the **Actions** menu. Local resources offer **Copy Path** (a pasteable filesystem path) and **Copy File URI** (a `file://` reference); web pages offer **Copy URL**. **Open Externally** and **Show in Folder** appear where applicable. A dismissible six-second toast previews the copied text without moving the preview content. Copy uses `wl-copy` with an explicit UTF-8 plain-text MIME type and survives closing Info. Omarchy clipboard history can recognize file URIs as file references; use Copy Path for ordinary text fields.


## Keyboard Guide

The **Keyboard Guide** item in the cog menu (or `bindlume --guide`) opens
one GTK settings dialog shared with the main app. It controls the Super-key HUD,
position, scale, opacity, timing, density, independent icon choices, category
markers, saved indicators, and per-group/per-shortcut visibility. Save applies
changes; Escape or Cancel discards them. A preview updates before saving.
The shell's guide-settings entry opens this same dialog.
The guide runs in Omarchy's shell even when the browser is closed. New
installations start with the guide disabled; existing preferences are retained.

The guide is vendored in `keyguide/` from MIT-licensed Omarchy Keyguide; attribution
and the upstream revision are in `keyguide/UPSTREAM.md`. `make install` deploys it
with the app, and links the shell plugin to that installed copy. An existing
standalone plugin is backed up under
`~/.local/state/bindlume/keyguide-backups/`; no second guide runs.
Update this bundled version with `make install`, not `omarchy plugin update`.
Uninstall removes the managed link and retains preferences and the backup.

The overlay is intentionally click-through. Super+mouse is also used by Hyprland
for window actions, so guide controls live in the app and the guide's bar menu.
Guide preferences live in `~/.config/bindlume/keyboard-guide.json`; older settings are migrated once. Keyboard input access is required on a fresh machine: from the
checkout run `sudo bash keyguide/scripts/input-access.sh install`, then
`omarchy restart shell`. This grants input access to the active local seat using
the included udev rule. Existing input access is left unchanged. The guide also
requires Quickshell, a C compiler, Python and xkbcli, as supplied by Omarchy.

### Guide timing and global shortcuts

**Show delay** controls how long Super must be held before the overlay appears
(0–5000 ms). **Fade duration** controls the opacity transition (0–2000 ms).
Both controls use **100 ms steps**, in the native panel and full guide settings;
zero preserves instant behavior. Short presses cancel the pending guide.

**Show action badges/icons** controls ordinary-action indicators in both layouts,
including the preview and legend. Compact mode's preview uses the same category
icons and visibility rules as the live overlay.

**Super+Ctrl+Shift+K** toggles a persistent list of global bindings that do not
include Super, including Ctrl/Alt/Shift combinations. Press it again to close.
This explicit guide opens immediately, independent of the hold delay. The native
panel has a matching button. These are compositor bindings, not shortcuts inside
every individual application.

### App layout

Shortcut rows have comfortable spacing. A single toolbar contains search, Bookmarks and a menu. The menu contains
filters, List/Live Keyboard views, expand/collapse, target selection, Keyboard
Guide, refresh and Info. Each shortcut shows its key combination below its name. The palette follows Omarchy.

**Win+Shift+K** opens the shortcut browser as a centered floating window, sized to 80% of the monitor. The installer includes this rule in `windows.lua`.

### Shortcut types and icons

The list uses the guide's **Action**, **System UI**, **Desktop App**, **Web App**
and **Command** classifications. Choose a type in the toolbar menu; **Apps**
includes desktop and web apps. The filter is saved and combines with search,
Bookmarks and learned status. Existing shortcut IDs and saved marks are preserved.
Unmatched supplementary shortcuts appear under **Other** instead of guessing.

Desktop apps use their installed icons. Web apps use cached site favicons where
available, falling back to installed web-app icons or the generic web icon. The
app, guide and preview share the lookup. Favicons are fetched directly from the
configured websites without browser cookies or a third-party icon service; cache
files live in `~/.cache/bindlume/favicons/`. Failed lookups retry after a
day. The original topic names remain searchable.

The toolbar starts with Bookmarks, Expand All, Collapse All and the List/Keyboard toggle, followed by search and the menu. Expand/collapse controls appear only in List view.

The keyboard view hides the numpad by default. Use **Numpad** to show it and **Fit width** to scale the keyboard with the window; both preferences are saved. Keys show available desktop app icons and web favicons for the current modifier layer.

Escape closes the main window, Info, and Keyboard Guide settings. Full guide settings also support Escape (canceling an active shortcut edit first).

Startup stages are recorded in `~/.local/state/bindlume/startup.jsonl`, with a process ID and elapsed milliseconds from Python entry: imports, activation, widgets, targets, mapped, first GTK frame, records loaded, and shortcuts rendered. The log rotates at 1 MiB. First frame measures GTK painting, not the end of the compositor animation or time before Python starts. The app defaults to the OpenGL GTK renderer to avoid slow renderer initialization; an explicit GSK_RENDERER override is respected.

App shortcuts are available through the help button beside the menu, or **F1**. They apply while the main window is focused.

| Action | Shortcut |
| --- | --- |
| Show app shortcuts | F1 |
| Switch List / Keyboard | Ctrl+K |
| Toggle bookmarks filter | Ctrl+B |
| Focus search | Ctrl+F |
| Expand all groups (List) | Ctrl+E |
| Collapse all groups (List) | Shift+Ctrl+E |
| Refresh shortcuts | Ctrl+R |
| Open filters and settings menu | F10 |
| Open app commands | Shift+F10 |
| Cycle bookmarked sources | Alt+S |
| Open source picker | Alt+Shift+S |
| Open settings | Ctrl+, / Ctrl+Alt+S |
| Open Keyboard Guide settings | Ctrl+Shift+, |
| Open Info | Ctrl+I |
| Clear all filters | Shift+Ctrl+F |
| Choose shortcut type | Alt+T |
| Choose learned status | Alt+L |
| Choose target window | Alt+W |
| Toggle numpad (Keyboard) | Shift+Ctrl+N |
| Toggle fit width (Keyboard) | Shift+Ctrl+W |
| Toggle all modifier layers (Keyboard) | Shift+Ctrl+A |
| Close current window | Esc |
| Navigate / activate controls | Tab / Shift+Tab, Space / Enter |

Keyboard and List views share search, favorites, learned-status, and shortcut-type filters. Keyboard always shows the filter bar; **Show filters** (available in List view) in the menu enables it there too. Apps (desktop + web) appears immediately above Desktop App.

The keyboard's extra-keys section supports **List** (the same interactive rows as the main list) and **Columns** (spaced cards with informational favorite/learned indicators on the right). Its badge counts matching shortcut bindings, including the current modifier layer. All layers keeps all modifier combinations visible, even while modifiers are held; key symbols and the legend identify Super, Ctrl, Shift, Alt, and no modifier.

The active view, optional List filter bar, keyboard layout mode, extra-keys expansion, modifier selection, numpad, fit width, and target window selection are saved alongside existing search/filter and category preferences. A target window can only be restored while that window still exists.

All layers is a separate switch. Modifier buttons form an additive group: with All layers on, selected or held modifiers match every combination containing them; with it off, they match the exact combination. Clicking a key preserves this inclusive/exact distinction in List view.

The source selector offers Omarchy, Tmux, Herdr, and Shefrd. The selected source refreshes every five seconds while the window is focused, or immediately with Ctrl+R. Source selection is saved. Bookmarks and learned markers have source-specific IDs.

Tmux reads the current socket's live key tables and prefix when available, otherwise Omarchy's configuration resolver. Herdr tries the live resolved-keymap API, falling back to the installed Omarchy helper (installed-version defaults plus current config). Shefrd uses `shefrd keys list --json`; it needs an installed executable and running server. SHEFRD_BIN can specify an executable outside PATH. The footer explicitly distinguishes live data, configuration, and unavailable sources. Config-derived data cannot establish whether a running app has reloaded it.

Application shortcuts are reference entries, with prefix/mode context preserved; the browser does not dispatch them into terminals. They support search, favorites, learned markers, and keyboard visualization.

Win+Shift+K opens Bindlume by default; Settings allows another chord. Window animations are off by default; in-app animations independently follow the system. Settings offers explicit overrides. The F10 **Omarchy-style list** switch displays aligned shortcut → description rows. Up/Down navigates list results from search; Enter runs the focused actionable result. Alt+S cycles shortcut sources.

Architecture direction: retain the standalone GTK application and resident startup path. Omarchy is an optional desktop integration, not the UI host. Other desktop integrations should use independent adapters; current Hyprland/Omarchy-specific functionality is not yet portable to every desktop.

List appearance has two independent switches in F10: **Flat list** removes category headers and hides Expand/Collapse All; **Columns** puts the shortcut, arrow, and description on one row. Existing Omarchy-style preferences migrate to both switches enabled. Columns use larger 14px shortcut text and a width measured from the longest shortcut in the complete source, unaffected by filtering or scroll position.

The main list uses Gtk.ListView virtualization for both grouped and flat modes. Category rows and expanded child rows share one scroll model, and unchanged rows survive incremental updates.

UI regression scenarios and manual integration checks are documented in [UI_SCENARIOS.md](UI_SCENARIOS.md). Run `make test` for the Python and QML suites. Mapped GTK workflow tests use isolated preferences and mock external desktop actions.

Keyboard-specific Numpad and Fit width switches are in Settings (F10); Flat list and Columns appear there only in List view. Key overlays default off for new preferences. The animation preference applies to all native app windows on Hyprland.


Shortcut editing is available through **App settings → Manage shortcuts** or `bindlume --manage`. The native editor loads the current Hyprland configuration, offers modifier keycaps and key/action pickers, and uses the bundled backend's transactional assignment and removal checks. Existing occupied bindings require explicit replacement/removal confirmation. Returning to the shortcut browser restores the previous view.

**Keyboard Guide** opens the app’s shared GTK settings surface. Presentation preferences, preview, per-group and per-shortcut visibility live there. App and HUD use the same selected style and palette. Visible Keyboard view suppresses the guide, including while a menu has focus, using a renewable lease that expires after the app exits unexpectedly.


Additional app shortcuts:

| Action | Shortcut |
| --- | --- |
| Manage shortcuts (App settings) | Ctrl+M |
| Apply shortcut (editor) | Ctrl+Enter |
| Return from editor / previous Info preview | Alt+Left |
| Next Info preview | Alt+Right |
| Show filters (List) | Alt+F |
| Flat list (List) | Alt+G |
| Columns (List) | Alt+C |
| Key overlay (Keyboard) | Ctrl+Shift+O |
| Bookmark selected shortcut (List) | Ctrl+Shift+B |
| Mark selected shortcut learned (List) | Ctrl+Shift+L |
| Quit app and resident process | Ctrl+Q |

Shortcut audit: modifier buttons, source bookmark stars, editor group/key/action pickers, animation preference and guide settings retain standard Tab/Shift+Tab, arrows, Space/Enter navigation. Destructive editor removal requires selecting the confirmation control and activating Remove; no one-key removal shortcut is assigned. Ctrl+R refreshes the editor while it is open. Ctrl+F focuses its action picker. F1 lists main-window accelerators; Info navigation shortcuts appear on its buttons.


Visibility replaces the former learned status: **Show all / Hidden / Not hidden** retains existing marks and filter choices. The legacy `learned.json` filename remains for compatibility. Bookmark and eye controls sit on the right; marked states stay visible, while unset states appear on hover or keyboard focus. Hiding here filters the shortcut browser; it does not disable a system keybinding or change the guide's separate HUD visibility settings.

Extra keyboard shortcuts offer **List** (description over shortcut), **Columns** (shortcut → description), and **Grid** (multiple cards). Previous multi-column card preferences migrate to Grid. Grid state icons remain informational and follow the same hover/marked visibility rule.

## Live list input

Enable **Live filter** in the List filter bar (Alt+V). Held modifiers and keys
filter the current source alongside the existing filters; releasing them clears
only the live filter. All layers includes additional modifiers. Escape leaves Live
view, restoring normal search and app shortcuts. The switch is remembered.
The guide stays suppressed while this view is visible. GTK requests system
shortcut inhibition while the window is focused; on Hyprland this also permits
modifier-held clicking and scrolling without moving the window or changing groups.
The request is released when leaving Live filter, hiding the app, or losing focus.
Other desktops decide whether to grant GTK's standard inhibition request.

Bookmark/visibility updates preserve row controls and scroll position. Settings
switch labels and controls share a highlighted click target. F10 toggles Settings;
Escape and closing Settings also dismiss its nested choice menu.

## A simple first launch, optional features

New profiles start with a flat, two-column list. The **Features** button
(Ctrl+Shift+P) opens an inert preview gallery for Bookmarks, Hide shortcuts,
Keyboard explorer, Shortcut editor, Keyboard guide, target-window selection,
Filters and layouts, Live filter, and Recent searches. Existing profiles retain
their capabilities. Disabling bookmarks or hidden marks removes their controls,
shortcuts and filters but keeps their stored data. Re-enabling restores access.

**View options** (F10) contains only options for the active view. **App settings**
(the rightmost cog, Shift+F10) contains Settings, optional target selection,
Keyboard shortcuts (F1), enabled tools, refresh, About, Quit, and Reset to Defaults.

Recent searches are stored locally, capped at 20, deduplicated and suggested
while typing. A search is remembered after a 1.2-second pause or when an action
is launched. Down selects a suggestion; Enter or a click applies it, and Escape
dismisses suggestions. Disable Recent searches to stop collecting/suggesting
without deleting the existing history.

Reset to Defaults first shows bookmarks, hidden marks, source bookmarks, recent
searches, features, active filters and display preferences that will be cleared
or restored. Cancel changes nothing. Confirm clears that app data and disables
the guide, while retaining desktop bindings and guide appearance settings.

Reset review uses category switches with counts and a scrollable side preview
shown on hover or keyboard focus. Empty categories are omitted. Clear all selects
or deselects every available category; Reset selected is disabled when none are
selected. Bookmarks, hidden marks, source bookmarks, searches, features, filters,
keyboard display and view preferences can be reset separately. No data is changed
until Reset selected is pressed.

### Shortcut sets and plugins

The source menu shows only enabled, installed applications with usable shortcuts. **Choose shortcut sets…** at the bottom opens the catalog. The catalog includes 30 default reference shortcuts each for Google Chrome and Chromium, detected through executable names or desktop launchers. Unavailable and empty sets stay out of the source menu; the catalog explains their status.

Use **Import set…**, **Create a set…**, or the folder button to manage data-only JSON plugins. No executable plugin code is loaded. Selection is saved separately from source bookmarks, and disabling a set keeps all marks. See [the plugin format and validation commands](../SHORTCUT_SETS.md). Agent authoring instructions are in [shortcut-set-creator](skills/shortcut-set-creator/SKILL.md).


### App settings and appearance

Open **Settings…** from the cog menu, or press **Ctrl+,** / **Ctrl+Alt+S**.
Language is shared by the browser and guide. The initial global shortcut is
**Super+Shift+K**; use the shared modifier/key picker or Capture shortcut in Settings, then click Apply.
Choosing Super+K replaces Omarchy's stock binding. The installer preserves your
chosen chord. Activating an existing window brings it to the current workspace.

Settings also controls system/light/dark colors, animations, separate application
and action icons, compact spacing, and label font/size. The Omarchy typography
preset selects monospace text and hides icons. Features is the first cog-menu
button, with **Ctrl+.** and **Ctrl+Shift+P** aliases. Its preview, description,
and grid preferences persist.

**Settings → Style** is always available. System detects Omarchy automatically;
its resolved style appears in parentheses, as do the system theme and animation mode.
Omarchy, Rounded, Square, and Neo-brutalism are available as explicit overrides.
Look definitions are in **looks.json**; GTK and the HUD consume the same tokens.
The main and guide settings use the same GTK components in `settings_ui.py`. Add a named
entry to extend the picker. Translation source text is in **translations.json**;
the guide's AppTranslations.js mirrors that catalog.

Guide settings (**Ctrl+Shift+,**) independently control density, category badges /
icons / no markers, app icons, and action icons. Saved bookmark/hidden indicators
are opt-in. Hidden browser shortcuts are excluded unless “Show hidden shortcuts”
is on; that switch is available only when the guide has hidden bindings.

All active preferences are under **~/.config/bindlume/**. The guide uses
**keyboard-guide.json**; its previous data-directory settings are copied once and
retained as a backup. The reset review lists filenames and symbolic-link targets.
Resetting app preferences leaves the global desktop binding unchanged.

“How to create shortcut sets” opens a Markdown guide inside the app. Copy content
and Copy path are separate actions. Copy for agents offers instructions with
just the local guide path, or instructions with the complete guide included.

Window animations default to **Disabled**. In-app animations separately default to **Follow system**. The preference is stored in
`ui-state.json` (`preferences.window_animations`: `system`, `on`, or `off`).
The obsolete `animate-window` marker is removed automatically. An explicit old
animation opt-out is preserved; resetting View and app restores Follow system.
Reset category switches and Clear all are positioned before their labels.

### Agents and conversations

Enable **Agent chat** in Features. **Ctrl+J** opens the full-height right sidebar
and focuses its composer; **Ctrl+Shift+H** opens searchable conversation history.
Enter sends; Shift+Enter adds a line. The close button or Escape collapses the
panel. Without an active chat it shows recent conversations, or suggestions if
there is no history. History shows titles; hover a title for metadata and use the
pencil to rename it. Copy exports the transcript, app session ID or file path,
and offers the provider's own session ID and resume command when available.

The app detects installed Codex, Claude, Gemini and OpenCode CLIs. Choose an agent
before the first message. Automatic compares provider-reported remaining usage
across available 5-hour and weekly windows; the provider with the most headroom
in its tightest window wins. Unknown quota is not treated as a full allowance.
Usage is cached for five minutes and can be refreshed from the Usage menu.
Automatic checks again before each turn; when providers change, the saved transcript
is carried forward. Each uses its
existing sign-in and configured model. No request is sent until Send is pressed.
Stop terminates the running response. Authentication and permission errors appear
in the conversation; the app never enables unrestricted agent execution.

Conversations are stored under `~/.config/bindlume/chats/<UUID>/`, with
`session.json`, a portable `transcript.md`, and provider-local runtime files.
Created/updated timestamps, status, message count, provider ID and available token
usage are retained. Disabling the feature or resetting settings retains chats.
The provider may also retain its native session in its own data directory.

**Any agent session** can control the app through `bindlume ctl`:

```sh
bindlume ctl schema
bindlume ctl search 'screenshot'
bindlume ctl bookmark EXACT_ID on
bindlume ctl hide EXACT_ID on
bindlume ctl features all off
bindlume ctl settings app_icons false
bindlume ctl reset                     # preview only
bindlume ctl reset --apply              # apply every preview category
```

Commands return JSON and update the running app through a local D-Bus interface;
they start the background app when needed. They do not edit state behind the UI.
The installer makes the bundled **bindlume** skill discoverable in shared,
Codex, Claude, Gemini and OpenCode skill directories, preserving independent user
skills. `bindlume ctl mcp` exposes the same validated operations over
stdio MCP. The sidebar supplies this tool automatically to its chosen agent.

Provider integration references: [Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode),
[Claude programmatic usage](https://code.claude.com/docs/en/headless),
[Gemini MCP configuration](https://geminicli.com/docs/tools/mcp-server/), and
[OpenCode MCP configuration](https://opencode.ai/docs/mcp-servers/).

Chat toggles with **Ctrl+J** or its toolbar button, grows the window by the panel
width, and restores it on close. Enter sends or queues a message while busy; the
queue is saved with the conversation and can be edited by removing entries. Stop
keeps queued messages for an explicit restart. An animated spinner reports activity.
Copy is hidden before a conversation exists, and title tooltips appear only for
truncated titles. Codex grants approval only to the app's own control tool; its
filesystem sandbox stays read-only. The bridge explicitly receives the desktop
session's D-Bus address.

Every GTK dialog inherits Escape handling and focus restoration from `dialogs.py`.
Closing a dialog preserves the parent's focused control; search is the fallback.
Dynamically mapped controls and changing dropdown labels share the translation
pass. Shortcut titles, paths, and conversation text remain user/provider content.

Photo review can be reproduced without opening desktop windows:
`VISUAL_REVIEW_DIR=/tmp/shortcut-photos VISUAL_STYLES=system,rounded,omarchy,square,neo-brutalism python tests/run.py tests.visual_review.Capture`.
The helper renders the actual GTK widgets to PNG on a private display.

## Companion and guide preferences

The chat header's settings button opens **AI companion settings**. Keyboard illustrations, persistent user memory, custom instructions, and session token counts have separate opt-in switches. Markdown replies support headings, emphasis, links, lists, fenced code with copying, and scrollable tables. A `keyboard` fenced block containing `{"keys":["SUPER","Y"],"label":"Example"}` renders an illustration when enabled. The vignette preference applies to all illustrated replies and can be changed by asking the companion.

Explicitly requested memories are stored as bullets in `~/.config/bindlume/user-memory.md`. The companion API supports reading, remembering, forgetting, and setting the vignette preference; disabled memory is neither supplied to the agent nor changed by its tool. Custom instructions are included only while enabled. Settings show installed harness paths and models; the chat distinguishes a configured model from a model reported by the provider. Token totals accumulate reported input/output usage over turns and exclude cached-token subtotals to avoid counting them twice. Unreported usage is shown as unavailable.

Guide settings can place their live preview on the right, expanding within the current monitor's available width. The footer's Auto-save switch persists independently of guide settings. When enabled, changes save after a short debounce, Save is disabled, and Cancel becomes Close. Closing waits for pending saves; failures leave the dialog available for retry.

**About** is now a concise version/build/language/runtime summary. **Inside the app** opens the separate architecture and resource browser.

## Native presentation defaults

Fresh installs enable agent chat, use system typography, and leave app/action icons off. Omarchy maps to the Square style, using the installed menu font and spacing tokens, plain search input, scroll-edge fades and an exclusive layer-shell overlay with a dimmed backdrop. The `gtk4-layer-shell` runtime is needed for this Wayland behavior; unsupported compositors use regular GTK windows. Existing explicit preferences are preserved.

Window animations default to off. In-app animations are independently configurable and follow GTK by default. The old `omarchy` style identifier migrates to `square`; application, launcher, agent skill, and config identifiers now use Bindlume. The installer automatically migrates existing user data; conflicting destination files stop migration without overwriting them.

### Fast companion connections and interaction checks

See [FAST_CHAT.md](FAST_CHAT.md) for direct Gemini API, OpenRouter, Ollama and compatible endpoint setup, research, limits, and evaluation guidance. API connections are explicit opt-ins in AI companion settings; keys are referenced by environment-variable name.

Shortcut capture temporarily requests compositor shortcut inhibition. Its button changes to “Press shortcut…” and focuses the capture control. Escape cancels without closing Settings; completing a chord, leaving the window, or closing the picker releases capture. Use the modifier/key dropdowns if the compositor declines the request. Tests on the private Broadway display cover the controller and inhibition lifecycle; they cannot verify a compositor’s decision.

Startup uses a private display cache while refreshing live bindings. Loading is distinct from no matches. Keyboard navigation retains its selection when the pointer moves over rows. Empty chat messages cannot be sent or queued.

### Raised keyboard view

Switch to the keyboard view, open its display options, and enable **Raised keys** for tilted, rounded keycaps with depth and accent illumination. Selected modifiers and physically held keys light up; matching bindings have an accent glow. Disable it to return to the flat map. This preference is saved and follows the current color palette.
