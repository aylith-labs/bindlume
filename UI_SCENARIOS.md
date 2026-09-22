# UI regression scenarios

Run `make test`. Python tests run on a private GTK Broadway display with a 90-second timeout; they never open test windows on the desktop. GTK4's `gtk4-broadwayd` is required. QML tests use Qt's offscreen backend. For a focused run: `python tests/run.py test_ui_workflows`.

The mapped-window tests isolate preferences and replace desktop discovery/dispatch. They exercise GTK widgets and application event handlers, including focus and popup mapping. They are not physical-input or compositor tests.

## Automated coverage

| Scenario | Expected outcome | Coverage |
| --- | --- | --- |
| Open F10, then Escape | Settings opens; Escape dismisses it without hiding the app | UI workflows |
| Shift+F10 | App commands opens directly | UI workflows |
| Change List to Keyboard and back | Show filters switch appears only in List | UI workflows |
| Hover settings switches | Every switch has explanatory help | UI workflows |
| Ctrl+B twice, reload preferences | Bookmarks filter toggles and persists | UI workflows |
| Alt+L while Settings is closed | Direct overlay opens, current item focused | UI workflows |
| Alt+T with List filters hidden or Keyboard active | Type picker opens without changing view | UI workflows |
| Open source picker using keyboard activation | Current row receives focus | UI workflows |
| Up/Down, Enter in picker | Selection changes and commits | UI workflows |
| Move selection then Escape | Original selection remains | UI workflows |
| Repeatedly open/dismiss all menus | App remains mapped in the same view | UI workflows |
| Alt+S with multiple/no bookmarked sources | Cycles only bookmarks; empty set does not change source | UI workflows |
| Flat list on/off | Expand/collapse controls hidden/restored | UI workflows |
| Columns plus search and window resize | Shortcut column width stays stable | UI workflows; app tests |
| 5,000 shortcut records | Model contains all records; fewer than 500 row widgets constructed | UI workflows |
| Source count update after garbage collection | Visible badges update correctly | UI workflows |
| Search, bookmarks, learned status, type combinations | Intersection is correct; preferences survive reload | App tests |
| Collapse groups, search, clear search | Expansion state preserved | App tests |
| Window target changes between selection and execution | Current target resolved at execution | App tests |
| Physical mapping and modifier combinations | Correct key/layer matching | Keyboard tests |
| Desktop IPC is slow | Lease work runs outside GTK main thread | Keyboard tests |
| Guide delay/compact preview/settings | Values and visibility agree | Guide and QML tests |
| Tmux prefix, app sources, disabled entries | Correct source records and context | Binding source tests |
| Install twice/uninstall in a temporary home | Idempotent integration and preserved unrelated config | Installer tests |
| Tooltip content and Info history | Correct labels, escaping, and navigation state | Info tests |

## Manual integration matrix

These checks remain necessary; a passing unit suite does not establish compositor behavior or visual quality.

- Open/close the resident app 20 times, alternating List and Keyboard. Check first-frame timings, right-edge movement, focus, and responsiveness. Repeat cold start separately.
- Try small windows, large fonts, 100%/150%/200% scale, both light and dark themes. Check no clipped focus rings, menu entries, column text, or inaccessible commands.
- Click each dropdown, then use arrows, Enter, Escape, Tab and Shift+Tab. Current selection must start focused. Bookmark a source without selecting it. Click outside to dismiss.
- Open Alt+L/Alt+T/Alt+W from both views, with Settings open and closed. Ensure there is one overlay and no accidental shortcut dispatch.
- Combine search, bookmarks, learned status, source and type; include empty results. Clear filters and confirm recovery. Close/reopen to verify persistence.
- Switch All layers on/off; combine Super/Ctrl/Shift/Alt. Compare List and Keyboard results. Release physical modifiers and verify no stuck states.
- Turn Key overlay off/on: modifier legend follows it, app icons remain. Numpad and Fit width remain Keyboard-only.
- Scroll 5,000 records, change source while loading, and repeatedly toggle grouping/columns. Watch latency, row state reuse, scroll stability and memory.
- With Keyboard focused, hold Super: the external guide stays hidden. Change view/focus or close the app: guide returns.
- Stop/restart Tmux or another source server. Refresh and verify unavailable states, totals and recovery; no UI freeze.
- Close the selected target window before activating an action. Confirm safe fallback/error and no action on an unrelated workspace.
- Choose Follow system, Enabled, and Disabled for Window animations in Settings, then compare open/close behavior. On another desktop the explanation must accurately describe compositor control.
- Quit Bindlume through App commands: resident process exits. Reopen via launcher; normal close hides it. Verify autostart after login.
- Test on another distribution/desktop before claiming portability. Omarchy, Hyprland and source-command availability are integration dependencies.

