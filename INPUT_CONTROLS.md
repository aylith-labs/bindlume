# Mouse gestures & controllers

Enable **Mouse gestures & controllers** in Features, then open its page from App settings. All assignments begin as No action. Right-button drag directions can focus search, clear search, toggle chat, or open the keyboard shortcut reference.

Connected Linux input interfaces are grouped by device name and vendor/product ID. Keyboard, mouse and joystick interfaces are shown together. The currently attached Azeron exposes all three, including `/dev/input/js0`. Its joystick node is readable by the current desktop user.

Select a controller, use the focused input tester to identify its button numbers, and assign actions. Enable controller actions separately. Actions only run while the main Bindlume window has focus, with no nested modal. The tester never dispatches actions. Initial joystick state is ignored, and descriptors close on focus loss, disable, disconnect, or shutdown. Presses use generic device button numbers, not assumed Xbox labels. Axis values can be inspected but are not mapped yet. Keyboard/mouse emulation continues through existing mappings. No firmware changes or desktop-wide remapping are performed.

Inspiration researched:
- [Omarchy mouse/keybind plugin](https://github.com/Davedes83/mouse-keybind-plugin): separate pointer settings and binding management.
- [Omarchy peripherals plugin](https://github.com/tpatzelt/omarchy-peripherals): device inventory spanning keyboards, mice and controllers via UPower.
- [Omarchy input manual](https://omarchy.org/manual/keyboard-mouse-trackpad/): compositor gestures are separate from app-local gestures.

# Usage panel

Omarchy's `omarchy-agent-usage-update` runs per-provider collectors and writes display records into `$XDG_STATE_HOME/omarchy/agents/usage`. The native panel reads limits, recentDays and modelUsage from those records. Bindlume reuses fresh account-limit records (five-minute freshness), falling back to its provider quota adapter when unavailable. Account limits are explicitly labeled; global Omarchy token totals are never imported into Bindlume charts.

Bindlume charts aggregate only its own saved conversations. New per-turn records include date, provider and reported model. Older records without metadata remain visible as undated/model-not-reported totals rather than being assigned invented dates or models. Input plus output counts include cached input once. Charts remain opt-in through AI companion settings. Deleted conversations no longer contribute to the saved-conversation charts.
