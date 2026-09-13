# Existing tools reviewed before implementing the keyboard view

Reviewed 13 September 2026 against these primary sources:

- [hyprKCS](https://github.com/kosa12/hyprKCS): Rust / GTK4 manager with an XKB-aware physical keyboard, selectable modifier layers, hover details and favorites. Its documented configuration parser targets `hyprland.conf`; this machine uses Lua. Used as a feature reference, not installed or copied.
- [Noctalia Keymap](https://noctalia.dev/plugins/community/keymap): supports the current Hyprland Lua registry, keyboard/list views and exact modifier layers. Requires Noctalia v5; this machine uses the Omarchy shell. Used as an interaction reference, not installed.
- [Omarchy Key Visualizer](https://github.com/felixzsh/omarchy-key-visualizer): demonstrates physical input through `input.keyboard.key`. A keystroke overlay rather than a full shortcut keyboard. Read its documentation/event usage; this app has its own leased IPC bridge without a persistent key history.
- [Hyprland Lua events](https://wiki.hypr.land/configuring/core/advanced-configuration/events/): documents XKB keycode, timestamp and press/release/repeat states.
- [Hyprland IPC](https://wiki.hypr.land/IPC/): event socket transport.
- [GTK modifier state](https://docs.gtk.org/gdk4/method.Device.get_modifier_state.html): GTK-focused modifier state. The app uses the compositor bridge for global physical presses, including keys consumed by global shortcuts.

The existing Omarchy adapter already handles this system's Lua bindings. Keeping it preserves the user's favorites, dispatch behavior and grouped browser while adding a separate native GTK keyboard view.