## Limits

No automated screenshot comparisons, accessibility audit, physical Wayland input, compositor timing guarantee, or multi-distribution validation is currently provided. Broadway verifies mapped GTK behavior, not how the compositor draws the final desktop window. The large-list assertion verifies bounded widget creation, not a fixed frame-rate guarantee.

### Live filter and settings regression verification

- Enable Live filter with Alt+V or the full switch row; hold/release modifiers and base keys. Search text stays unchanged, the current source/type/visibility filters remain combined, and All layers includes extra modifiers.
- Escape exits Live filter. Leaving List, hiding the app, or losing focus releases GTK system-shortcut inhibition. Guide suppression lasts while Live filter is visible.
- Actual Wayland verification: inhibition granted; Super+Ctrl+T returned two matching shortcuts; Super+Ctrl alone returned 56. With those modifiers held, injected pointer scrolling moved the adjustment from 0 to 360, and a real pointer click reached the row action handler (dispatch mocked). Shell state reported `keyboardViewActive=true`, `visible=false`. Inhibition was false after disabling the switch.
- Keyboard events use the current GDK keymap rather than physical XKB codes, so remapped virtual keyboards and shifted symbols work.
- Hover over a settings label, not just the switch: highlight and help appear. Visually verified the Columns tooltip with real Wayland pointer motion.
- F10 opens and closes Settings; closing its parent dismisses an anchored choice. Alt+L from Settings keeps its independent choice overlay open.
- Bookmark/hide a scrolled row with Show all: no model rebuild; controls and scroll position remain. With visibility filtering active, removing a row preserves the scroll offset (clamped at the end).
- GTK workflows use fresh application instances and bounded waits for allocation on the private Broadway display.

### Features, search history, menus and reset

- Fresh profile: flat columns; no bookmark button, keyboard toggle, optional filters or view-options button. Recent searches is enabled; other optional tools start off. Existing profiles migrate with their capabilities available.
- Turn off Bookmarks / Hide shortcuts while their filters are active: both filters reset, all matching rows return, row/source controls and corresponding app shortcuts disappear, and saved marks remain intact. Re-enable and verify the marks are unchanged.
- Feature gallery: sample rows and miniature keyboard use production components. Preview controls cannot focus or invoke actions. Cards wrap into two columns at desktop width.
- F10 opens View options; Shift+F10 opens the separate App settings menu. Target selection opens nested under App settings when clicked, or directly at the rightmost cog from Alt+W even when View options is hidden. Closing its parent closes a nested choice.
- Type a query, pause, then type a matching prefix: recent queries appear. Down focuses a suggestion; Enter/click fills search; Escape dismisses. Deduplication ignores case and history is capped at 20. Disabling Recent searches stops new collection without clearing prior history.
- Reset review lists retained bookmarks and hidden marks by name where available, source bookmarks, search history, feature changes and current filter/display preferences. Cancel changes nothing; confirm clears reviewed app data. Desktop bindings remain intact.
- Source menu: compact equal-height rows, centered count badges and aligned bookmark/check columns. Multiline action tooltips keep accelerator keycaps vertically centered.
- Visually inspected real Wayland screenshots of the gallery, both menu styles, compact source menu and the clean default profile.

