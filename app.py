#!/usr/bin/python
"""Persistent shortcut browser using the installed Omarchy dispatch adapter."""
import hashlib
import json
from pathlib import Path
import subprocess
import threading
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gio, GLib, Gdk
from shortcut_data import matches_query, details, split_shortcut, attach_tooltip
from theme import SystemTheme
from keyboard_view import KeyboardView
from info_view import InfoWindow

APP_ID = 'local.omarchy.Shortcuts'
STATE = Path.home() / '.config/omarchy-shortcuts/favorites.json'
SOURCE = Path('/usr/share/omarchy/bin/omarchy-menu-keybindings')
PROJECT = Path(__file__).resolve().parent
UI_STATE = STATE.parent / 'ui-state.json'
LEARNED_STATE = STATE.parent / 'learned.json'
LAUNCHER = Path.home() / '.local/share/applications/omarchy-shortcuts.desktop'


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2) + '\n')
    tmp.replace(path)


def project_info(shortcut_count):
    files = sorted(p for p in PROJECT.rglob('*') if p.is_file()
                   and not any(part.startswith('.') or part == '__pycache__'
                               for part in p.relative_to(PROJECT).parts))
    counts = [(str(p.relative_to(PROJECT)), len(p.read_text().splitlines()))
              for p in files if p.suffix in ('.py', '.lua', '.md', '.desktop', '.txt', '.json')]
    python_lines = sum(n for name, n in counts if name.endswith('.py'))
    listing = '\n'.join(f'  {name}: {n} lines' for name, n in counts)
    launcher_lines = len(LAUNCHER.read_text().splitlines()) if LAUNCHER.exists() else 0
    return [
        ('Search, hover and global shortcut',
         'Hover an action to see its description, dispatcher and full arguments. @w finds W with any modifier '
         'combination; @ctrl+w requires Ctrl and allows additional modifiers. @enter and @esc aliases work too. '
         'Combine tokens with text, such as @w window. Super+Shift+K launches or focuses this app and selects '
         'the search field. The binding is in ~/.config/hypr/bindings.lua.'),
        ('Live keyboard and system theme',
         'The keyboard uses the installed libxkbcommon to resolve the active Hyprland keyboard layout. '
         'All layers shows counts across all combinations; modifier buttons pin a layer. Held modifiers '
         'temporarily select their live layer. Clicking a key filters the list to its actions. '
         'Media and mouse shortcuts appear in the extra-keys section.\n\n'
         'The list is the primary/default view. Physical press/release events are shown only on the separate Live Keyboard tab. The local input_bridge.lua '
         'hook publishes numeric key states on the Hyprland IPC socket, with a short lease renewed by this app. '
         'Closing the app or returning to the list disables capture; a crashed app’s lease expires after ten seconds. '
         'No text or key history is written to disk. Modifiers also update through this local event bridge.\n\n'
         'Colors follow ~/.local/state/omarchy/current/theme/colors.toml, checked every second. '
         'The app falls back to GTK system styling if no Omarchy palette is available. No system theme is changed.'),
        ('Existing projects researched',
         'hyprKCS — Rust/GTK4 shortcut manager, XKB keyboard map, modifier layers and favorites. '
         'https://github.com/kosa12/hyprKCS\n\n'
         'Noctalia Keymap — Lua-aware Hyprland keyboard/list views; requires Noctalia v5. '
         'https://noctalia.dev/plugins/community/keymap\n\n'
         'Omarchy Key Visualizer — a live keypress overlay using Hyprland Lua input events. '
         'https://github.com/felixzsh/omarchy-key-visualizer\n\n'
         'This app retains its existing Omarchy adapter and implements its own GTK keyboard view. '
         'Research notes and primary documentation links are in RESEARCH.md.'),
        ('Linked Info and previews',
         'Press Escape to close Info. The Actions menu offers Copy Path as plain text for local files and Copy URL for web pages. Local-file previews offer Show in Folder to select the file in its containing folder. Info is a modal with linked sections and a preview pane. Click a file, folder or web link to inspect it here. '
         'Back and forward navigate preview history; the Actions menu contains Open Externally, Show in Folder, Copy Path and Copy File URI or Copy URL as appropriate. '
         'Files show source or formatted Markdown, folders show clickable entries, images render inline, and web pages '
         'show readable content with working links. Preview state stays in memory. Binary files show metadata and an external-open option.'),
        ('Built on this machine',
         'Python 3 with GTK4 / PyGObject for the native interface. Bash runs the installed '
         'Omarchy adapter; Hyprland controls window focus and actions. No web server or extra Python packages were installed.'),
        ('Project files and line counts',
         f'{PROJECT}\n\n{len(files)} project files; {python_lines} Python lines; '
         f'{sum(n for _, n in counts)} text lines in total. Counts include comments and blank lines, '
         'exclude hidden files and __pycache__, and are recalculated whenever Info opens.\n\n'
         f'{listing}\n\nExternal desktop launcher: {launcher_lines} lines (not included above).\n{LAUNCHER}'),
        ('Where the shortcuts come from',
         f'{shortcut_count} shortcuts currently loaded.\n\n'
         f'{SOURCE}\n\n'
         'Super+K is defined in /usr/share/omarchy/default/hypr/bindings/utilities.lua. '
         'The menu script reads live “hyprctl binds” output, supplements Lua bindings from source, '
         'and supplies some static shortcuts. Defaults live in /usr/share/omarchy/default/hypr/bindings/; '
         'personal bindings live in ~/.config/hypr/bindings.lua. '
         'The menu maintains generated keybindings-*.records caches under ~/.cache/omarchy/ '
         '(or $XDG_CACHE_HOME/omarchy/). Refresh reloads its current records.'),
        ('How clicking works',
         'The app reads the installed menu script up to its final menu/print branch and runs its '
         'output_binding_records function. Each record contains a shortcut, description, dispatcher, and arguments. '
         'Current is the default target and means the active workspace. App launches run there without focusing a window elsewhere. '
         'Window-specific actions use the most recently focused other window on that workspace. '
         'Choosing a named window pins the target for this session. Clicking focuses that target through hyprctl, then calls the installed '
         'dispatch_binding function. The reference window stays open. Categories are assigned from words '
         'in each description. Missing dispatch metadata and interactive mouse drags remain shortcut-only. '
         'Omarchy package files are never modified; an upstream adapter interface change may require an app update.'),
        ('Favorites / bookmarks',
         f'{STATE}\n\nA JSON list of stable shortcut IDs, derived from each key combination and description. '
         'Stars are saved immediately. Changing a shortcut’s keys or description gives it a new ID. '
         'Back up this file to keep your favorites; remove it while the app is closed to reset them.'),
        ('Learned shortcuts',
         f'{LEARNED_STATE}\n\nThe checkmark beside each bookmark toggles whether you have learned a shortcut. '
         'Learned status is saved immediately as stable shortcut IDs, independently of favorites. '
         'The All shortcuts / Learned / To learn filter combines with search and Favorites. '
         'The filter is session-only; the learned marks persist across restarts.'),
        ('Expanded and collapsed groups',
         f'{UI_STATE}\n\nThe expanded_groups object stores a true/false value for each category. '
         'Individual toggles and Expand All / Collapse All save immediately, including groups hidden by a filter. '
         'New groups start expanded. Search and Favorites filtering preserve this state. '
         'Remove this file while the app is closed to restore all groups to expanded.'),
        ('What is not saved',
         'The search query, Favorites-only filter, selected target window and keyboard modifier layer are session-only. The view always starts at List. '
         'The default target is Current; the target list updates every three seconds. Favorites and group states use temporary files '
         'followed by an atomic rename. No account, cloud sync or telemetry is implemented.'),
        ('Omarchy knowledge and configuration',
         '~/.codex/skills/omarchy/SKILL.md is the local assistant guide. Its companion Markdown guides are '
         'hyprland.md, plugins.md, theming.md, hooks.md, capture.md and contributing.md.\n\n'
         '/usr/share/omarchy/ contains installed commands, default configuration, shell/plugin code, themes, '
         'migrations and installation scripts. Personal desktop overrides live in ~/.config/hypr/ and '
         '~/.config/omarchy/. This app’s preferences are separate, in ~/.config/omarchy-shortcuts/.'),
        ('Launch and maintenance',
         f'Search “Omarchy Shortcuts” in the app launcher, or run:\npython {PROJECT / "app.py"}\n\n'
         f'Read {PROJECT / "README.md"} for maintenance notes. Super+K still opens the original menu. '
         'The current desktop launch log is /tmp/omarchy-shortcuts.log; it is temporary. '
         'Project changes take effect after restarting the app.')
    ]


