# Bindlume testing preview

The first public alpha targets Omarchy's Lua-based Hyprland desktop. This release invites testing; it does not claim production stability or support for every Linux desktop.

## Verified locally on 22 September 2026

- Full suite: 207 Python tests discovered; 206 passed, one opt-in photo test skipped. Six QML checks passed.
- Focused regressions cover inline session rename, search clearing, physical keyboard row offsets, Shift-only Restart, scrolling, source-menu keyboard navigation, and preservation of saved data during the Bindlume identity migration.
- Live identity migration preserved 20 user files byte-for-byte and all five saved conversations. New launcher, control API, desktop binding, and restart were verified.
- Changed rename, search, keyboard, usage, and dialog surfaces were visually inspected on an isolated GTK display.

## Known limitations for testers

- Only the current Lua-based Omarchy setup has been exercised on a real desktop. Windows, macOS, and other Linux/compositor combinations are not supported alpha targets.
- The companion depends on the installed harness, its authentication, model availability, and provider limits. Each supported harness has adapter tests; not every live provider/account combination has been verified.
- Some translations are incomplete and fall back to English. Physical keyboard layouts, multiple monitors/mixed DPI, and controller models need wider testing. Controller axes are inspectable but do not have action mappings.
- GTK/Broadway tests cannot prove all Wayland focus and input behavior. Report compositor-specific problems with your versions and display scale.
- The optional global keyboard guide needs explicit input-access setup. Core search and browsing work without granting it.
- Direct API connections may incur provider charges and require their own credentials; a CLI subscription is not an API subscription.

## Repeatable checks

```sh
make test
BINDLUME_CHAOS_SEED=20260922 BINDLUME_CHAOS_STEPS=300 /usr/bin/python tests/run.py test_native_style.NativeWorkflows.test_seeded_interactions
NATIVE_PHOTOS=/tmp/bindlume-native /usr/bin/python tests/run.py test_native_style.NativeWorkflows.test_photos
```

The tests use private Broadway/offscreen displays and temporary user settings. Inspect generated screenshots; capture success alone is not visual approval. Test installation with `install.py install --home <temporary-directory> --no-reload`, then test update and uninstall against that same directory.

Please file reproducible bugs at https://github.com/aylith-labs/bindlume/issues/new/choose.
