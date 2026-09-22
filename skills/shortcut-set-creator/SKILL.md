---
name: shortcut-set-creator
description: Create or update data-only shortcut-set plugins for the standalone shortcut browser, including installed-app detection and stable shortcut identities. Use when adding an application's shortcuts or a personal reference set; not for changing desktop keybindings.
---

Create version-1 JSON shortcut sets for the shortcut browser. The installed format and validator are in `~/.local/share/bindlume/SHORTCUT_SETS.md` and `shortcut_sets.py`; read the format before editing. Use the current Bindlume checkout when developing from source.

Use the target application's official shortcut reference, matching OS and version. State whether the set contains defaults or a live keymap; don't present defaults as user-customized bindings. JSON plugins are references and must not contain executable actions. Implementing a new live reader is separate source-code work.

Put user sets in `$XDG_CONFIG_HOME/bindlume/shortcut-sets/`, defaulting to `~/.config/bindlume/shortcut-sets/`. Use unique stable set and shortcut IDs. Retain IDs and the set name when updating existing entries so bookmarks/hidden marks survive. Detect installed applications using executable basenames and/or desktop IDs. Omit detection only for intentional personal/reference sets.

Validate with `python ~/.local/share/bindlume/shortcut_sets.py FILE`. To import a new file from elsewhere, add `--install`; existing sets should be edited in place. Test parsing, detection with the application absent and present, and at least representative modifier combinations. An empty or invalid set must not appear in the source menu. Report the path and shortcut count, and instruct the user to open source menu → Choose shortcut sets → Refresh, or refresh through the app when accessible. Do not modify Hyprland bindings or install the target app as part of authoring a reference set.