def adapter(body, *args):
    source = SOURCE.read_text()
    marker = 'if [[ $1 == "--print" || $1 == "-p" ]]; then'
    if marker not in source:
        raise RuntimeError('Omarchy shortcut adapter changed; update the app adapter.')
    return subprocess.run(['bash', '-s', '--', *args], input=source.split(marker)[0] + '\n' + body,
                          text=True, capture_output=True, timeout=30, check=True).stdout

def records():
    result = []
    for line in adapter('output_binding_records').splitlines():
        parts = line.split('\t', 2)
        if len(parts) != 3 or ' → ' not in parts[0]:
            continue
        key, name = parts[0].split(' → ', 1)
        dispatcher, arg = parts[1:]
        identity = hashlib.sha256((key.strip() + '\0' + name).encode()).hexdigest()[:20]
        result.append(dict(id=identity, key=key.strip(), name=name, dispatcher=dispatcher, arg=arg, group=group(name)))
    return result

def group(name):
    n = name.lower()
    for title, words in [
        ('Workspaces', ['workspace', 'scratchpad']),
        ('Windows', ['window', 'full screen', 'full width', 'focus', 'group', 'split', 'cycle to']),
        ('Capture & clipboard', ['screenshot', 'screenrecord', 'clipboard', 'copy', 'paste', 'cut', 'color picker', 'download video']),
        ('Sound & media', ['audio', 'volume', 'microphone', 'mute', 'media', 'track', 'play', 'pause']),
        ('Desktop & system', ['theme', 'system', 'lock', 'nightlight', 'brightness', 'bluetooth', 'wifi', 'notification', 'display', 'power', 'screensaver']),
    ]:
        if any(w in n for w in words):
            return title
    return 'Apps & tools'