- With optional features disabled, F1 shows no empty sections or shortcut-editor navigation; Focus search follows Show app shortcuts. GTK Inspector bindings remain documented under Developer tools.
- Source picker omits known zero-count sources, retains unknown counts, focuses the current visible source, and navigates only visible entries.
- Features gallery switches between a two-column grid and a single list without changing feature states.
- Reset review exposes configuration file locations without selecting or deleting additional data.
- Repeated default-profile `f / fi / fil / fi / f / empty` searches reuse rows; dispatch still targets the selected result after filtering.

- Window animations is an app preference, defaults to Follow system, and lives only in ui-state.json. Reset View and app restores Follow system; no marker file remains.

- Uninstall or make a source unavailable: it disappears from the source popup; the active source falls back to another usable enabled set. If none remain, the empty popup still offers Choose shortcut sets and keyboard activation works.
- Toggle an available set off/on: persist selection and retain all source/shortcut bookmarks and hidden marks. Uninstalled or zero-count sources are disabled in the catalog.
- Import valid JSON, reject duplicate/empty/invalid/executable plugins, create two templates without overwriting either, edit a label/key while preserving IDs, refresh and verify saved marks persist.
- Detect browsers both through PATH and desktop launchers; Chrome and Chromium each supply 30 reference shortcuts without executing actions.

- On Wayland, open View options, click Visibility, choose another value, then click outside or the toolbar button: the parent menu closes. Repeat each value with actual pointer input; signal-only tests cannot detect lost compositor popup grabs. Nested popup closure must restore the outer popup grab.
- With optional features off (history and animation do not require extra width), the main window uses 800 logical pixels; enabling a feature returns to 1000. Hyprland must not override GTK's requested width.

## Settings consolidation and current-workspace activation

- Invoke the app from a different workspace: capture the caller's workspace
  before GTK presents the existing window. Use Lua dispatchers on current
  Hyprland, with legacy dispatcher fallback. Verify the app moves and focuses
  without moving the user to its former workspace.
- Ctrl+, and Ctrl+Alt+S open the same Settings window. Ctrl+Shift+, opens guide
  settings when enabled; Ctrl+. and Ctrl+Shift+P open Features.
- Removing the final mark clears the corresponding active filter, removes the
  button/setting, and keeps all rows available. Empty View options disappears.
- Feature tooltips contain only hidden descriptions/previews. Both visible
  means no tooltip. Compact switch rows put the control before its label.
- Toggle each guide display option independently. Compact density must not
  change the category marker choice. “Show hidden shortcuts” is available only
  with hidden guide bindings. Saved indicators are off by default.
- Preferences use one config directory, with one-time non-destructive guide
  migration. Reset review shows that directory once, file-type icons and any
  symlink targets. Global keybinding changes are not part of preference reset.
- Switch language and switch back; existing controls must return to their
  original text. User-provided shortcut/source names stay intact.

- Open shortcut-set authoring help inside the chooser. Check rendered headings, code and links; Copy content/path and both agent-instruction variants copy the expected text. Escape closes only the help overlay.
- Capture a global shortcut through the same modifier/key picker as the editor. Modifier-only input keeps capture active; Escape cancels capture without applying a binding.
- Disable both icon settings after searching/backspacing has populated the row cache. Existing and revisited rows must have no icon columns. Re-enabling action icons restores aligned columns.

- Agent chat starts disabled for existing and new profiles. Enabling it exposes Ctrl+J and Ctrl+Shift+H in F1. Opening chat focuses the bottom composer; hiding it retains the conversation.
- With no chats, suggestion buttons fill the composer without sending. With history, the empty chat view offers recent titles. Search history, press Enter to open its first match, rename a chat, hover metadata, and copy each export format.
- Use a fake installed provider to test JSON event parsing, streaming, cancellation and authentication errors without making paid model requests. Confirm transcripts and native IDs survive restart. Never bypass provider permissions to make a test pass.
- Test ctl search/bookmark/hide, all-features on/off, settings validation and reset preview/apply against isolated app state. Confirm live UI updates and no mark deletion from disabling a feature.
- Opening Features, shortcut-set selection, history, and rename dialogs focuses their primary text input.
