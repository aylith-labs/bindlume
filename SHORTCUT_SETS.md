# Shortcut-set plugins

Open the source menu → **Choose shortcut sets…**. Only enabled sets for installed apps with a positive shortcut count appear in the source menu. The chooser lists unavailable integrations with their status. Detection refreshes every 30 seconds, or immediately with **Refresh**. Disabling a set preserves bookmarks and hidden marks.

**Import set…** validates and copies a JSON file. **Create a set…** creates a working sample and opens it in your default editor. Edit it, save, and press Refresh. **Open shortcut-set folder** opens the files for editing or removal. Invalid sets are skipped and their errors appear in the chooser.

User sets live in `$XDG_CONFIG_HOME/bindlume/shortcut-sets/` (normally `~/.config/bindlume/shortcut-sets/`). Bundled browser sets live in the installed application's `bundled-shortcut-sets/`. Application updates do not replace user sets. No Python imports or shell commands are allowed in JSON plugins.

## Format, version 1

```json
{
  "version": 1,
  "id": "example-editor",
  "name": "Example Editor",
  "description": "Default Linux shortcuts for Example Editor 1.x.",
  "platforms": ["linux"],
  "detect": {
    "executables": ["example-editor"],
    "desktop_ids": ["org.example.Editor.desktop"]
  },
  "documentation": "https://example.org/editor/shortcuts",
  "shortcuts": [
    {"id": "find", "keys": "CTRL + F", "title": "Find", "category": "Navigation"},
    {"id": "command-palette", "keys": "CTRL SHIFT + P", "title": "Command palette", "category": "Navigation"}
  ]
}
```

- `id` is a stable, unique lowercase identifier. Keep shortcut IDs stable when editing labels or key combinations so saved marks survive.
- `name` is unique and must not use a live integration's name. Imported duplicates are rejected; edit the existing file to update it.
- `description` is required. `documentation` is optional; record the authoritative source/version there.
- `platforms` defaults to `["linux"]`; accepted values are `linux`, `win32`, `darwin`. This describes the set, not a promise that the entire app is portable.
- `detect` is optional. Any matching executable in PATH or desktop file in XDG application directories makes the app available. Use executable basenames and desktop IDs, not shell commands or file paths. Empty detection means a personal/reference set, always available on its supported platforms.
- `shortcuts` contains 1–10,000 entries. Each needs `id`, `keys`, `title`; `category` is optional. Keys use uppercase names and modifiers: `CTRL SHIFT + T`, `ALT + LEFT`, `F12`, `SPACE`. A set describes one keystroke per entry; for prefix modes, identify the mode/prefix in the category.
- Plugins are references: their rows cannot execute commands or send keys. Built-in live integrations retain their existing dispatch capabilities. JSON files are capped at 2 MB.

Validate without changing anything:

```sh
python ~/.local/share/bindlume/shortcut_sets.py my-set.json
```

Import from the command line by adding `--install`, then Refresh in the chooser. Test missing/present executables, duplicate IDs, empty sets, and a bookmark surviving a label edit.

Chrome and Chromium ship with 30 default Windows/Linux shortcuts based on [Google's shortcut reference](https://support.google.com/chrome/answer/157179?hl=en). These are reference bindings, not a live read of browser extensions or user overrides. Live Omarchy, Tmux, Herdr and Shefrd readers remain in `binding_sources.py`; Omarchy's adapter is isolated in `app.py`.

## Set categories

Set metadata includes a top-level `category`: `browsers`, `desktop`, `terminals`, `development`, or `personal`. For example, Chrome and Chromium use `"category": "browsers"`. Bindlume translates the group label for the active UI language. This is independent of the per-shortcut category. Older sets without this field appear under Personal.