def clients():
    return json.loads(subprocess.check_output(['hyprctl', '-j', 'clients'], text=True, timeout=3))

class Shortcuts(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)
        self.connect('activate', self.activate)
        self.items = []
        self.targets = []
        self.window = None
        self.learned_filter = None
        try:
            self.learned = set(json.loads(LEARNED_STATE.read_text()))
        except (OSError, ValueError):
            self.learned = set()
        self.info_window = None
        self.keyboard_filter = None
        self.keyboard = None
        self.connect("shutdown", self.shutdown)
        try:
            saved = json.loads(UI_STATE.read_text()).get("expanded_groups", {})
            self.expanded_groups = {k: v for k, v in saved.items() if isinstance(v, bool)}
        except (OSError, ValueError, AttributeError):
            self.expanded_groups = {}
        try:
            self.favorites = set(json.loads(STATE.read_text()))
        except (OSError, ValueError):
            self.favorites = set()

    def activate(self, *_):
        if self.window:
            self.window.present()
            GLib.timeout_add(100, self.focus_search)
            return
        self.window = Gtk.ApplicationWindow(application=self, title='Omarchy Shortcuts')
        self.window.set_default_size(1050, 850)
        self.system_theme = SystemTheme(lambda: self.keyboard.area.queue_draw() if self.keyboard else None)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(root, 'set_margin_' + side)(16)
        self.window.set_child(root)
        header = Gtk.Box(spacing=12)
        title = Gtk.Label(label='Omarchy Shortcuts', xalign=0, hexpand=True)
        title.add_css_class('title-1')
        header.append(title)
        refresh = Gtk.Button(label='Refresh')
        refresh.connect('clicked', lambda *_: self.refresh())
        header.append(refresh)
        info = Gtk.Button(label='Info')
        info.connect('clicked', lambda *_: self.show_info())
        header.append(info)
        root.append(header)
        self.search = Gtk.SearchEntry(placeholder_text='Search actions, or @w / @ctrl+w…', hexpand=True)
        self.search.connect('changed', self.search_changed)
        self.only_favorites = Gtk.ToggleButton(label='★ Favorites')
        self.only_favorites.connect('toggled', lambda *_: self.render())
        controls = Gtk.Box(spacing=10)
        controls.append(self.search)
        controls.append(self.only_favorites)
        self.learned_filter = Gtk.DropDown.new_from_strings(['All shortcuts', 'Learned', 'To learn'])
        self.learned_filter.set_tooltip_text('Filter by learned status')
        self.learned_filter.connect('notify::selected', lambda *_: self.render())
        controls.append(self.learned_filter)
        root.append(controls)
        group_controls = Gtk.Box(spacing=10)
        self.view_stack = Gtk.Stack(vexpand=True, vhomogeneous=False, hhomogeneous=False)
        switcher = Gtk.StackSwitcher(stack=self.view_stack)
        group_controls.append(switcher)
        self.list_controls = Gtk.Box(spacing=10)
        group_controls.append(self.list_controls)
        for label, expanded in [('Expand All', True), ('Collapse All', False)]:
            button = Gtk.Button(label=label)
            button.connect('clicked', lambda _, value=expanded: self.set_all_expanded(value))
            self.list_controls.append(button)
        root.append(group_controls)
        target_row = Gtk.Box(spacing=10, vexpand=False, valign=Gtk.Align.START)
        target_row.append(Gtk.Label(label='Target window'))
        self.target_model = Gtk.StringList.new(['Current'])
        self.target = Gtk.DropDown(model=self.target_model, hexpand=True)
        target_row.append(self.target)
        root.append(target_row)
        self.keyboard = KeyboardView(self.select_key, lambda: self.system_theme.colors)
        self.keyboard_notice = Gtk.Label(label='', xalign=0, wrap=True, visible=False)
        self.keyboard_notice.add_css_class('dim-label')
        root.append(self.keyboard_notice)
        scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, valign=Gtk.Align.START)
        scroll.set_child(self.list_box)
        self.view_stack.add_titled(scroll, 'list', 'List')
        keyboard_scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        keyboard_scroll.set_child(self.keyboard)
        self.view_stack.add_titled(keyboard_scroll, 'keyboard', 'Live Keyboard')
        self.view_stack.set_visible_child_name('list')
        self.view_stack.connect('notify::visible-child-name', self.view_changed)
        root.append(self.view_stack)
        self.status = Gtk.Label(label='Loading shortcuts…', xalign=0, wrap=True)
        self.status.add_css_class('dim-label')
        root.append(self.status)
        self.refresh_targets()
        self.window.present()
        self.refresh()
        GLib.timeout_add_seconds(3, self.refresh_targets)
        GLib.timeout_add(150, self.focus_search)

    def view_changed(self, *_):
        is_keyboard = self.view_stack.get_visible_child_name() == 'keyboard'
        self.keyboard.set_live(is_keyboard)
        self.list_controls.set_visible(not is_keyboard)

    def shutdown(self, *_):
        if self.keyboard:
            self.keyboard.stop()

    def focus_search(self):
        self.view_stack.set_visible_child_name('list')
        if self.info_window:
            self.info_window.close()
        self.window.present()
        try:
            ours = next((c for c in clients() if c['class'] == APP_ID and c['title'] == 'Omarchy Shortcuts'), None)
            if ours:
                subprocess.run(['hyprctl', 'eval', 'hl.dispatch(hl.dsp.focus({ window = ' + json.dumps('address:' + ours['address']) + ' }))'], capture_output=True, timeout=2)
        except (subprocess.SubprocessError, ValueError):
            pass
        self.search.grab_focus()
        self.search.select_region(0, -1)
        return False

    def search_changed(self, *_):
        self.keyboard_filter = None
        if hasattr(self, 'keyboard_notice'):
            self.keyboard_notice.set_text('')
            self.keyboard_notice.set_visible(False)
        self.render()

    def select_key(self, symbol, layer):
        if not symbol:
            return
        self.view_stack.set_visible_child_name('list')
        self.search.set_text('@' + symbol.lower())
        self.keyboard_filter = (symbol, layer)
        label = ' + '.join(sorted(layer)) if layer else ('All layers' if layer is None else 'No modifiers')
        self.keyboard_notice.set_visible(True)
        self.keyboard_notice.set_text(f'Keyboard selection: {label} + {symbol} · Edit search to clear the layer filter')
        self.render()

    def refresh_targets(self):
        try:
            selected = self.target.get_selected()
            old = self.targets[selected - 1]['address'] if 0 < selected <= len(self.targets) else None
            updated = sorted([c for c in clients() if c['class'] != APP_ID and c['mapped']], key=lambda c: c.get('focusHistoryID', 999))
            labels = [f"{c['title'][:65]}  ·  workspace {c['workspace']['name']}" for c in updated]
            if [(c['address'], c['title']) for c in updated] != [(c['address'], c['title']) for c in self.targets]:
                self.targets = updated
                self.target_model.splice(0, self.target_model.get_n_items(), ['Current'] + labels)
                self.target.set_selected(next((i + 1 for i,c in enumerate(updated) if c['address'] == old), 0))
        except (subprocess.SubprocessError, ValueError):
            pass
        return True

    def refresh(self):
        def work():
            try:
                items = records()
                GLib.idle_add(self.loaded, items)
            except Exception as e:
                GLib.idle_add(self.status.set_text, 'Could not load shortcuts: ' + str(e))
        threading.Thread(target=work, daemon=True).start()

    def loaded(self, items):
        self.items = items
        if self.keyboard:
            self.keyboard.set_items(items)
        self.render()

    def favorite(self, item):
        if item['id'] in self.favorites:
            self.favorites.remove(item['id'])
        else:
            self.favorites.add(item['id'])
        save_json(STATE, sorted(self.favorites))
        self.render()

    def toggle_learned(self, item):
        if item['id'] in self.learned:
            self.learned.remove(item['id'])
        else:
            self.learned.add(item['id'])
        save_json(LEARNED_STATE, sorted(self.learned))
        self.render()

    def filtered_items(self):
        query = self.search.get_text().casefold()
        mode = self.learned_filter.get_selected() if self.learned_filter else 0
        matches = [r for r in self.items if matches_query(r, query)
                   and (not self.only_favorites.get_active() or r['id'] in self.favorites)
                   and (mode != 1 or r['id'] in self.learned)
                   and (mode != 2 or r['id'] not in self.learned)]
        if self.keyboard_filter:
            symbol, layer = self.keyboard_filter
            matches = [r for r in matches if split_shortcut(r['key'])[1] == symbol
                       and (layer is None or split_shortcut(r['key'])[0] == layer)]
        return matches

    def set_all_expanded(self, expanded):
        for category in {item['group'] for item in self.items}:
            self.expanded_groups[category] = expanded
        save_json(UI_STATE, {'expanded_groups': self.expanded_groups})
        self.render()

    def group_toggled(self, section, _property, category):
        self.expanded_groups[category] = section.get_expanded()
        save_json(UI_STATE, {'expanded_groups': self.expanded_groups})

    def open_folder(self, folder):
        try:
            folder.mkdir(parents=True, exist_ok=True)
            Gio.AppInfo.launch_default_for_uri(folder.as_uri(), None)
        except Exception as e:
            self.status.set_text('Could not open folder: ' + str(e))

    def show_info(self):
        if self.info_window:
            self.info_window.close()
        self.info_window = InfoWindow(self, project_info(len(self.items)), PROJECT, STATE.parent)
        self.info_window.connect('close-request', self.info_closed)
        self.info_window.present()

    def info_closed(self, *_):
        self.info_window = None
        return False

    def render(self):
        while child := self.list_box.get_first_child():
            self.list_box.remove(child)
        matches = self.filtered_items()
        if hasattr(self, 'status'):
            learned_count = sum(r['id'] in self.learned for r in self.items)
            self.status.set_text(f'{len(matches)} of {len(self.items)} shortcuts · {learned_count} learned')
        if not matches:
            self.list_box.append(Gtk.Label(label='No shortcuts match these filters.', margin_top=30))
        for category in sorted({r['group'] for r in matches}):
            members = [r for r in matches if r['group'] == category]
            section = Gtk.Expander(label=f'{category}  ·  {len(members)}', expanded=self.expanded_groups.get(category, True))
            section.connect('notify::expanded', self.group_toggled, category)
            rows = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
            rows.add_css_class('boxed-list')
            for item in members:
                row = Gtk.Box(spacing=8, margin_top=4, margin_bottom=4, margin_start=8, margin_end=8)
                star = Gtk.Button(label='★' if item['id'] in self.favorites else '☆')
                star.set_tooltip_text('Remove favorite' if item['id'] in self.favorites else 'Add favorite')
                star.connect('clicked', lambda _, r=item: self.favorite(r))
                row.append(star)
                learned = Gtk.ToggleButton(label='✓' if item['id'] in self.learned else '○', active=item['id'] in self.learned)
                learned.set_tooltip_text('Mark as not learned' if item['id'] in self.learned else 'Mark as learned')
                learned.connect('toggled', lambda _, r=item: self.toggle_learned(r))
                row.append(learned)
                action = Gtk.Button(hexpand=True)
                action.add_css_class('flat')
                content = Gtk.Box(spacing=12)
                content.append(Gtk.Label(label=item['name'], xalign=0, hexpand=True, wrap=True))
                key = Gtk.Label(label=item['key'], xalign=1)
                key.add_css_class('dim-label')
                content.append(key)
                action.set_child(content)
                draggable = 'drag(' in item['arg'] or 'resize({' in item['arg'] and 'mouse:' in item['key'].lower()
                action.set_sensitive(bool(item['dispatcher']) and not draggable)
                note = 'Use the mouse shortcut to drag interactively.' if draggable else (
                    'This action is only available through its keyboard shortcut.' if not item['dispatcher'] else '')
                attach_tooltip(action, item, note)
                attach_tooltip(row, item, note)
                action.connect('clicked', lambda _, r=item: self.run_action(r))
                row.append(action)
                rows.append(row)
            section.set_child(rows)
            self.list_box.append(section)

    def run_action(self, item):
        index = self.target.get_selected()
        target = self.targets[index - 1] if 0 < index <= len(self.targets) else None
        self.status.set_text('Running ' + item['name'] + '…')
        def work():
            try:
                action_target = target
                # Current means the active workspace, never the last window elsewhere.
                needs_window = (item['dispatcher'] == 'sendshortcut' or
                                'hl.dsp.window.' in item['arg'] or
                                'hl.dsp.send_key_state' in item['arg'])
                if index == 0 and needs_window:
                    workspace = json.loads(subprocess.check_output(['hyprctl', '-j', 'activeworkspace'], text=True, timeout=3))['id']
                    candidates = sorted([c for c in clients() if c['class'] != APP_ID and c['mapped']
                                         and c['workspace']['id'] == workspace],
                                        key=lambda c: c.get('focusHistoryID', 999))
                    action_target = candidates[0] if candidates else None
                if action_target:
                    current = {c['address'] for c in clients()}
                    if action_target['address'] not in current:
                        raise RuntimeError('Target window has closed. Select another window.')
                    selector = json.dumps('address:' + action_target['address'])
                    subprocess.run(['hyprctl', 'eval', 'hl.dispatch(hl.dsp.focus({ window = ' + selector + ' }))'], check=True, capture_output=True, text=True, timeout=3)
                elif needs_window:
                    raise RuntimeError('No target window on the current workspace. Select a window explicitly.')
                adapter('dispatch_binding "$1" "$2"', item['dispatcher'], item['arg'])
                GLib.idle_add(self.status.set_text, 'Ran ' + item['name'])
            except Exception as e:
                GLib.idle_add(self.status.set_text, 'Action failed: ' + str(e))
        threading.Thread(target=work, daemon=True).start()

if __name__ == '__main__':
    Shortcuts().run()
