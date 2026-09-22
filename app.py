#!/usr/bin/python
"""Persistent shortcut browser using the installed Omarchy dispatch adapter."""
import time
STARTED = time.perf_counter()
ACTIVATED = STARTED
import os
import hashlib
from difflib import SequenceMatcher
from collections import OrderedDict
import json
from pathlib import Path
import subprocess
import threading
import sys
import shutil
# Avoid the slow default renderer initialization on this desktop.
# Respect an explicit renderer selected by the caller.
os.environ.setdefault('GSK_RENDERER', 'gl')
if __name__ == '__main__' and os.environ.get('GDK_BACKEND') != 'broadway' and Path('/usr/lib/libgtk4-layer-shell.so').exists() and 'libgtk4-layer-shell.so' not in os.environ.get('LD_PRELOAD', ''):
    os.environ['LD_PRELOAD'] = '/usr/lib/libgtk4-layer-shell.so' + (' ' + os.environ['LD_PRELOAD'] if os.environ.get('LD_PRELOAD') else '')
    os.execv(sys.executable, [sys.executable, *sys.argv])
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gio, GLib, Gdk, Pango, GObject, GdkPixbuf
from shortcut_data import action_tooltip, matches_query, details, split_shortcut, attach_tooltip, reveal_indicators_on_hover, make_switch_row, canonical, hotkey_caps
from theme import SystemTheme, LOOKS
from keyboard_view import KeyboardView
from binding_sources import SOURCES, load as load_source, refresh_registry
import shortcut_sets
import source_library
import preferences
import source_cache
import localization
from info_view import InfoWindow
from guide import GuideController
from features import FEATURES, DEFAULT_FEATURES, ACTION_FEATURES, gallery
from shortcut_manager import ShortcutManagerPanel
from shortcut_types import TYPES, FILTERS, annotate, load_presentations, matches_type

APP_ID = 'com.aylith.Bindlume'
STATE = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'bindlume/favorites.json'
SOURCE = Path('/usr/share/omarchy/bin/omarchy-menu-keybindings')
PROJECT = Path(__file__).resolve().parent
UI_STATE = STATE.parent / 'ui-state.json'
LEARNED_STATE = STATE.parent / 'learned.json'
LAUNCHER = Path.home() / '.local/share/applications/bindlume.desktop'


# One source for keyboard dispatch and the in-app reference.
APP_SHORTCUTS = [
    ('F1', 'Show app shortcuts', 'help'),
    ('<Control>m', 'Manage shortcuts', 'manage'),
    ('<Control>Return', 'Apply shortcut (Editor)', 'manage_apply'),
    ('<Control>q', 'Quit app and background process', 'quit'),
    ('<Alt>Left', 'Back from shortcut management', 'back'),
    ('<Alt>f', 'Toggle filters (List)', 'filters'),
    ('<Alt>g', 'Toggle flat list (List)', 'flat'),
    ('<Alt>c', 'Toggle columns (List)', 'columns'),
    ('<Alt>v', 'Enable live filter (List; Escape exits)', 'live'),
    ('<Control><Shift>o', 'Toggle key overlay (Keyboard)', 'overlay'),
    ('<Control><Shift>b', 'Bookmark selected shortcut (List)', 'bookmark_row'),
    ('<Control><Shift>l', 'Hide/show selected shortcut (List)', 'learn_row'),
    ('<Control>k', 'Switch List / Keyboard', 'view'),
    ('<Control>b', 'Toggle bookmarks filter', 'favorites'),
    ('<Control>f', 'Focus search', 'search'),
    ('<Control>e', 'Expand all groups (List)', 'expand'),
    ('<Control><Shift>e', 'Collapse all groups (List)', 'collapse'),
    ('<Control>r', 'Refresh shortcuts', 'refresh'),
    ('F10', 'Open view options', 'menu'),
    ('<Shift>F10', 'Open app settings', 'commands'),
    ('<Control><Shift>p', 'Choose features', 'features'),
    ('<Control>period', 'Choose features', 'features'),
    ('<Control>j', 'Toggle chat and focus input', 'chat'),
    ('<Control><Shift>h', 'Choose a conversation', 'chat_history'),
    ('<Control><Shift>comma', 'Open Keyboard Guide settings', 'guide'),
    ('<Control>comma', 'Open settings', 'preferences'),
    ('<Control>i', 'Open Info', 'info'),
    ('<Control><Shift>f', 'Clear all filters', 'clear'),
    ('<Alt>s', 'Cycle bookmarked sources', 'source'),
    ('<Alt><Shift>s', 'Choose shortcut source', 'source_menu'),
    ('<Control><Alt>s', 'Open settings', 'preferences'),
    ('<Alt>t', 'Choose shortcut type', 'type'),
    ('<Alt>l', 'Choose visibility', 'learned'),
    ('<Alt>w', 'Choose window for shortcut actions', 'target'),
    ('<Control><Shift>n', 'Toggle numpad (Keyboard)', 'numpad'),
    ('<Control><Shift>w', 'Toggle fit width (Keyboard)', 'fit'),
    ('<Control><Shift>a', 'Toggle all modifier layers (Keyboard)', 'layers'),
]


def application_icon(source):
    if source.startswith('/'):
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(source, 32, 32, True)
            return Gtk.Image.new_from_paintable(Gdk.Texture.new_for_pixbuf(pixbuf))
        except GLib.Error:
            return Gtk.Image.new_from_icon_name('application-x-executable-symbolic')
    return Gtk.Image.new_from_icon_name(source)


def startup_mark(stage):
    elapsed = round((time.perf_counter() - STARTED) * 1000, 1)
    if os.environ.get('GDK_BACKEND') == 'broadway' and not os.environ.get('SHORTCUTS_STARTUP_LOG'): return
    path = Path(os.environ.get('SHORTCUTS_STARTUP_LOG') or Path.home() / '.local/state/bindlume/startup.jsonl')
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if stage == 'imports' and path.exists() and path.stat().st_size > 1024 * 1024:
            path.replace(path.with_suffix('.previous.jsonl'))
        with path.open('a') as stream:
            stream.write(json.dumps(dict(pid=os.getpid(), stage=stage, elapsed_ms=elapsed, activation_ms=round((time.perf_counter()-ACTIVATED)*1000, 1))) + '\n')
    except OSError:
        pass

startup_mark('imports')


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2) + '\n')
    tmp.replace(path)


def project_info(shortcut_count):
    tr = localization.text
    listing = '\n'.join(f'{p.name}: {len(p.read_text().splitlines())}' for p in sorted(PROJECT.glob('*.py')))
    return [
        (tr('About'), tr('Browse, find and remember shortcuts for your desktop and installed apps.')),
        (tr('Search'), tr('Search by name, or type @ctrl+w to find a key combination. Bookmark useful shortcuts and hide the ones you do not need.')),
        (tr('Window for shortcut actions'), tr('Current is the default target. Choose another window from View options to send actions there.')),
        (tr('Keyboard guide'), tr('Hold Super to see the guide. Its settings control spacing, icons, position and which shortcuts appear. Open guide settings with Ctrl+Shift+,.')),
        (tr('Agent chat'), tr('Ask an installed agent to find shortcuts or change app settings. Conversations are saved locally; messages are sent to the agent you choose.')),
        (tr('Configuration files'), str(UI_STATE.parent)+'\n\n'+ '\n'.join(str(path) for path in (UI_STATE,STATE,LEARNED_STATE,UI_STATE.parent/'keyboard-guide.json'))),
        (tr('Documentation'), '\n'.join(str(PROJECT/name) for name in ('README.md','SHORTCUT_SETS.md','skills/bindlume/SKILL.md'))),
        (tr('Project files'), tr('{count} shortcuts').format(count=shortcut_count)+'\n\n'+str(PROJECT)+'\n\n'+listing),
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
    presentation = load_presentations()
    return annotate(result, presentation["bindings"], presentation["showActions"])

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

class ShortcutEntry(GObject.Object):
    def __init__(self, data):
        super().__init__()
        self.data = data


class ShortcutSection(Gtk.Box):
    def __init__(self, title, count, expanded, changed, icon=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0, hexpand=True)
        self.add_css_class('category-card')
        self.set_overflow(Gtk.Overflow.HIDDEN)
        self.header = Gtk.ToggleButton(active=expanded, hexpand=True)
        self.header.add_css_class('category-header')
        content = Gtk.Box(spacing=12)
        if icon:
            content.append(Gtk.Label(label=icon, margin_end=4))
        content.append(Gtk.Label(label=title, xalign=0, hexpand=True))
        badge = Gtk.Label(label=str(count), valign=Gtk.Align.CENTER)
        badge.add_css_class('count-badge')
        content.append(badge)
        self.arrow = Gtk.Image(icon_name='pan-down-symbolic' if expanded else 'pan-end-symbolic')
        content.append(self.arrow)
        self.header.set_child(content)
        self.append(self.header)
        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, visible=expanded)
        self.append(self.body)
        def toggled(*_):
            self.body.set_visible(self.get_expanded())
            self.arrow.set_from_icon_name('pan-down-symbolic' if self.get_expanded() else 'pan-end-symbolic')
            changed(self)
        self.header.connect('toggled', toggled)

    def get_expanded(self):
        return self.header.get_active()

    def set_expanded(self, value):
        self.header.set_active(value)

    def set_child(self, child):
        self.body.append(child)


class Shortcuts(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        Gtk.Window.set_default_icon_name(APP_ID)
        localization.install(self)
        import dialogs
        dialogs.install(self)
        import overlay_surface
        self.overlay_surfaces = None
        self.connect('startup', lambda *_: overlay_surface.install(self))
        self.connect('command-line', self.command_line)
        self.connect('activate', self.activate)
        for name, callback in [('hide', self.hide_main), ('quit', lambda *_: self.quit()), ('restart', lambda *_: self.restart())]:
            action = Gio.SimpleAction.new(name, None)
            action.connect('activate', callback)
            self.add_action(action)
        self.items = []
        self.key_size_group = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL)
        self.targets = []
        self.window = None
        self.type_filter = None
        self.learned_filter = None
        try:
            self.learned = set(json.loads(LEARNED_STATE.read_text()))
        except (OSError, ValueError):
            self.learned = set()
        self.guide_window = None
        self.info_window = None
        self.keyboard_filter = None
        self.keyboard = None
        self.connect("shutdown", self.shutdown)
        try:
            saved = json.loads(UI_STATE.read_text())
            if not isinstance(saved, dict):
                saved = {}
        except (OSError, ValueError):
            saved = {}
        if not isinstance(saved.get('features', {}), dict): saved['features'] = {}
        if not isinstance(saved.get('search_history', []), list): saved['search_history'] = []
        self.features = {**({key: True for key in FEATURES} if saved else DEFAULT_FEATURES), **{k: v for k,v in saved.get('features', {}).items() if k in FEATURES and isinstance(v,bool)}}
        for optional in ('appearance', 'inputs'):
            if optional not in saved.get('features', {}): self.features[optional] = False
        self.features.pop('animations', None)
        saved_look = 'square' if saved.get('look') == 'omarchy' else saved.get('look', 'system')
        self.look = saved_look if saved_look in LOOKS else 'system'
        self.feature_view = {key: value for key, value in saved.get('feature_view', {}).items() if key in ('grid', 'previews', 'descriptions') and isinstance(value, bool)} if isinstance(saved.get('feature_view', {}), dict) else {}
        self.preferences = dict(preferences.DEFAULTS, **{k:v for k,v in saved.get('preferences', {}).items() if k in preferences.DEFAULTS}) if isinstance(saved.get('preferences', {}), dict) else preferences.DEFAULTS.copy()
        if isinstance(saved.get('preferences', {}), dict) and 'system_typography' not in saved.get('preferences', {}) and any(k in saved.get('preferences', {}) for k in ('font_family','font_size')):
            self.preferences['system_typography'] = False
        localization.language = self.preferences['language']
        # Preserve an explicit legacy opt-out; the old enabled default now follows the desktop.
        if (not isinstance(saved.get('preferences'), dict) or 'window_animations' not in saved['preferences']) and saved.get('animate_windows') is False:
            self.preferences['window_animations'] = 'off'
        self.search_history = [q for q in saved.get('search_history', []) if isinstance(q,str) and q.strip()][:20]
        self.history_timer = None
        ratio = saved.get('chat_split_ratio', .6)
        self.chat_split_ratio = max(.2, min(.8, ratio)) if isinstance(ratio, (int, float)) else .6
        self.keyboard_preferences = saved.get('keyboard_view', {})
        if not isinstance(self.keyboard_preferences, dict): self.keyboard_preferences = {}
        self.flat_list = saved.get('flat_list', saved.get('omarchy_style', not bool(saved))) is True
        self.columns = saved.get('columns', saved.get('omarchy_style', not bool(saved))) is True
        self.shortcut_column_width = 0
        self.column_signature = None
        self.search_expanded = {}
        self.source_name = saved.get('source', 'Omarchy')
        if self.source_name not in SOURCES: self.source_name = 'Omarchy'
        favorites = saved.get('favorite_sources', ['Omarchy'])
        self.favorite_sources = set(favorites) & set(SOURCES) if isinstance(favorites, list) else {'Omarchy'}
        self.source_note = ''
        self.disabled_sources = set(saved.get('disabled_sources', [])) if isinstance(saved.get('disabled_sources', []), list) else set()
        self.source_counts = {}
        self.source_badges = set()
        self.counts_busy = False
        self.refresh_busy = False
        self.saved_target = saved.get('target', None)
        self.live_view = saved.get('live_view', False) is True
        self.live_keys = {}
        self.live_mods = {}
        self.live_pressed_modifiers = {}
        self.saved_view = saved.get('view', 'list')
        self.show_list_filters = saved.get('show_list_filters', False) is True
        groups = saved.get('expanded_groups', {})
        self.expanded_groups = {k: v for k, v in groups.items() if isinstance(v, bool)} if isinstance(groups, dict) else {}
        filters = saved.get('filters', {})
        self.saved_filters = filters if isinstance(filters, dict) else {}
        try:
            self.favorites = set(json.loads(STATE.read_text()))
        except (OSError, ValueError):
            self.favorites = set()

    def command_line(self, _application, command_line):
        arguments = command_line.get_arguments()[1:]
        if arguments and arguments not in (['--guide'], ['--background'], ['--manage']):
            command_line.printerr('Usage: bindlume [--guide|--background|--manage]\n')
            return 2
        self.background_start = '--background' in arguments
        self.activate()
        if '--manage' in arguments:
            self.show_management()
        if '--guide' in arguments:
            self.show_guide()
        return 0

    def bring_forward(self):
        if self.overlay_surfaces is not None: return
        if not isinstance(self.window.get_display(), Gdk.Display) or os.environ.get('GDK_BACKEND') == 'broadway':
            return
        if not os.environ.get('HYPRLAND_INSTANCE_SIGNATURE') or not shutil.which('hyprctl'):
            return
        def query(name):
            return json.loads(subprocess.check_output(['hyprctl', '-j', name], timeout=2))
        try:
            workspace = query('activeworkspace')['id']
        except (OSError, ValueError, KeyError, subprocess.SubprocessError):
            return
        def focus():
            try:
                clients = []
                for attempt in range(5):
                    clients = [client for client in query('clients')
                               if client.get('pid') == os.getpid() and client.get('class') == APP_ID]
                    if clients: break
                    time.sleep(.03)
                clients.sort(key=lambda client: client.get('title') != 'Bindlume')
                for client in clients:
                    address = 'address:' + client['address']
                    if client.get('workspace', {}).get('id') != workspace:
                        code = 'hl.dsp.window.move({workspace = ' + json.dumps(str(workspace)) + ', window = ' + json.dumps(address) + ', follow = false})'
                        result = subprocess.run(['hyprctl', 'dispatch', code], capture_output=True, timeout=2)
                        if result.returncode:
                            subprocess.run(['hyprctl', 'dispatch', 'movetoworkspacesilent',
                                            f'{workspace},{address}'], capture_output=True, timeout=2)
                if clients:
                    address = 'address:' + clients[-1]['address']
                    result = subprocess.run(['hyprctl', 'dispatch', 'hl.dsp.focus({window = ' + json.dumps(address) + '})'],
                                            capture_output=True, timeout=2)
                    if result.returncode:
                        subprocess.run(['hyprctl', 'dispatch', 'focuswindow', address], capture_output=True, timeout=2)
            except (OSError, ValueError, KeyError, subprocess.SubprocessError):
                pass
        threading.Thread(target=focus, daemon=True).start()

    def activate(self, *_):
        global ACTIVATED
        ACTIVATED = time.perf_counter()
        startup_mark('activation-request')
        if self.window:
            if not self.window.get_visible() and not self.preferences['remember_search']:
                self.search.set_text('')
            self.bring_forward()
            self.window.present()
            self.search.grab_focus()
            self.search.select_region(0, -1)
            return
        startup_mark('activate')
        self.window = Gtk.ApplicationWindow(application=self, title=__import__('brand').NAME)
        from input_controls import Controls
        self.input_controls = Controls(self)
        self.update_window_size()
        self.window.connect('close-request', self.hide_main)
        self.window.add_css_class('shortcuts-app')
        self.window.connect('notify::is-active', self.keyboard_focus_changed)
        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect('key-pressed', self.close_on_escape)
        keys.connect('key-released', self.live_key_released)
        keys.connect('modifiers', self.live_modifiers_changed)
        self.window.add_controller(keys)
        self.system_theme = SystemTheme(lambda: self.keyboard.area.queue_draw() if self.keyboard else None)
        self.system_theme.set_look(self.look if self.feature_enabled('appearance') else 'system')
        self.system_theme.set_preferences(self.preferences)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.main_root = root
        root.add_css_class('main-root')
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(root, 'set_margin_' + side)(0)
        self.main_pane = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL, wide_handle=False)
        self.main_pane.add_css_class("chat-splitter")
        self.main_pane.set_start_child(root)
        self.main_pane.set_resize_start_child(True)
        self.main_pane.set_shrink_start_child(True)
        self.main_pane.set_shrink_end_child(False)
        self.main_pane.connect('notify::position', self.chat_split_changed)
        self.window.set_child(self.main_pane)
        self.chat_panel = None
        toolbar = Gtk.Box(spacing=6)
        toolbar.add_css_class('main-toolbar')
        self.management_back = Gtk.Button(label='Back to shortcuts', hexpand=True, visible=False)
        self.management_back.connect('clicked', self.close_management)
        action_tooltip(self.management_back, 'Back to shortcuts (Alt+Left)')
        toolbar.append(self.management_back)
        self.search = Gtk.Entry(placeholder_text='Search shortcuts… (@ to search keys)', hexpand=True)
        self.search.add_css_class('main-search')
        self.search.connect('changed', self.update_search_clear)
        self.search.connect('icon-release', self.clear_search_icon)
        self.update_search_clear(self.search)

        action_tooltip(self.search, 'Search actions or key combinations, such as @w or @ctrl+w (Ctrl+F)')
        self.only_favorites = Gtk.ToggleButton(icon_name='starred-symbolic')
        action_tooltip(self.only_favorites, 'Show bookmarks only (Ctrl+B)')
        toolbar.append(self.only_favorites)
        self.source_picker = Gtk.DropDown.new_from_strings(SOURCES)
        self.source_picker.set_factory(self.source_factory())
        self.source_picker.set_list_factory(self.source_factory(show_favorites=True))
        self.source_picker.set_selected(SOURCES.index(self.source_name))
        action_tooltip(self.source_picker, 'Choose shortcut source; Alt+S cycles starred sources (Alt+Shift+S)')
        self.source_picker.connect('notify::selected', self.source_changed)
        toolbar.append(self.source_picker)
        self.list_controls = Gtk.Box(spacing=4)
        for icon, label, expanded in [('pan-down-symbolic', 'Expand all', True), ('pan-up-symbolic', 'Collapse all', False)]:
            button = Gtk.Button(icon_name=icon)
            action_tooltip(button, label + (' (Ctrl+E)' if expanded else ' (Ctrl+Shift+E)'))
            button.connect('clicked', lambda _, value=expanded: self.set_all_expanded(value))
            self.list_controls.append(button)
        toolbar.append(self.list_controls)
        self.view_toggle = Gtk.ToggleButton(icon_name='input-keyboard-symbolic')
        action_tooltip(self.view_toggle, 'Switch to keyboard view (Ctrl+K)')
        self.view_toggle.connect('toggled', self.toggle_view)
        toolbar.append(self.search)
        menu = Gtk.MenuButton(icon_name='view-more-symbolic')
        action_tooltip(menu, 'Options for the current view (F10)')
        self.menu_button = menu
        toolbar.append(menu)
        toolbar.append(self.view_toggle)

        self.app_menu_button = Gtk.MenuButton(icon_name='emblem-system-symbolic')
        action_tooltip(self.app_menu_button, 'App settings and tools (Shift+F10)')
        self.chat_button = Gtk.Button(icon_name='user-available-symbolic')
        action_tooltip(self.chat_button, 'Toggle chat and focus input (Ctrl+J)')
        self.chat_button.connect('clicked', lambda *_: self.show_chat(self.main_pane.get_end_child() is None))
        toolbar.append(self.chat_button)
        toolbar.append(self.app_menu_button)
        root.append(toolbar)
        popover = Gtk.Popover()
        popover.set_halign(Gtk.Align.END)
        menu.set_popover(popover)
        options = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(options, 'set_margin_' + side)(12)
        menu_scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,
                                        max_content_height=340, propagate_natural_height=True)
        self.view_heading = view_heading = Gtk.Label(label='View options', xalign=0)
        view_heading.add_css_class('heading')
        options.append(view_heading)
        menu_scroll.set_child(options)
        self.menu_pages = menu_pages = Gtk.Stack(vhomogeneous=False, hhomogeneous=True)
        main_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        main_page.append(menu_scroll)
        more = Gtk.Button(label='App settings', margin_start=12, margin_end=12, margin_bottom=12)
        action_tooltip(more, 'Open shortcut management, guide settings, refresh, About, and Quit (Shift+F10)')
        more.set_visible(False)
        main_page.append(more)
        command_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                               margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        back = Gtk.Button(label='‹  Settings')
        action_tooltip(back, 'Return to filters and settings (F10)')
        back.set_visible(False)
        command_page.append(back)
        app_heading = Gtk.Label(label='App settings', xalign=0)
        app_heading.add_css_class('heading')
        command_page.append(app_heading)
        menu_pages.add_named(main_page, 'settings')
        app_popover = Gtk.Popover(halign=Gtk.Align.END)
        app_popover.set_child(command_page)
        self.app_menu_button.set_popover(app_popover)
        self.wire_menu_toggle(menu, 'menu')
        self.wire_menu_toggle(self.app_menu_button, 'commands')
        more.connect('clicked', lambda *_: self.app_menu_button.popup())
        back.connect('clicked', lambda *_: menu_pages.set_visible_child_name('settings'))
        def settings_closed(*_):
            choice = getattr(self, 'choice_popover', None)
            anchor = choice.get_parent() if choice else None
            if anchor and anchor.is_ancestor(popover):
                self.dismiss_choice()
            menu_pages.set_visible_child_name('settings')
        popover.connect('closed', settings_closed)
        def app_settings_closed(*_):
            choice = getattr(self, 'choice_popover', None)
            anchor = choice.get_parent() if choice else None
            if anchor and anchor.is_ancestor(app_popover): self.dismiss_choice()
        app_popover.connect('closed', app_settings_closed)
        popover.set_child(menu_pages)
        self.filter_bar = Gtk.Box(spacing=8)
        root.append(self.filter_bar)
        self.show_filters_row = Gtk.Box(spacing=16)
        self.show_filters_row.append(Gtk.Label(label='Show filters', xalign=0, hexpand=True))
        show_filters = Gtk.Switch(active=self.show_list_filters, valign=Gtk.Align.CENTER)
        action_tooltip(show_filters, 'Show the modifier and shortcut-type filters above the list. Keyboard view always shows these controls (Alt+F)')
        show_filters.connect('notify::active', self.list_filters_toggled)
        self.show_filters_row.append(show_filters)
        make_switch_row(self.show_filters_row, show_filters)
        options.append(self.show_filters_row)
        self.settings_switches = {'Show filters': show_filters}
        self.settings_rows = {'Show filters': self.show_filters_row}

        for label, active, callback in [
            ('Flat list', self.flat_list, self.flat_changed),
            ('Columns', self.columns, self.columns_changed),
        ]:
            setting = Gtk.Box(spacing=16)
            setting.append(Gtk.Label(label=label, xalign=0, hexpand=True))
            toggle = Gtk.Switch(active=active, valign=Gtk.Align.CENTER)
            toggle.set_tooltip_text({
                'Flat list': 'Show one continuous list without category headers. Expand and collapse controls are hidden.',
                'Columns': 'Put larger shortcut keys on the left, followed by an arrow and the description. Column width stays fixed while filtering.',
            }[label])
            if label in ('Flat list', 'Columns'):
                action_tooltip(toggle, toggle.get_tooltip_text() + (' (Alt+G)' if label == 'Flat list' else ' (Alt+C)'))
            self.settings_switches[label] = toggle
            self.settings_rows[label] = setting
            toggle.connect('notify::active', callback)
            setting.append(toggle)
            make_switch_row(setting, toggle)
            options.append(setting)
        self.learned_filter = Gtk.DropDown.new_from_strings(['Show all', 'Hidden', 'Not hidden'])
        action_tooltip(self.learned_filter, 'Filter by visibility (Alt+L)')
        visibility_label = Gtk.Label(label='Visibility', xalign=0)
        action_tooltip(visibility_label, 'Show all shortcuts, only hidden shortcuts, or only shortcuts that are not hidden (Alt+L)')
        self.visibility_label = visibility_label
        options.append(visibility_label)
        options.append(self.learned_filter)

        self.type_filter = Gtk.DropDown.new_from_strings([label for _, label in FILTERS])
        action_tooltip(self.type_filter, 'Choose shortcut type (Alt+T)')
        self.filter_bar.append(self.type_filter)
        live_row = Gtk.Box(spacing=8)
        live_row.append(Gtk.Label(label='Live filter'))
        self.live_switch = Gtk.Switch(active=self.live_view, valign=Gtk.Align.CENTER)
        action_tooltip(self.live_switch, 'Hold keys to filter shortcuts. Desktop shortcuts are inhibited while this window is focused; scroll or click an action with modifiers held. Escape exits Live filter (Alt+V)')
        live_row.append(self.live_switch)
        make_switch_row(live_row, self.live_switch)
        self.live_switch.connect('notify::active', self.live_view_toggled)
        self.filter_bar.append(live_row)
        self.view_stack = Gtk.Stack(vexpand=True, vhomogeneous=False, hhomogeneous=False)
        target_label = Gtk.Label(label='Window for shortcut actions', xalign=0)
        action_tooltip(target_label, 'Choose which window receives window actions run from the shortcut list. Current uses the most recently focused other window on this workspace (Alt+W)')
        self.target_label = target_label
        options.append(target_label)
        self.target_model = Gtk.StringList.new(['Current'])
        self.target = Gtk.DropDown(model=self.target_model, hexpand=True)
        self.target.connect('notify::selected', self.target_changed)
        action_tooltip(self.target, 'Choose which window receives window actions run from the shortcut list. Current uses the most recently focused other window on this workspace (Alt+W)')
        options.append(self.target)
        self.appearance_row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.appearance_row.append(Gtk.Label(label='Appearance', xalign=0))
        self.look_picker = Gtk.DropDown.new_from_strings([value['name'] for value in LOOKS.values()])
        self.look_picker.set_selected(list(LOOKS).index(self.look))
        self.look_picker.connect('notify::selected', self.look_changed)
        self.appearance_row.append(self.look_picker)
        command_page.append(self.appearance_row)
        self.command_buttons = {}
        for label, callback in [('Features', self.show_features), ('Settings…', lambda: preferences.show(self)), ('Keyboard shortcuts', self.show_shortcuts), ('Manage shortcuts', self.show_management), ('Keyboard Guide', self.show_guide), ('Mouse gestures & controllers', lambda: __import__('input_controls').show(self)), ('Refresh shortcuts', self.refresh), ('About', self.show_info), ('Quit', self.quit_or_restart)]:
            button = Gtk.Button(label=label)
            button.get_child().set_xalign(0)
            self.command_buttons[label] = button
            hotkey = {'Features': 'Ctrl+Shift+P', 'Keyboard shortcuts': 'F1', 'Manage shortcuts': 'Ctrl+M', 'Settings…': 'Ctrl+,', 'Keyboard Guide': 'Ctrl+Shift+,', 'Refresh shortcuts': 'Ctrl+R', 'About': 'Ctrl+I'}.get(label, '')
            if callback == self.quit:
                action_tooltip(button, 'Close all Shortcuts windows and stop the background process. Closing a window normally keeps the app ready for instant reopening. The next launch starts it again. (Ctrl+Q)')
            elif hotkey:
                action_tooltip(button, f'{label} ({hotkey})')
            def clicked(_button, action=callback):
                restart = action == self.quit_or_restart and getattr(self, '_restart_menu_mode', False)
                popover.popdown()
                self.app_menu_button.popdown()
                if restart: self.restart()
                else: action()
            button.connect('clicked', clicked)
            if label == 'Features': command_page.insert_child_after(button, app_heading)
            else: command_page.append(button)
        self._restart_menu_mode = False
        menu_keys = Gtk.EventControllerKey()
        menu_keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        menu_keys.connect('modifiers', self.restart_modifiers_changed)
        menu_keys.connect('key-pressed', lambda _,key,code,state: self.restart_shift_key(key,True))
        menu_keys.connect('key-released', lambda _,key,code,state: self.restart_shift_key(key,False))
        app_popover.add_controller(menu_keys)
        def sync_restart_label(*_):
            self.stop_restart_watch()
            self.poll_restart_modifier()
            self._restart_watch = GLib.timeout_add(50, self.poll_restart_modifier)
        app_popover.connect('map',sync_restart_label)
        app_popover.connect('closed',lambda *_:self.stop_restart_watch())
        reset = Gtk.Button(label='Reset to Defaults…')
        reset.get_child().set_xalign(0)
        reset.set_tooltip_text('Review everything that will be cleared before resetting the app.')
        reset.connect('clicked', lambda *_: self.show_reset())
        command_page.append(reset)
        self.keyboard = KeyboardView(self.select_key, lambda: self.system_theme.colors, self.keyboard_preferences, self.save_keyboard_preferences,
                                     row_factory=self.shortcut_row, section_factory=ShortcutSection,
                                     item_state=lambda item: (item["id"] in self.favorites, item["id"] in self.learned))
        self.keyboard_notice = Gtk.Label(label='', xalign=0, wrap=True, visible=False)
        self.keyboard_notice.add_css_class('dim-label')
        root.append(self.keyboard_notice)
        scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.create_shortcut_list()
        scroll.set_child(self.list_box)
        self.list_scroll = scroll
        live_scroll = Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.VERTICAL)
        live_scroll.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        live_scroll.connect('scroll', self.live_scroll)
        scroll.add_controller(live_scroll)
        from native_style import ScrollScrim
        self.list_surface = ScrollScrim(scroll, lambda: self.system_theme.current_look == 'square',
                                        lambda: self.system_theme.menu_background())
        self.view_stack.add_titled(self.list_surface, 'list', 'List')
        keyboard_scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        keyboard_scroll.set_child(self.keyboard)
        self.keyboard_scroll = keyboard_scroll
        self.view_stack.add_titled(keyboard_scroll, 'keyboard', 'Live Keyboard')
        self.view_stack.set_visible_child_name('keyboard' if self.saved_view == 'keyboard' else 'list')
        self.view_stack.connect('notify::visible-child-name', self.view_changed)
        for label, field in (('Numpad', 'show_numpad'), ('Fit width', 'fit_width'), ('Raised keys', 'raised_keys')):
            setting = Gtk.Box(spacing=16)
            setting.append(Gtk.Label(label=label, xalign=0, hexpand=True))
            toggle = self.keyboard.option_buttons[field]
            setting.append(toggle)
            if label in ('Flat list', 'Columns'):
                action_tooltip(toggle, toggle.get_tooltip_text() + (' (Alt+G)' if label == 'Flat list' else ' (Alt+C)'))
            self.settings_switches[label] = toggle
            self.settings_rows[label] = setting
            make_switch_row(setting, toggle)
            options.prepend(setting)
        root.append(self.view_stack)
        self.status = Gtk.Label(label='Loading shortcuts…', xalign=0,
                                ellipsize=Pango.EllipsizeMode.END, lines=1)
        self.status.add_css_class('dim-label')
        self.status.add_css_class('main-status')
        root.append(self.status)
        self.restore_filters()
        self.search.connect('changed', self.search_changed)
        search_focus = Gtk.EventControllerFocus()
        search_focus.connect('leave', lambda *_: GLib.idle_add(self.history_focus_left))
        self.search.add_controller(search_focus)
        self.only_favorites.connect('toggled', self.filters_changed)
        self.learned_filter.connect('notify::selected', self.filters_changed)
        self.type_filter.connect('notify::selected', self.filters_changed)
        for dropdown in (self.source_picker, self.type_filter, self.learned_filter, self.target, self.look_picker):
            self.wire_choice(dropdown)
        if os.environ.get('GDK_BACKEND') != 'broadway':
            from agent_control import register
            register(self)
        if os.environ.get('BINDLUME_RESTART_FILE'):GLib.idle_add(self.restore_restart)
        startup_mark('widgets-ready')
        self.view_changed()
        self.apply_features()
        if not self.feature_enabled('guide'): self.sync_guide_feature(False)
        self.refresh_targets()
        startup_mark('targets-ready')
        def mapped(window):
            startup_mark('mapped')
            clock = window.get_frame_clock()
            handler = None
            def painted(*_):
                startup_mark('first-frame')
                clock.disconnect(handler)
            handler = clock.connect('after-paint', painted)
        self.window.connect('map', mapped)
        if not getattr(self, 'background_start', False): self.window.present()
        self.refresh()
        GLib.timeout_add_seconds(3, self.refresh_targets)
        self.source_timer = GLib.timeout_add_seconds(5, self.poll_source)
        GLib.timeout_add_seconds(1, self.initial_source_counts)
        GLib.timeout_add_seconds(30, self.refresh_source_counts)
        if not getattr(self, 'background_start', False): GLib.timeout_add(150, self.focus_search)

    def stop_restart_watch(self):
        if getattr(self,'_restart_watch',None):
            GLib.source_remove(self._restart_watch)
            self._restart_watch=None
        self.restart_modifiers_changed(None,0)

    def poll_restart_modifier(self):
        if not self.app_menu_button.get_popover().get_visible():
            self._restart_watch=None
            self.restart_modifiers_changed(None,0)
            return False
        keyboard=self.window.get_display().get_default_seat().get_keyboard()
        self.restart_modifiers_changed(None,keyboard.get_modifier_state() if keyboard else 0)
        return True

    def restart_modifiers_changed(self, _controller, state):
        self._restart_menu_mode = bool(state & Gdk.ModifierType.SHIFT_MASK)
        button=getattr(self,'command_buttons',{}).get('Quit')
        if button:
            import localization
            text='Restart' if self._restart_menu_mode else 'Quit'
            button.set_label(localization.text(text))
            button.get_child()._translation_source=text
            button.get_child().set_xalign(0)
            panel=getattr(self,'chat_panel',None)
            busy=bool(panel and (panel.run or panel.choosing))
            button.set_sensitive(not (self._restart_menu_mode and busy))
            button.set_tooltip_text(localization.text('Stop the response before restarting.' if self._restart_menu_mode and busy else 'Restart Bindlume and restore the chat draft.' if self._restart_menu_mode else 'Quit Bindlume. Hold Shift to restart.'))
        return False

    def restart_shift_key(self, key, pressed):
        if key in (Gdk.KEY_Shift_L,Gdk.KEY_Shift_R):
            self.restart_modifiers_changed(None,Gdk.ModifierType.SHIFT_MASK if pressed else 0)
        return False

    def quit_or_restart(self):
        if getattr(self,'_restart_menu_mode',False):self.restart()
        else:self.quit()

    def restart(self):
        panel=getattr(self,'chat_panel',None)
        if panel and (panel.run or panel.choosing):return
        import tempfile
        data={}
        if panel and self.main_pane.get_end_child():
            buffer=panel.input.get_buffer()
            data={'chat':True,'session':panel.session['id'] if panel.session else None,
                  'draft':buffer.get_text(buffer.get_start_iter(),buffer.get_end_iter(),True)}
        self.save_ui_state()
        with tempfile.NamedTemporaryFile(mode='w',prefix='bindlume-restart-',delete=False) as file:
            json.dump(data,file)
            self._restart_file=file.name
        self.quit()

    def restore_restart(self):
        path=os.environ.pop('BINDLUME_RESTART_FILE',None)
        if not path:return False
        try:data=json.loads(Path(path).read_text())
        finally:Path(path).unlink(missing_ok=True)
        if data.get('chat'):
            self.show_chat(True)
            if data.get('session'):
                try:self.chat_panel.open(data['session'])
                except (OSError,ValueError,KeyError):pass
            self.chat_panel.input.get_buffer().set_text(data.get('draft',''))
        return False

    def hide_main(self, *_):
        if getattr(self, 'chat_panel', None) and self.chat_panel.history_window: self.chat_panel.history_window.close()
        self.dismiss_choice()
        self.menu_button.popdown()
        for name in ('about_window', 'companion_window', 'info_window', 'guide_window', 'shortcuts_window', 'features_window', 'reset_window', 'source_library_window', 'preferences_window'):
            child = getattr(self, name, None)
            if child: child.close()
        self.window.set_visible(False)
        self.update_live_capture()
        if self.keyboard:
            self.keyboard.suppress_guide = False
            self.keyboard.set_live(False)
        return True

    def close_on_escape(self, _controller, keyval, _keycode, _state):
        panel = getattr(self, 'chat_panel', None)
        focus = self.window.get_focus()
        in_chat = panel is not None and focus is not None and focus.is_ancestor(panel)
        if in_chat and keyval == Gdk.KEY_Escape:
            self.show_chat(False)
            return True
        if not in_chat and self.live_list_active() and not self.menu_button.get_popover().get_visible() and not self.app_menu_button.get_popover().get_visible() and not (getattr(self, 'choice_popover', None) and self.choice_popover.get_visible()):
            if keyval == Gdk.KEY_Escape:
                self.live_switch.set_active(False)
            else:
                base_keyval = keyval
                event = _controller.get_current_event() if _controller else None
                if event:
                    translated = self.window.get_display().translate_key(_keycode, Gdk.ModifierType(0), event.get_layout())
                    if translated[0]: base_keyval = translated[1]
                self.live_key(_keycode, keyval, True, base_keyval)
            return True
        if os.environ.get('SHORTCUTS_PROFILE_SEARCH'):
            self._search_key_started = time.perf_counter()
        if keyval == Gdk.KEY_Escape:
            if getattr(self, 'history_popover', None) and self.history_popover.get_visible():
                self.history_popover.popdown()
                return True
            if self.dismiss_choice(): return True
            if self.app_menu_button.get_popover().get_visible():
                self.app_menu_button.popdown()
                return True
            if self.menu_button.get_popover().get_visible():
                self.menu_button.popdown()
                return True
            self.window.close()
            return True
        if getattr(self, 'history_popover', None) and self.history_popover.get_visible() and keyval in (Gdk.KEY_Up, Gdk.KEY_Down):
            focus = self.window.get_focus()
            buttons = getattr(self, 'history_buttons', [])
            index = buttons.index(focus) if focus in buttons else -1
            index += 1 if keyval == Gdk.KEY_Down else -1
            if index < 0: self.search.grab_focus()
            elif buttons: buttons[min(index, len(buttons)-1)].grab_focus()
            return True
        if not (_state & Gtk.accelerator_get_default_mod_mask()) and keyval in (Gdk.KEY_Up, Gdk.KEY_Down):
            if self.navigate_results(keyval): return True
        if not (_state & Gtk.accelerator_get_default_mod_mask()) and keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and self.view_stack.get_visible_child_name() == 'list':
            focus = self.window.get_focus()
            if focus == self.search or (focus and focus.is_ancestor(self.search)) or focus == self.list_box:
                self.activate_list_item(self.list_box, self.list_selection.get_selected())
                return True
        mask = Gtk.accelerator_get_default_mod_mask()
        for accelerator, _label, action in APP_SHORTCUTS:
            valid, key, mods = Gtk.accelerator_parse(accelerator)
            if valid and Gdk.keyval_to_lower(keyval) == key and (_state & mask) == mods:
                self.shortcut_action(action)
                return True
        return False

    def shortcut_action(self, action):
        if not self.action_enabled(action): return
        keyboard = self.view_stack.get_visible_child_name() == 'keyboard'
        managing = self.view_stack.get_visible_child_name() == 'manage'
        if action == 'chat': self.show_chat(self.main_pane.get_end_child() is None)
        elif action == 'chat_history':
            self.show_chat()
            self.chat_panel.history()
        elif action == 'features': self.show_features()
        elif action == 'manage': self.show_management()
        elif action == 'manage_apply':
            if managing and not self.manager_panel.busy: self.manager_panel.assign()
        elif action == 'quit': self.quit()
        elif action == 'back':
            if managing: self.close_management()
        elif action in ('filters', 'flat', 'columns'):
            if self.view_stack.get_visible_child_name() == 'list':
                button = self.settings_switches[{'filters':'Show filters', 'flat':'Flat list', 'columns':'Columns'}[action]]
                button.set_active(not button.get_active())
        elif action == 'live':
            if not keyboard and not managing: self.live_switch.set_active(not self.live_switch.get_active())
        elif action == 'overlay':
            if keyboard:
                button = self.keyboard.option_buttons['key_overlay']
                button.set_active(not button.get_active())
        elif action in ('bookmark_row', 'learn_row'):
            if self.view_stack.get_visible_child_name() == 'list':
                selected = self.list_selection.get_selected_item()
                item = selected.data.get('item') if selected else None
                if item:
                    (self.favorite if action == 'bookmark_row' else self.toggle_learned)(item)
        elif action == 'help': self.show_shortcuts()
        elif action == 'view': self.view_toggle.set_active(not self.view_toggle.get_active())
        elif action == 'favorites': self.only_favorites.set_active(not self.only_favorites.get_active())
        elif action == 'search':
            if managing:
                self.manager_panel.action.grab_focus()
                return
            self.search.grab_focus()
            self.search.select_region(0, -1)
        elif action in ('expand', 'collapse'):
            if not keyboard: self.set_all_expanded(action == 'expand')
        elif action == 'refresh':
            if managing: self.manager_panel.refresh()
            else: self.refresh()
        elif action == 'source':
            favorites = [source for source in SOURCES if source in self.favorite_sources and self.source_available(source)]
            if favorites:
                index = favorites.index(self.source_name) if self.source_name in favorites else -1
                self.source_picker.set_selected(SOURCES.index(favorites[(index + 1) % len(favorites)]))
            else:
                self.status.set_text('Bookmark sources in the source menu to cycle them with Alt+S.')
        elif action == 'source_sets': source_library.show(self)
        elif action == 'source_menu': self.open_choice(self.source_picker)
        elif action in ('menu', 'commands'):
            self.dismiss_choice()
            selected = self.app_menu_button if action == 'commands' else self.menu_button
            other = self.menu_button if action == 'commands' else self.app_menu_button
            other.popdown()
            if selected.get_popover().get_visible(): selected.popdown()
            else: selected.popup()
        elif action == 'preferences': preferences.show(self)
        elif action == 'guide': self.show_guide()
        elif action == 'info': self.show_info()
        elif action in ('type', 'learned', 'target'):
            self.open_choice({'type': self.type_filter, 'learned': self.learned_filter, 'target': self.target}[action])
        elif action == 'clear':
            self.search.set_text('')
            self.only_favorites.set_active(False)
            self.type_filter.set_selected(0)
            self.learned_filter.set_selected(0)
            self.keyboard_filter = None
            self.update_keyboard_notice()
            self.filters_changed()
        elif keyboard and action in ('numpad', 'fit'):
            button = self.keyboard.option_buttons['show_numpad' if action == 'numpad' else 'fit_width']
            button.set_active(not button.get_active())
        elif action == 'layers':
            button = self.keyboard.all_button
            button.set_active(not button.get_active())

    def wire_menu_toggle(self, button, action):
        # Nested popovers can leave MenuButton's internal active state out of
        # sync. Decide from the visible popup and consume the complete click.
        click = Gtk.GestureClick(button=1)
        click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        def pressed(gesture, _count, x, y):
            if 0 <= x < button.get_width() and 0 <= y < button.get_height():
                gesture.set_state(Gtk.EventSequenceState.CLAIMED)
                self.shortcut_action(action)
        click.connect('pressed', pressed)
        button.add_controller(click)

    def dismiss_choice(self):
        popover = getattr(self, 'choice_popover', None)
        if popover and popover.get_visible():
            popover.popdown()
            return True
        return False

    def wire_choice(self, dropdown):
        # Use the same focused overlay for pointer activation and hotkeys.
        click = Gtk.GestureClick(button=1)
        click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        def pressed(gesture, _count, x, y):
            if not (0 <= x < dropdown.get_width() and 0 <= y < dropdown.get_height()):
                return
            # Always claim activation: letting GTK's native DropDown handle a
            # second click creates a competing modal popup/grab.
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)
            if getattr(self, '_choice_dropdown', None) == dropdown and self.dismiss_choice():
                return
            self.open_choice(dropdown, from_control=True)
        click.connect('pressed', pressed)
        dropdown.add_controller(click)
        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        def key_pressed(_controller, key, *_):
            if key in (Gdk.KEY_space, Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_Down):
                if getattr(self, '_choice_dropdown', None) == dropdown and self.dismiss_choice():
                    return True
                self.open_choice(dropdown, from_control=True)
                return True
            return False
        keys.connect('key-pressed', key_pressed)
        dropdown.add_controller(keys)

    def open_choice(self, dropdown, from_control=False):
        # Hotkeys open a direct overlay, even for controls inside Settings.
        self.dismiss_choice()
        if not from_control:
            self.menu_button.popdown()
            self.app_menu_button.popdown()
        old = getattr(self, 'choice_popover', None)
        if old:
            old.unparent()
        popover = Gtk.Popover()
        self.choice_popover = popover
        self._choice_dropdown = dropdown
        fallback = self.menu_button if self.menu_button.get_visible() else self.app_menu_button
        anchor = dropdown if dropdown.get_mapped() else fallback
        owner = next((button for button in (self.menu_button, self.app_menu_button)
                      if anchor.is_ancestor(button.get_popover())), None)
        popover.set_parent(anchor)
        def choice_closed(*_):
            def release_popup():
                if not popover.get_visible() and popover.get_parent():
                    popover.unparent()
                    # Reacquire the outer Wayland popup grab after its nested
                    # popup closes; GTK otherwise leaves a visible inert menu.
                    if owner and owner.get_popover().get_visible():
                        owner.popdown()
                        owner.popup()
                return False
            GLib.idle_add(release_popup)
        popover.connect('closed', choice_closed)
        choices = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        choices.add_css_class('choice-menu')
        model = dropdown.get_model()
        visible_rows = []
        for index in range(model.get_n_items()):
            if dropdown == self.source_picker and not self.source_available(model.get_item(index).get_string()):
                continue
            row = Gtk.ListBoxRow()
            visible_rows.append(row)
            row.choice_index = index
            box = Gtk.Box(spacing=14, margin_top=3, margin_bottom=3, margin_start=6, margin_end=6)
            label = model.get_item(index).get_string()
            box.append(Gtk.Label(label=label, xalign=0, hexpand=True))
            if dropdown == self.source_picker:
                count = self.source_counts.get(label)
                badge = Gtk.Label(label=str(count) if count is not None else '—')
                badge.add_css_class('count-badge')
                badge.set_valign(Gtk.Align.CENTER)
                box.append(badge)
                star = Gtk.Button(label='★' if label in self.favorite_sources else '☆')
                star.add_css_class('flat')
                star.set_valign(Gtk.Align.CENTER)
                star.set_visible(self.feature_enabled('bookmarks'))
                def bookmark(button, source=label):
                    if source in self.favorite_sources: self.favorite_sources.remove(source)
                    else: self.favorite_sources.add(source)
                    button.set_label('★' if source in self.favorite_sources else '☆')
                    self.save_ui_state()
                star.connect('clicked', bookmark)
                star.set_tooltip_text('Bookmark this source for Alt+S')
                box.append(star)
            check = Gtk.Image(icon_name='object-select-symbolic', valign=Gtk.Align.CENTER)
            check.set_opacity(1 if index == dropdown.get_selected() else 0)
            if dropdown == self.source_picker:
                box.insert_child_after(check, box.get_first_child())
            else:
                box.append(check)
            row.set_child(box)
            choices.append(row)
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,
                                    max_content_height=340, propagate_natural_height=True)
        scroll.set_child(choices)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        content.append(scroll)
        if dropdown == self.source_picker:
            content.append(Gtk.Separator())
            browse = Gtk.Button(label='Choose shortcut sets…')
            browse.add_css_class('flat')
            browse.get_child().set_xalign(0)
            browse.connect('clicked', lambda *_: source_library.show(self))
            content.append(browse)
        popover.set_child(content)
        localization.translate_tree(popover)
        def chosen(_list, row):
            dropdown.set_selected(row.choice_index)
            popover.popdown()
        choices.connect('row-activated', chosen)
        def keys(_controller, key, *_):
            if key == Gdk.KEY_Escape:
                popover.popdown()
                return True
            if key in (Gdk.KEY_Up, Gdk.KEY_Down, Gdk.KEY_Home, Gdk.KEY_End):
                targets = visible_rows + ([browse] if dropdown == self.source_picker else [])
                if not targets:return True
                focus = self.window.get_focus()
                current = next((i for i,target in enumerate(targets) if focus is target or (focus and focus.is_ancestor(target))), None)
                if current is None:
                    row=choices.get_selected_row()
                    current=targets.index(row) if row in targets else 0
                index = 0 if key == Gdk.KEY_Home else len(targets)-1 if key == Gdk.KEY_End else (current+(1 if key==Gdk.KEY_Down else -1))%len(targets)
                target=targets[index]
                if isinstance(target,Gtk.ListBoxRow):choices.select_row(target)
                else:choices.unselect_all()
                target.grab_focus()
                return True
            if key in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
                if dropdown == self.source_picker and self.window.get_focus() == browse:
                    browse.emit('clicked')
                    return True
                row = choices.get_selected_row()
                if row: chosen(choices, row)
                return True
            return False
        controller = Gtk.EventControllerKey()
        controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        controller.connect('key-pressed', keys)
        popover.add_controller(controller)
        self.choice_list = choices
        self.choice_key_handler = keys
        def focus_current(*_):
            row = next((row for row in visible_rows if row.choice_index == dropdown.get_selected()), visible_rows[0] if visible_rows else None)
            if row:
                choices.select_row(row)
                row.grab_focus()
            elif dropdown == self.source_picker:
                browse.grab_focus()
        popover.connect('map', focus_current)
        popover.popup()

    def show_shortcuts(self):
        if getattr(self, 'shortcuts_window', None):
            self.shortcuts_window.present()
            return
        window = Gtk.Window(title='App Shortcuts', transient_for=self.window,
                            application=self, modal=True, default_width=900, default_height=560)
        self.shortcuts_window = window
        window.connect('close-request', self.shortcuts_closed)
        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        def close(_controller, keyval, *_):
            if keyval in (Gdk.KEY_Escape, Gdk.KEY_F1):
                window.close()
                return True
            return False
        keys.connect('key-pressed', close)
        window.add_controller(keys)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                      margin_top=18, margin_bottom=18, margin_start=18, margin_end=18)
        header = Gtk.Box(spacing=12)
        title = Gtk.Label(label='App shortcuts', xalign=0, hexpand=True)
        title.add_css_class('title-2')
        header.append(title)
        button = Gtk.Button(icon_name='window-close-symbolic')
        action_tooltip(button, 'Close (Esc)')
        button.connect('clicked', lambda *_: window.close())
        header.append(button)
        box.append(header)
        box.append(Gtk.Label(label='Available while the main window is focused.', xalign=0))
        scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        columns = Gtk.Box(spacing=28, homogeneous=True)
        groups = [
            ('Navigation', ['help', 'search', 'view', 'source', 'source_menu', 'source_sets', 'back']),
            ('Filters', ['menu', 'favorites', 'clear', 'type', 'learned', 'target']),
            ('List', ['expand', 'collapse', 'filters', 'flat', 'columns', 'bookmark_row', 'learn_row']),
            ('Keyboard', ['numpad', 'fit', 'layers', 'overlay']),
            ('Agent chat', ['chat','chat_history']),
            ('App', ['features', 'commands', 'preferences', 'manage', 'manage_apply', 'refresh', 'guide', 'info', 'quit']),
        ]
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20, hexpand=True)
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20, hexpand=True)
        columns.append(left)
        columns.append(right)
        def add_group(parent, title, rows):
            if not rows: return
            group = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            heading = Gtk.Label(label=title, xalign=0)
            heading.add_css_class('heading')
            group.append(heading)
            grid = Gtk.Grid(column_spacing=12, row_spacing=10)
            for row, (shortcut, label) in enumerate(rows):
                grid.attach(Gtk.Label(label=label, xalign=0, hexpand=True, wrap=True), 0, row, 1, 1)
                key_label = hotkey_caps(shortcut)
                key_label.set_tooltip_text(shortcut)
                grid.attach(key_label, 1, row, 1, 1)
            group.append(grid)
            parent.append(group)
        for index, (title, actions) in enumerate(groups):
            rows = [(Gtk.accelerator_get_label(*Gtk.accelerator_parse(a)[1:]), label)
                    for selected in actions for a, label, action in APP_SHORTCUTS if action == selected and self.action_enabled(action)]
            add_group(left if index < 3 else right, title, rows)
        add_group(right, 'Controls & windows', [
            ('Esc', 'Close current window'),
            ('Tab / Shift+Tab', 'Move between controls'),
            ('Space / Enter', 'Activate focused control'),
            ('Arrow keys', 'Navigate options'),
        ])
        add_group(right, 'Developer tools', [('Ctrl+Shift+D', 'Open GTK Inspector'), ('Ctrl+Shift+I', 'Inspect a widget')])
        scroll.set_child(columns)
        box.append(scroll)
        window.set_child(box)
        window.present()

    def shortcuts_closed(self, *_):
        self.shortcuts_window = None
        return False

    def toggle_view(self, button):
        self.view_stack.set_visible_child_name('keyboard' if button.get_active() else 'list')

    def view_changed(self, *_):
        is_keyboard = self.view_stack.get_visible_child_name() == 'keyboard'
        is_managing = self.view_stack.get_visible_child_name() == 'manage'
        self.management_back.set_visible(is_managing)
        for control in (self.search, self.only_favorites, self.source_picker, self.status):
            control.set_visible(not is_managing)
        self.keyboard.suppress_guide = (is_keyboard or self.live_list_active()) and self.window.get_visible()
        if is_managing:
            self.update_live_capture()
            self.keyboard.set_live(False)
            self.list_controls.set_visible(False)
            self.filter_bar.set_visible(False)
            for row in self.settings_rows.values(): row.set_visible(False)
            return
        self.keyboard.set_live(is_keyboard and self.window.is_active())
        self.update_live_capture()
        self.list_controls.set_visible(not is_keyboard and not self.flat_list)
        for label in ('Show filters', 'Flat list', 'Columns'):
            self.settings_rows[label].set_visible(not is_keyboard)
        for label in ('Numpad', 'Fit width', 'Raised keys'):
            self.settings_rows[label].set_visible(is_keyboard)
        self.view_toggle.set_active(is_keyboard)
        self.view_toggle.set_icon_name('view-list-symbolic' if is_keyboard else 'input-keyboard-symbolic')
        action_tooltip(self.view_toggle, 'Switch to list view (Ctrl+K)' if is_keyboard else 'Switch to keyboard view (Ctrl+K)')
        destination = self.keyboard.toolbar if is_keyboard else self.filter_bar
        # Share the actual controls, keeping their state and behavior identical.
        for control in (self.keyboard.modifier_group, self.keyboard.layer_control):
            parent = control.get_parent()
            if parent != destination:
                if parent: parent.remove(control)
                destination.prepend(control)

        parent = self.type_filter.get_parent()
        if parent != destination:
            if parent: parent.remove(self.type_filter)
            destination.append(self.type_filter)
        self.type_filter.set_hexpand(is_keyboard)
        self.type_filter.set_halign(Gtk.Align.END if is_keyboard else Gtk.Align.START)
        self.filter_bar.set_visible(not is_keyboard and self.show_list_filters)
        if hasattr(self, 'command_buttons'): self.apply_feature_visibility()
        self.saved_view = 'keyboard' if is_keyboard else 'list'
        self.save_ui_state()
        if hasattr(self, 'list_box'): self.render()

    def list_filters_toggled(self, button, *_):
        self.show_list_filters = button.get_active()
        self.filter_bar.set_visible(self.show_list_filters and self.view_stack.get_visible_child_name() == 'list')
        self.save_ui_state()

    def feature_enabled(self, key):
        return self.features.get(key, False)

    def action_enabled(self, action):
        if action == 'favorites' and hasattr(self, 'only_favorites'): return self.only_favorites.get_visible()
        if action == 'learned' and hasattr(self, 'visibility_label'): return self.visibility_label.get_visible()
        if action == 'menu' and hasattr(self, 'menu_button'): return self.menu_button.get_visible()
        if action in ('type', 'layers'): return self.feature_enabled('layouts') or self.feature_enabled('keyboard')
        feature = ACTION_FEATURES.get(action)
        return feature is None or self.feature_enabled(feature)

    def show_features(self):
        self.menu_button.popdown()
        self.app_menu_button.popdown()
        existing = getattr(self, 'features_window', None)
        if existing:
            existing.present()
            return
        self.features_window = gallery(self)
        self.features_window.connect('close-request', lambda *_: setattr(self, 'features_window', None) or False)
        self.features_window.present()

    def set_feature(self, key, enabled):
        self.features[key] = enabled
        if key == 'guide': self.sync_guide_feature(enabled)
        self.apply_features()
        self.save_ui_state()
        if getattr(self, 'shortcuts_window', None): self.shortcuts_window.close()

    def sync_guide_feature(self, enabled):
        if not enabled and not shutil.which('omarchy-shell'): return
        # Serialize quick successive changes; a slow backend must not freeze GTK.
        if not hasattr(self, '_guide_executor'):
            from concurrent.futures import ThreadPoolExecutor
            self._guide_executor = ThreadPoolExecutor(max_workers=1)
        def update():
            try: GuideController().patch(enabled=enabled)
            except (OSError, RuntimeError, subprocess.SubprocessError) as error:
                GLib.idle_add(self.status.set_text, 'Keyboard guide: ' + str(error))
        self._guide_executor.submit(update)

    def set_preference(self, key, value):
        self.preferences[key] = value
        self.system_theme.set_preferences(self.preferences)
        if key == 'language':
            localization.set_language(self, value)
            def update_guide():
                try: GuideController().patch(language=localization.resolve_language(value))
                except (OSError, RuntimeError): pass
            threading.Thread(target=update_guide, daemon=True).start()
        self.save_ui_state()
        if key == 'window_animations': self.sync_window_animations()
        if hasattr(self, 'row_cache'):
            self.row_cache.clear()
            self.list_model.remove_all()
        self.render()

    def look_changed(self, *_):
        self.look = list(LOOKS)[self.look_picker.get_selected()]
        self.system_theme.set_look(self.look if self.feature_enabled('appearance') else 'system')
        self.system_theme.set_preferences(self.preferences)
        self.save_ui_state()

    def chat_split_changed(self, pane, *_):
        if getattr(self, '_restoring_chat_split', False) or pane.get_end_child() is None:return
        width=pane.get_width()
        if width <= 0:return
        self.chat_split_ratio=max(.2,min(.8,pane.get_position()/width))
        self.save_ui_state()

    def show_chat(self, visible=True):
        if visible and not self.feature_enabled('agent'): return
        if not visible:
            if getattr(self, 'chat_panel', None) and self.chat_panel.history_window:
                self.chat_panel.history_window.close()
            self.main_pane.set_end_child(None)
            if hasattr(self, '_before_chat_size'):
                self.window.set_default_size(*self._before_chat_size)
                del self._before_chat_size
            self.render()
            self.search.grab_focus()
            return
        self.app_menu_button.popdown()
        self.menu_button.popdown()
        if self.chat_panel is None:
            from chat_view import ChatPanel
            self.chat_panel = ChatPanel(self, UI_STATE.parent)
        if self.main_pane.get_end_child() is None:
            default_width, default_height = self.window.get_default_size()
            width = self.window.get_width() or default_width
            height = self.window.get_height() or default_height
            self._before_chat_size = (width, height)
            self.main_pane.set_end_child(self.chat_panel)
            available = width + 400
            available_height = max(height, 500)
            surface = self.window.get_surface()
            if surface:
                monitor = self.window.get_display().get_monitor_at_surface(surface)
                if monitor:
                    available = min(available, monitor.get_geometry().width - 40)
                    available_height = min(available_height, monitor.get_geometry().height - 40)
            if self.overlay_surfaces is not None:
                bounds = self.overlay_surfaces.available_bounds(self.window)
                available = min(available, bounds[0] - 40)
                available_height = min(available_height, bounds[1] - 40)
            self.window.set_default_size(max(1, available), max(1, available_height))
            self._restoring_chat_split = True
            self.main_pane.set_position(round(available * self.chat_split_ratio))
            def restored():
                self._restoring_chat_split = False
                return False
            GLib.timeout_add(250, restored)
            self.render()
        self.chat_panel.input.grab_focus()

    def apply_feature_visibility(self):
        self.chat_button.set_visible(self.feature_enabled('agent'))
        if not self.feature_enabled('agent') and self.main_pane.get_end_child(): self.show_chat(False)
        self.appearance_row.set_visible(False)
        managing = self.view_stack.get_visible_child_name() == 'manage'
        keyboard = self.view_stack.get_visible_child_name() == 'keyboard'
        ids = {item['id'] for item in self.items}
        has_favorites = bool(self.favorites & ids)
        has_hidden = self.feature_enabled('hidden') and bool(self.learned & ids)
        self.view_heading.set_visible(has_hidden or self.feature_enabled('target') or (not keyboard and self.feature_enabled('layouts')))
        self.only_favorites.set_visible(self.feature_enabled('bookmarks') and has_favorites and not managing)
        self.view_toggle.set_visible(self.feature_enabled('keyboard') and not managing)
        self.visibility_label.set_visible(has_hidden)
        self.learned_filter.set_visible(has_hidden)
        self.target_label.set_visible(self.feature_enabled('target'))
        self.target.set_visible(self.feature_enabled('target'))
        for label, feature in (('Manage shortcuts','manage'), ('Keyboard Guide','guide'), ('Mouse gestures & controllers','inputs')):
            self.command_buttons[label].set_visible(self.feature_enabled(feature))
        for label in ('Show filters','Flat list','Columns'):
            self.settings_rows[label].set_visible(not keyboard and not managing and self.feature_enabled('layouts'))
        self.live_switch.get_parent().set_visible(self.feature_enabled('live'))
        self.list_controls.set_visible(not managing and not keyboard and not self.flat_list and self.feature_enabled('layouts'))
        self.menu_button.set_visible(not managing and (keyboard or self.feature_enabled('layouts') or self.feature_enabled('target') or has_hidden))
        self.filter_bar.set_visible(not managing and not keyboard and (self.show_list_filters or (self.feature_enabled('live') and not self.feature_enabled('layouts'))))
        self.keyboard.indicator_features = (self.feature_enabled('bookmarks'), self.feature_enabled('hidden'))

    def update_window_size(self):
        compact = not any(enabled for name, enabled in self.features.items()
                          if name not in ('history', 'animations', 'agent'))
        if compact != getattr(self, '_compact_window', None):
            self._compact_window = compact
            if not self.window.get_mapped(): self.window.set_default_size(800, 650 if compact else 760)

    def apply_features(self):
        self.system_theme.set_look(self.look if self.feature_enabled('appearance') else 'system')
        self.system_theme.set_preferences(self.preferences)
        self.update_window_size()
        self.sync_window_animations()
        if not self.feature_enabled('bookmarks'): self.only_favorites.set_active(False)
        if not self.feature_enabled('hidden'): self.learned_filter.set_selected(0)
        if not self.feature_enabled('target'):
            self.target.set_selected(0)
            self.saved_target = None
        if not self.feature_enabled('live'): self.live_switch.set_active(False)
        if not self.feature_enabled('keyboard') and self.view_stack.get_visible_child_name() == 'keyboard':
            self.view_toggle.set_active(False)
        if not self.feature_enabled('manage') and self.view_stack.get_visible_child_name() == 'manage':
            self.view_stack.set_visible_child_name('list')
        if not self.feature_enabled('layouts'):
            self.settings_switches['Show filters'].set_active(False)
            self.settings_switches['Flat list'].set_active(True)
            self.settings_switches['Columns'].set_active(True)
            self.type_filter.set_selected(0)
            for button in self.keyboard.buttons.values(): button.set_active(False)
            self.keyboard.all_button.set_active(True)
        if not self.feature_enabled('history') and getattr(self, 'history_popover', None):
            self.history_popover.popdown()
        self.apply_feature_visibility()
        self.list_model.remove_all()
        self.render()

    def history_focus_left(self):
        popup = getattr(self, 'history_popover', None)
        focus = self.window.get_focus()
        if popup and not (focus and (focus.is_ancestor(popup) or focus.is_ancestor(self.search))): popup.popdown()
        return False

    def remember_search(self):
        if self.history_timer: GLib.source_remove(self.history_timer)
        self.history_timer = None
        if not self.feature_enabled('history'): return False
        query = self.search.get_text().strip()
        if query:
            self.search_history = [query] + [q for q in self.search_history if q.casefold() != query.casefold()]
            self.search_history = self.search_history[:20]
            self.save_ui_state()
        return False

    def update_history_suggestions(self):
        if self.history_timer:
            GLib.source_remove(self.history_timer)
            self.history_timer = None
        if not self.feature_enabled('history'): return
        if not hasattr(self, 'history_popover'):
            self.history_popover = Gtk.Popover(autohide=False, has_arrow=False)
            self.history_popover.set_parent(self.search)
            self.history_popover.set_halign(Gtk.Align.START)
        query = self.search.get_text().strip()
        options = [q for q in self.search_history if query.casefold() in q.casefold() and q.casefold() != query.casefold()][:6]
        def remember():
            self.history_timer = None
            return self.remember_search()
        self.history_timer = GLib.timeout_add(1200, remember)
        if not query or not options or self.live_list_active():
            self.history_popover.popdown()
            return
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        heading = Gtk.Label(label='Recent searches', xalign=0, margin_start=10, margin_top=6, margin_bottom=4)
        heading.add_css_class('dim-label')
        box.append(heading)
        self.history_buttons = []
        for value in options:
            button = Gtk.Button(label=value, halign=Gtk.Align.FILL)
            button.add_css_class('flat')
            def chosen(_button, text=value):
                self.search.set_text(text)
                self.search.set_position(-1)
                self.history_popover.popdown()
                self.search.grab_focus()
            button.connect('clicked', chosen)
            box.append(button)
            self.history_buttons.append(button)
        self.history_popover.set_child(box)
        self.history_popover.popup()

    def reset_changes(self):
        items = {r['id']: r['name'] for r in self.items}
        changes = []
        def add(key, title, entries, note=''):
            if entries:
                changes.append((key, title, len(entries), '\n'.join(entries) + ('\n\n' + note if note else '')))
        add('bookmarks', 'Bookmarks', [items.get(key, key) for key in sorted(self.favorites)])
        add('hidden', 'Hidden shortcuts', [items.get(key, key) for key in sorted(self.learned)])
        add('sources', 'Source bookmarks', sorted(self.favorite_sources))
        add('source_selection', 'Disabled shortcut sets', sorted(self.disabled_sources))
        add('history', 'Recent searches', self.search_history)
        add('features', 'Features', [FEATURES[key][0] + (' → off' if not DEFAULT_FEATURES[key] else ' → on') for key in FEATURES if self.features[key] != DEFAULT_FEATURES[key]],
            'Disabling features also restores their active filters and view options to defaults. Keyboard guide will be disabled; its appearance and desktop bindings are retained.')
        filters = []
        if self.search.get_text(): filters.append('Search: ' + self.search.get_text() + ' → empty')
        if self.only_favorites.get_active(): filters.append('Bookmarks only → off')
        if self.learned_filter.get_selected(): filters.append('Visibility → show all')
        if self.type_filter.get_selected(): filters.append('Shortcut type → all types')
        if self.live_view: filters.append('Live filter → off')
        if self.keyboard.manual: filters.append('Modifiers: ' + ', '.join(sorted(self.keyboard.manual)) + ' → none')
        if not self.keyboard.all_layers: filters.append('All layers → on')
        if self.keyboard_filter: filters.append('Selected keyboard key → none')
        for group in self.expanded_groups: filters.append('Category expansion: ' + group + ' → default')
        add('filters', 'Search and filters', filters)
        keyboard = []
        for field, title, default in [('raised_keys','Raised keys',False), ('show_numpad','Numpad',False), ('fit_width','Fit width',False), ('key_overlay','Key overlay',False), ('extras_expanded','Extra keys expanded',False), ('extras_layout','Extra-key layout','grid')]:
            value = getattr(self.keyboard, field)
            if value != default: keyboard.append(f'{title}: {value} → {default}')
        add('keyboard', 'Keyboard display', keyboard)
        preferences = []
        for changed, text in [
            (self.saved_view != 'list', f'View: {self.saved_view} → list'),
            (not self.flat_list, 'Flat list → on'), (not self.columns, 'Columns → on'),
            (self.source_name != 'Omarchy', f'Source: {self.source_name} → Omarchy'),
            (self.show_list_filters, 'Show filters → off'),
            (self.target.get_selected() != 0 or self.saved_target is not None, 'Target window → Current')]:
            if changed: preferences.append(text)
        for key, value in self.feature_view.items():
            if value is not True: preferences.append(f'Features {key} → on')
        if self.look != 'system': preferences.append('Style → System')
        for key, value in self.preferences.items():
            if key != 'global_hotkey' and value != __import__('preferences').DEFAULTS.get(key):
                label = key.replace('_', ' ').capitalize()
                preferences.append(f'{label}: {value} → {__import__("preferences").DEFAULTS.get(key)}')
        add('preferences', 'View and app', preferences)
        return changes

    def show_reset(self):
        self.app_menu_button.popdown()
        window = Gtk.Window(application=self, transient_for=self.window, modal=True,
                            title='Reset to Defaults', default_width=760, default_height=620)
        window.add_css_class('shortcuts-app')
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14,
                       margin_top=20, margin_bottom=20, margin_start=20, margin_end=20)
        heading = Gtk.Label(label='Review what will change', xalign=0)
        heading.add_css_class('title-2')
        body.append(heading)
        body.append(Gtk.Label(label='Choose what to reset. Unselected data stays as it is. Your desktop shortcut bindings will not be changed.', xalign=0, wrap=True))
        locations = Gtk.Expander(label='Configuration files')
        locations.add_css_class('config-files')
        config_root = STATE.parent
        directory = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        base = Gtk.Label(label=str(config_root).replace(str(Path.home()), '~', 1), xalign=0, selectable=True)
        base.add_css_class('config-path')
        directory.append(base)
        paths = Gtk.Grid(column_spacing=16, row_spacing=10, hexpand=True)
        for index, (title, path) in enumerate([
            ('Preferences & searches', UI_STATE), ('Bookmarks', STATE),
            ('Hidden shortcuts', LEARNED_STATE),
            ('Keyboard guide', config_root / 'keyboard-guide.json'),
            ('Custom shortcut sets', shortcut_sets.user_directory()),
            ('Conversations', config_root / 'chats'),
            ('Agent usage cache', config_root / 'agent-usage.json'),
            ('User memory', config_root / 'user-memory.md'),
        ]):
            paths.attach(Gtk.Label(label=title, xalign=0), 0, index, 1, 1)
            file_row = Gtk.Box(spacing=8)
            icon = 'folder-symbolic' if path.is_dir() or path.name in ('shortcut-sets', 'chats') else (
                   'application-json-symbolic' if path.suffix == '.json' else 'text-x-generic-symbolic')
            file_row.append(Gtk.Image.new_from_gicon(Gio.content_type_get_symbolic_icon('application/json')) if path.suffix == '.json' else Gtk.Image(icon_name=icon))
            label = Gtk.Label(label=path.name, xalign=0, selectable=True)
            label.add_css_class('config-path')
            file_row.append(label)
            symlink = path.is_symlink() or any(parent.is_symlink() for parent in path.parents)
            if symlink:
                link = Gtk.Image(icon_name='emblem-symbolic-link')
                link.set_tooltip_text('Symbolic link → ' + str(path.resolve()))
                file_row.append(link)
            file_row.set_tooltip_text(str(path) + (' → ' + str(path.resolve()) if symlink else ''))
            paths.attach(file_row, 1, index, 1, 1)
        directory.append(paths)
        locations.set_child(directory)
        body.append(locations)
        categories = self.reset_changes()
        if not categories: window.set_default_size(760, 280)
        master_row = Gtk.Box(spacing=12)
        master = Gtk.Switch(active=True, valign=Gtk.Align.CENTER)
        master.set_tooltip_text('Select or deselect every reset category. Nothing changes until you confirm.')
        master_row.append(master)
        master_row.append(Gtk.Label(label='Clear all', xalign=0, hexpand=True))
        make_switch_row(master_row, master)
        body.append(master_row)
        panes = Gtk.Box(spacing=20, vexpand=True)
        rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        category_scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=False, hscrollbar_policy=Gtk.PolicyType.NEVER)
        category_scroll.set_child(rows)
        panes.append(category_scroll)
        panes.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        preview = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, hexpand=True)
        preview_title = Gtk.Label(label='Hover a category to review it', xalign=0, wrap=True)
        preview_title.add_css_class('heading')
        preview_state = Gtk.Label(xalign=0, wrap=True)
        preview_state.add_css_class('dim-label')
        description = Gtk.Label(xalign=0, yalign=0, wrap=True, selectable=True, max_width_chars=45)
        preview_scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        preview_scroll.set_child(description)
        preview.append(preview_title)
        preview.append(preview_state)
        preview.append(preview_scroll)
        panes.append(preview)
        switches = {}
        reset_rows = {}
        current = None
        def show_preview(key):
            nonlocal current
            current = key
            _, title, count, detail = next(entry for entry in categories if entry[0] == key)
            preview_title.set_text(f'{localization.text(title)} · {count}')
            preview_state.set_text('Will be cleared or restored to defaults.' if switches[key].get_active() else 'Kept unchanged.')
            description.set_text(detail)
            preview_scroll.get_vadjustment().set_value(0)
        label_widths = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL)
        badge_widths = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL)
        for key, title, count, detail in categories:
            row = Gtk.Box(spacing=10)
            label = Gtk.Label(label=title, xalign=0)
            label_widths.add_widget(label)
            row.append(label)
            badge = Gtk.Label(label=str(count), valign=Gtk.Align.CENTER)
            badge.add_css_class('count-badge')
            badge_widths.add_widget(badge)
            row.append(badge)
            toggle = Gtk.Switch(active=True, valign=Gtk.Align.CENTER)
            row.prepend(toggle)
            make_switch_row(row, toggle)
            motion = Gtk.EventControllerMotion()
            motion.connect('enter', lambda *_, selected=key: show_preview(selected))
            row.add_controller(motion)
            focus = Gtk.EventControllerFocus()
            focus.connect('enter', lambda *_, selected=key: show_preview(selected))
            row.add_controller(focus)
            rows.append(row)
            switches[key] = toggle
            reset_rows[key] = row
        master_row.set_visible(bool(categories))
        panes.set_visible(bool(categories))
        body.append(panes)
        if not categories: body.append(Gtk.Label(label='Nothing to reset. Your app is already at its defaults.', wrap=True, vexpand=True))
        controls = Gtk.Box(spacing=10, halign=Gtk.Align.END)
        cancel = Gtk.Button(label='Cancel' if categories else 'Close')
        cancel.connect('clicked', lambda *_: window.close())
        confirm = Gtk.Button(label='Reset selected')
        confirm.set_visible(bool(categories))
        confirm.add_css_class('destructive-action')
        syncing = False
        def selection_changed(*_):
            nonlocal syncing
            if syncing: return
            syncing = True
            master.set_active(bool(switches) and all(toggle.get_active() for toggle in switches.values()))
            if current: show_preview(current)
            confirm.set_sensitive(any(toggle.get_active() for toggle in switches.values()))
            syncing = False
        def all_changed(*_):
            nonlocal syncing
            if syncing: return
            syncing = True
            for toggle in switches.values(): toggle.set_active(master.get_active())
            syncing = False
            selection_changed()
        for toggle in switches.values(): toggle.connect('notify::active', selection_changed)
        master.connect('notify::active', all_changed)
        confirm.connect('clicked', lambda *_: (self.reset_defaults({key for key, toggle in switches.items() if toggle.get_active()}), window.close()))
        selection_changed()
        window.reset_rows = reset_rows
        window.reset_preview = description
        window.reset_preview_state = preview_state
        window.reset_counts = {key: count for key, _, count, _ in categories}
        window.reset_switches = switches
        window.clear_all_switch = master
        window.confirm_button = confirm
        controls.append(cancel)
        controls.append(confirm)
        body.append(controls)
        window.set_child(body)
        keys = Gtk.EventControllerKey()
        keys.connect('key-pressed', lambda _, key, *_args: (window.close() or True) if key == Gdk.KEY_Escape else False)
        window.add_controller(keys)
        # Measure after inheriting the window's style. Preview text must never
        # participate in allocating the category column.
        width = rows.measure(Gtk.Orientation.HORIZONTAL, -1).natural
        category_scroll.set_min_content_width(width)
        category_scroll.set_max_content_width(width)
        category_scroll.set_size_request(width, -1)
        window.reset_size_groups = (label_widths, badge_widths)
        self.reset_window = window
        window.present()
        cancel.grab_focus()

    def reset_defaults(self, selected=None):
        selected = {key for key, _, _, _ in self.reset_changes()} if selected is None else set(selected)
        if not selected: return
        if 'bookmarks' in selected:
            self.favorites.clear()
            save_json(STATE, [])
        if 'hidden' in selected:
            self.learned.clear()
            save_json(LEARNED_STATE, [])
        if 'sources' in selected: self.favorite_sources.clear()
        if 'source_selection' in selected: self.disabled_sources.clear()
        if 'history' in selected:
            if self.history_timer:
                GLib.source_remove(self.history_timer)
                self.history_timer = None
            self.search_history.clear()
            if getattr(self, 'history_popover', None): self.history_popover.popdown()
        if 'filters' in selected:
            self.search.set_text('')
            self.expanded_groups.clear()
            self.search_expanded.clear()
            self.keyboard_filter = None
            self.only_favorites.set_active(False)
            self.learned_filter.set_selected(0)
            self.type_filter.set_selected(0)
            self.live_switch.set_active(False)
            for button in self.keyboard.buttons.values(): button.set_active(False)
            self.keyboard.all_button.set_active(True)
        if 'preferences' in selected:
            self.feature_view = {}
            hotkey = self.preferences['global_hotkey']
            self.preferences = __import__('preferences').DEFAULTS.copy()
            self.preferences['global_hotkey'] = hotkey
            localization.set_language(self, 'en')
            self.system_theme.set_preferences(self.preferences)
            self.look_picker.set_selected(0)
            self.source_picker.set_selected(0)
            self.view_stack.set_visible_child_name('list')
            self.view_toggle.set_active(False)
            self.target.set_selected(0)
            self.saved_target = None
            for name, value in (('Show filters',False), ('Flat list',True), ('Columns',True)):
                self.settings_switches[name].set_active(value)
        if 'keyboard' in selected:
            for button in self.keyboard.option_buttons.values(): button.set_active(False)
            self.keyboard.extras_expanded = False
            self.keyboard.extras_layout = 'grid'
            self.keyboard.columns = True
            self.keyboard.persist()
        if 'features' in selected:
            self.features = DEFAULT_FEATURES.copy()
            self.apply_features()
            self.sync_guide_feature(False)
            if getattr(self, 'features_window', None): self.features_window.close()
        else:
            self.apply_feature_visibility()
            self.list_model.remove_all()
            self.render()
        self.save_ui_state()
        if 'preferences' in selected: self.sync_window_animations()

    def live_list_active(self):
        return getattr(self, 'live_view', False) and hasattr(self, 'view_stack') and self.view_stack.get_visible_child_name() == 'list'

    def live_view_toggled(self, switch, *_):
        self.live_view = switch.get_active()
        self.live_keys.clear()
        self.live_mods.clear()
        self.live_pressed_modifiers.clear()
        self.keyboard_focus_changed()
        self.save_ui_state()
        self.render()

    def sync_live_modifier_buttons(self):
        # Paint held modifiers without toggling the persistent manual filters.
        if not self.keyboard: return
        held = set(self.live_mods.values()) if self.live_list_active() else set()
        for modifier, button in self.keyboard.buttons.items():
            if modifier in held or button.get_active():
                button.set_state_flags(Gtk.StateFlags.CHECKED, False)
            else:
                button.unset_state_flags(Gtk.StateFlags.CHECKED)

    def update_live_capture(self):
        surface = self.window.get_surface()
        wanted = self.live_list_active() and self.window.get_visible() and self.window.is_active()
        if surface and wanted != getattr(self, '_live_inhibited', False):
            if wanted: surface.inhibit_system_shortcuts(None)
            else: surface.restore_system_shortcuts()
            self._live_inhibited = wanted
        if not wanted and (self.live_keys or self.live_mods):
            self.live_keys.clear()
            self.live_mods.clear()
            self.live_pressed_modifiers.clear()
            self.render()

        self.sync_live_modifier_buttons()

    def live_modifiers_changed(self, _controller, state):
        self.restart_modifiers_changed(_controller,state)
        if self.live_list_active():
            held = {bit: name for bit, name in ((1, 'SHIFT'), (4, 'CTRL'), (8, 'ALT'), (67108864, 'SUPER')) if state & bit}
            if held != self.live_mods:
                self.live_mods = held
                self.render()
        return False

    def live_key(self, code, keyval, pressed, base_keyval=None):
        modifiers = {'Super_L':'SUPER', 'Super_R':'SUPER', 'Control_L':'CTRL', 'Control_R':'CTRL',
                     'Shift_L':'SHIFT', 'Shift_R':'SHIFT', 'Alt_L':'ALT', 'Alt_R':'ALT'}
        name = Gdk.keyval_name(keyval) or ''
        before = (dict(self.live_keys), dict(self.live_mods))
        if not pressed:
            self.live_keys.pop(code, None)
            self.live_mods.pop(code, None)
            self.live_pressed_modifiers.pop(code, None)
            if name in modifiers and modifiers[name] not in self.live_pressed_modifiers.values():
                self.live_mods = {code: mod for code, mod in self.live_mods.items() if mod != modifiers[name]}
        elif name in modifiers:
            self.live_pressed_modifiers[code] = modifiers[name]
            self.live_mods[code] = modifiers[name]
        else:
            symbol = Gdk.keyval_name(Gdk.keyval_to_lower(base_keyval if base_keyval is not None else keyval)) or name
            self.live_keys[code] = canonical(symbol)
        if before != (self.live_keys, self.live_mods): self.render()

    def live_key_released(self, _controller, keyval, code, _state):
        self.restart_shift_key(keyval,False)
        if self.live_list_active(): self.live_key(code, keyval, False)

    def live_scroll(self, controller, dx, dy):
        if not self.live_list_active() or not controller.get_current_event_state() & Gtk.accelerator_get_default_mod_mask(): return False
        adjustment = self.list_scroll.get_vadjustment()
        adjustment.set_value(adjustment.get_value() + dy * 60)
        return True

    def keyboard_focus_changed(self, *_):
        if self.keyboard and hasattr(self, 'view_stack'):
            self.keyboard.suppress_guide = self.window.get_visible() and (self.view_stack.get_visible_child_name() == 'keyboard' or self.live_list_active())
            self.keyboard.set_live(self.window.is_active() and self.view_stack.get_visible_child_name() == 'keyboard')
            self.update_live_capture()

    def shutdown(self, *_):
        self.stop_restart_watch()
        panel = getattr(self, 'chat_panel', None)
        if panel and panel.run: panel.run.stop()
        if self.history_timer:
            GLib.source_remove(self.history_timer)
            self.history_timer = None
        if getattr(self, 'history_popover', None):
            self.history_popover.unparent()
            self.history_popover = None
        if self.keyboard:
            self.keyboard.stop()

    def focus_search(self):
        if self.info_window:
            self.info_window.close()
        self.window.present()
        self.search.grab_focus()
        self.search.select_region(0, -1)
        return False

    def restore_filters(self):
        saved = self.saved_filters
        query = saved.get('search', '') if self.preferences['remember_search'] else ''
        self.search.set_text(query if isinstance(query, str) else '')
        self.only_favorites.set_active(saved.get('favorites_only') is True)
        mode = saved.get('learned', 'all')
        modes = ['all', 'learned', 'unlearned']
        self.learned_filter.set_selected(modes.index(mode) if mode in modes else 0)
        if self.type_filter:
            kinds = [kind for kind, _ in FILTERS]
            selected = saved.get('type', 'all')
            self.type_filter.set_selected(kinds.index(selected) if selected in kinds else 0)
        key = saved.get('keyboard')
        self.keyboard_inclusive = isinstance(key, dict) and key.get('inclusive') is True
        self.keyboard_filter = None
        if isinstance(key, dict):
            symbol, layer = key.get('symbol'), key.get('layer')
            if (isinstance(symbol, str) and symbol and
                    self.search.get_text() == '@' + symbol.lower() and
                    (layer is None or (isinstance(layer, list) and
                     all(isinstance(v, str) and v in {'SUPER', 'CTRL', 'ALT', 'SHIFT'} for v in layer)))):
                self.keyboard_filter = (symbol, None if layer is None else frozenset(layer))
        self.update_keyboard_notice()

    def save_keyboard_preferences(self, preferences):
        self.keyboard_preferences = preferences
        self.save_ui_state()
        if hasattr(self, 'list_box'): self.render()

    def save_ui_state(self):
        filters = self.saved_filters.copy()
        if hasattr(self, 'search') and hasattr(self, 'only_favorites') and self.learned_filter:
            key = self.keyboard_filter
            filters = {
                'search': self.search.get_text() if self.preferences['remember_search'] else '',
                'favorites_only': self.only_favorites.get_active(),
                'type': FILTERS[self.type_filter.get_selected()][0] if self.type_filter else filters.get('type', 'all'),
                'learned': ['all', 'learned', 'unlearned'][self.learned_filter.get_selected()],
                'keyboard': None if key is None else {
                    'symbol': key[0], 'layer': None if key[1] is None else sorted(key[1]), 'inclusive': getattr(self, 'keyboard_inclusive', False)},
            }
        if not getattr(self, 'preferences', preferences.DEFAULTS)['remember_search']:
            filters['search'] = ''
        self.saved_filters = filters
        save_json(UI_STATE, {'resolved_look': __import__('theme').resolve_look(self.look if self.feature_enabled('appearance') else 'system'), 'preferences': getattr(self, 'preferences', preferences.DEFAULTS), 'look': getattr(self, 'look', 'system'), 'feature_view': getattr(self, 'feature_view', {}), 'disabled_sources': sorted(self.disabled_sources), 'features': self.features, 'search_history': self.search_history, 'expanded_groups': self.expanded_groups, 'filters': filters, 'keyboard_view': getattr(self, 'keyboard_preferences', {}), 'chat_split_ratio': self.chat_split_ratio, 'view': getattr(self, 'saved_view', 'list'), 'live_view': getattr(self, 'live_view', False), 'show_list_filters': getattr(self, 'show_list_filters', False), 'target': getattr(self, 'saved_target', None), 'source': getattr(self, 'source_name', 'Omarchy'), 'flat_list': getattr(self, 'flat_list', False), 'columns': getattr(self, 'columns', False), 'favorite_sources': sorted(getattr(self, 'favorite_sources', {'Omarchy'}))})

    def filters_changed(self, *_):
        self.save_ui_state()
        self.render()

    def update_keyboard_notice(self):
        if not hasattr(self, 'keyboard_notice'):
            return
        self.keyboard_notice.set_visible(self.keyboard_filter is not None)
        if self.keyboard_filter:
            symbol, layer = self.keyboard_filter
            label = ' + '.join(sorted(layer)) if layer else ('All layers' if layer is None else 'No modifiers')
            self.keyboard_notice.set_text(f'Keyboard selection: {label} + {symbol} · Edit search to clear the layer filter')
        else:
            self.keyboard_notice.set_text('')

    def update_search_clear(self, entry):
        position = Gtk.EntryIconPosition.SECONDARY
        entry.set_icon_from_icon_name(position, 'edit-clear-symbolic' if entry.get_text() else None)
        entry.set_icon_activatable(position, True)
        entry.set_icon_tooltip_text(position, localization.text('Clear search'))

    def clear_search_icon(self, entry, position):
        if position == Gtk.EntryIconPosition.SECONDARY:
            entry.set_text('')
            entry.grab_focus()

    def search_changed(self, *_):
        if self.overlay_surfaces is not None: self.overlay_surfaces.freeze_top(self.window)
        if hasattr(self, 'list_scroll'): self.list_scroll.get_vadjustment().set_value(0)
        self.update_history_suggestions()
        profile_path = os.environ.get('SHORTCUTS_PROFILE_SEARCH')
        started = time.perf_counter()
        if profile_path:
            self._search_trace = {'query': self.search.get_text(), 'view': self.view_stack.get_visible_child_name(),
                                  'input_to_change_ms': round((started - getattr(self, '_search_key_started', started))*1000, 3)}
        self._reset_results_scroll = True
        self.list_selection.set_selected(Gtk.INVALID_LIST_POSITION)
        self.search_expanded = {}
        self.keyboard_filter = None
        self.update_keyboard_notice()
        self.filters_changed()
        if profile_path:
            trace = self._search_trace
            self._search_trace = None
            trace['handler_ms'] = round((time.perf_counter() - started)*1000, 3)
            frame_clock = self.window.get_frame_clock()
            if frame_clock:
                def painted(*_):
                    frame_clock.disconnect(handler)
                    trace['change_to_paint_ms'] = round((time.perf_counter() - started)*1000, 3)
                    trace['input_to_paint_ms'] = round(trace['input_to_change_ms'] + trace['change_to_paint_ms'], 3)
                    with open(profile_path, 'a') as log:
                        log.write(json.dumps(trace) + '\n')
                handler = frame_clock.connect('after-paint', painted)
                self.window.queue_draw()

    def select_key(self, symbol, layer, inclusive=False):
        if not symbol:
            return
        self.view_stack.set_visible_child_name('list')
        self.search.set_text('@' + symbol.lower())
        self.keyboard_filter = (symbol, layer)
        self.keyboard_inclusive = inclusive
        self.update_keyboard_notice()
        self.filters_changed()

    def target_changed(self, *_):
        if getattr(self, '_updating_targets', False): return
        selected = self.target.get_selected()
        self.saved_target = self.targets[selected - 1]['address'] if 0 < selected <= len(self.targets) else None
        self.save_ui_state()

    def refresh_targets(self):
        if getattr(self, '_targets_busy', False): return True
        self._targets_busy = True
        def worker():
            try:
                updated = sorted([c for c in clients() if c['class'] != APP_ID and c['mapped']], key=lambda c: c.get('focusHistoryID', 999))
            except (OSError, subprocess.SubprocessError, ValueError): updated = None
            GLib.idle_add(self.targets_loaded, updated)
        threading.Thread(target=worker, daemon=True).start()
        return True

    def targets_loaded(self, updated):
        self._targets_busy = False
        if updated is None: return False
        try:
            selected = self.target.get_selected()
            old = self.targets[selected - 1]['address'] if 0 < selected <= len(self.targets) else self.saved_target
            labels = [f"{c['title'][:65]}  ·  workspace {c['workspace']['name']}" for c in updated]
            if [(c['address'], c['title']) for c in updated] != [(c['address'], c['title']) for c in self.targets]:
                self._updating_targets = True
                self.targets = updated
                self.target_model.splice(0, self.target_model.get_n_items(), ['Current'] + labels)
                self.target.set_selected(next((i + 1 for i,c in enumerate(updated) if c['address'] == old), 0))
                self._updating_targets = False
        except (subprocess.SubprocessError, ValueError):
            pass
        return False

    def flat_changed(self, toggle, *_):
        self.flat_list = toggle.get_active()
        self.list_controls.set_visible(not self.flat_list and self.view_stack.get_visible_child_name() == 'list')
        self.save_ui_state()
        self.render()

    def columns_changed(self, toggle, *_):
        self.columns = toggle.get_active()
        self.save_ui_state()
        self.render()

    def sync_window_animations(self):
        # One source of truth: the window rules read this preference from UI_STATE.
        mode = self.preferences.get('window_animations', 'off')
        legacy = STATE.parent / 'animate-window'
        migrated = legacy.exists()
        if migrated: legacy.unlink()
        if getattr(self, '_applied_animation_mode', None) == mode and not migrated: return
        initial = not hasattr(self, '_applied_animation_mode')
        self.save_ui_state()
        self._applied_animation_mode = mode
        # The installed window rule reads persisted preferences already. Reloading
        # the entire compositor on each launch blocks the first frame needlessly.
        if initial and not migrated: return
        if os.environ.get('GDK_BACKEND') == 'broadway' or not shutil.which('hyprctl'): return
        subprocess.run(['hyprctl', 'reload'], capture_output=True, timeout=3)
        result = subprocess.run(['hyprctl', 'configerrors'], capture_output=True, text=True, timeout=3)
        if result.stdout.strip(): self.status.set_text(result.stdout.strip())

    def navigate_results(self, keyval):
        if self.view_stack.get_visible_child_name() != 'list': return False
        focus = self.window.get_focus()
        if not (focus == self.search or (focus and focus.is_ancestor(self.search))
                or focus == self.list_box or (focus and focus.is_ancestor(self.list_box))):
            return False
        positions = [i for i in range(self.list_model.get_n_items())
                     if 'item' in self.list_model.get_item(i).data]
        if not positions: return False
        selected = self.list_selection.get_selected()
        current = positions.index(selected) if selected in positions else (-1 if keyval == Gdk.KEY_Down else 0)
        index = positions[(current + (1 if keyval == Gdk.KEY_Down else -1)) % len(positions)]
        self.list_selection.set_selected(index)
        self.list_box.scroll_to(index, Gtk.ListScrollFlags.NONE, None)
        return True

    def source_factory(self, show_favorites=False):
        factory = Gtk.SignalListItemFactory()
        def setup(_factory, item):
            box = Gtk.Box(spacing=12)
            box.title = Gtk.Label(xalign=0, hexpand=True, width_chars=7)
            box.badge = Gtk.Label(valign=Gtk.Align.CENTER, width_chars=4)
            box.badge.add_css_class('count-badge')
            box.badge.set_visible(show_favorites)
            box.append(box.title)
            box.append(box.badge)
            if show_favorites:
                box.star = Gtk.Button(label='☆')
                box.star.add_css_class('flat')
                def toggle(*_):
                    source = box.source_name
                    if source in self.favorite_sources: self.favorite_sources.remove(source)
                    else: self.favorite_sources.add(source)
                    self.save_ui_state()
                    for other in self.source_badges:
                        if hasattr(other, 'star'):
                            favored = other.source_name in self.favorite_sources
                            other.star.set_label('★' if favored else '☆')
                            other.star.set_tooltip_text('Remove source bookmark' if favored else 'Bookmark source')
                box.star.connect('clicked', toggle)
                box.append(box.star)
            item.set_child(box)
        def bind(_factory, item):
            box = item.get_child()
            box.source_name = item.get_item().get_string()
            box.title.set_text(box.source_name)
            count = self.source_counts.get(box.source_name)
            box.badge.set_text(str(count) if count is not None else '—')
            if hasattr(box, 'star'):
                favored = box.source_name in self.favorite_sources
                box.star.set_label('★' if favored else '☆')
                box.star.set_tooltip_text('Remove source bookmark' if favored else 'Bookmark source')
            self.source_badges.add(box)
        def unbind(_factory, item):
            self.source_badges.discard(item.get_child())
        factory.connect('setup', setup)
        factory.connect('bind', bind)
        factory.connect('unbind', unbind)
        return factory

    def update_source_count(self, source, count):
        self.source_counts[source] = count
        for box in self.source_badges:
            if box.source_name == source:
                box.badge.set_text(str(count) if count is not None else '—')
        return False

    def initial_source_counts(self):
        self.refresh_source_counts()
        return False

    def source_available(self, source):
        return (source not in self.disabled_sources and shortcut_sets.installed(source)
                and (self.source_counts.get(source) or 0) > 0)

    def set_source_enabled(self, source, enabled):
        if enabled: self.disabled_sources.discard(source)
        else: self.disabled_sources.add(source)
        self.ensure_available_source()
        self.save_ui_state()

    def reload_source_registry(self):
        if self.counts_busy: return
        before = list(SOURCES)
        refresh_registry()
        if before != SOURCES:
            self._updating_source_model = True
            self.source_picker.set_model(Gtk.StringList.new(SOURCES))
            self.source_picker.set_selected(SOURCES.index(self.source_name) if self.source_name in SOURCES else 0)
            self._updating_source_model = False

    def ensure_available_source(self):
        if self.source_available(self.source_name): return
        available = [name for name in SOURCES if self.source_available(name)]
        if available:
            self.source_picker.set_selected(SOURCES.index(available[0]))
            if self.source_name != available[0]: self.source_changed()
        else:
            self.items = []
            self.source_note = 'No available shortcut sets · Choose shortcut sets from the source menu'
            self.render()

    def refresh_source_counts(self):
        if self.counts_busy: return True
        self.reload_source_registry()
        self.counts_busy = True
        sources = list(SOURCES)
        def work():
            for source in sources:
                try:
                    if not shortcut_sets.installed(source): count = 0
                    else:
                        cached = source_cache.read(source)
                        if cached: count = len(cached[0])
                        elif source == self.source_name and self.refresh_busy: continue
                        else:
                            rows, note = (records(), '') if source == 'Omarchy' else load_source(source)
                            count = len(rows)
                except Exception:
                    count = 0
                GLib.idle_add(self.update_source_count, source, count)
            GLib.idle_add(self.source_counts_finished)
        threading.Thread(target=work, daemon=True).start()
        return True

    def source_counts_finished(self):
        self.counts_busy = False
        self.ensure_available_source()
        library = getattr(self, 'source_library_window', None)
        if library: library.refresh_sources()
        popup = getattr(self, 'choice_popover', None)
        if popup and popup.get_visible() and getattr(self, '_choice_dropdown', None) == self.source_picker:
            self.open_choice(self.source_picker, from_control=True)
        return False

    def source_changed(self, *_):
        if getattr(self, '_updating_source_model', False): return
        if self.source_picker.get_selected() >= len(SOURCES): return
        self.source_name = SOURCES[self.source_picker.get_selected()]
        self.source_note = ''
        self.items = []
        self.search.set_text('')
        self.keyboard_filter = None
        self.type_filter.set_selected(0)
        self.save_ui_state()
        self.render()
        self.refresh()

    def poll_source(self):
        if self.window.is_active():
            self.refresh()
        return True

    def refresh(self):
        if self.source_name in self.disabled_sources:
            self.ensure_available_source()
            return
        if self.refresh_busy: return
        self.refresh_busy = True
        source = self.source_name
        if not self.items:
            cached = source_cache.read(source)
            if cached and shortcut_sets.installed(source):
                self.items, _ = cached
                self.source_note = 'Saved shortcuts · refreshing…'
            self.render()
        def work():
            try:
                startup_mark("records-start")
                if source in self.disabled_sources or not shortcut_sets.installed(source):
                    items, note = [], f'{source} is not installed'
                else:
                    items, note = (records(), 'Live Hyprland bindings') if source == 'Omarchy' else load_source(source)
                source_cache.write(source, items, note)
                GLib.idle_add(self.source_loaded, source, items, note)
            except Exception as e:
                GLib.idle_add(self.source_loaded, source, [], f'Cannot read {source}: {e}')
        threading.Thread(target=work, daemon=True).start()

    def source_loaded(self, source, items, note):
        unavailable = not items and ('unavailable' in note or 'not installed' in note or note.startswith('Cannot read'))
        self.update_source_count(source, None if unavailable else len(items))
        self.refresh_busy = False
        if source != self.source_name:
            self.refresh()
            return False
        if source in self.disabled_sources or not shortcut_sets.installed(source) or not items:
            if unavailable and self.items:
                self.source_note = 'Saved shortcuts · refresh unavailable'
            else:
                self.items = items
                self.source_note = note
            self.render()
            self.ensure_available_source()
            return False
        if items != self.items or note != self.source_note:
            self.source_note = note
            self.loaded(items)
        return False

    def loaded(self, items):
        self.items = items
        self.render()
        startup_mark("shortcuts-rendered")

    def favorite(self, item):
        if not self.feature_enabled('bookmarks'): return
        if item['id'] in self.favorites:
            self.favorites.remove(item['id'])
        else:
            self.favorites.add(item['id'])
        save_json(STATE, sorted(self.favorites))
        self.refresh_marks(item)

    def toggle_learned(self, item):
        if not self.feature_enabled('hidden'): return
        if item['id'] in self.learned:
            self.learned.remove(item['id'])
        else:
            self.learned.add(item['id'])
        save_json(LEARNED_STATE, sorted(self.learned))
        self.refresh_marks(item)

    def refresh_marks(self, item):
        if hasattr(self, 'view_stack'): self.apply_feature_visibility()
        # Keep focused controls alive when marking does not change membership.
        matches = {record['id'] for record in self.filtered_items()}
        changed_membership = self.only_favorites.get_active() or self.learned_filter.get_selected() != 0
        if changed_membership:
            positions = [(scroll.get_vadjustment(), scroll.get_vadjustment().get_value())
                         for scroll in (getattr(self, 'list_scroll', None), getattr(self, 'keyboard_scroll', None))
                         if scroll]
            self.render()
            def restore():
                for adjustment, position in positions: adjustment.set_value(position)
                return False
            restore()
            GLib.idle_add(restore)
            # ListView adjusts its anchor during the next layout, after idle work.
            def after_layout(_widget, _clock):
                restore()
                return False
            self.list_box.add_tick_callback(after_layout)
            GLib.timeout_add(45, restore)
            return
        for i in range(self.list_model.get_n_items()):
            entry = self.list_model.get_item(i)
            if entry.data.get('item', {}).get('id') == item['id']:
                entry.data['appearance'] = (item['id'] in self.favorites, item['id'] in self.learned,
                                             self.columns, self.shortcut_column_width)
        def update(widget):
            if getattr(widget, 'shortcut_id', None) == item['id'] and hasattr(widget, 'refresh_marks'):
                widget.refresh_marks()
            child = widget.get_first_child()
            while child:
                update(child)
                child = child.get_next_sibling()
        update(self.list_box)
        if self.keyboard: update(self.keyboard.extras_host)
        if hasattr(self, 'status'):
            self.status.set_text(localization.text('{shown} of {total} shortcuts').format(shown=len(matches), total=len(self.items)) + (' · ' + localization.text('{count} hidden').format(count=len(self.learned.intersection(r["id"] for r in self.items))) if self.feature_enabled('hidden') else '') + (' · ' + localization.text(self.source_note) if getattr(self, 'source_note', '') else ''))

    def filtered_items(self):
        query = self.search.get_text().casefold()
        mode = self.learned_filter.get_selected() if self.learned_filter else 0
        selected_type = FILTERS[self.type_filter.get_selected()][0] if self.type_filter else 'all'
        matches = [r for r in self.items if matches_query(r, query)
                   and matches_type(r, selected_type)
                   and (not self.feature_enabled('bookmarks') or not self.only_favorites.get_active() or r['id'] in self.favorites)
                   and (not self.feature_enabled('hidden') or mode != 1 or r['id'] in self.learned)
                   and (not self.feature_enabled('hidden') or mode != 2 or r['id'] not in self.learned)]
        if self.keyboard_filter:
            symbol, layer = self.keyboard_filter
            matches = [r for r in matches if split_shortcut(r['key'])[1] == symbol
                       and (layer is None or (layer <= split_shortcut(r['key'])[0] if getattr(self, 'keyboard_inclusive', False) else split_shortcut(r['key'])[0] == layer))]
        keyboard = getattr(self, 'keyboard', None)
        if keyboard and self.view_stack.get_visible_child_name() == 'list':
            selected = frozenset(keyboard.manual)
            if self.live_list_active():
                selected |= frozenset(self.live_mods.values())
                symbols = set(self.live_keys.values())
                if symbols: matches = [r for r in matches if split_shortcut(r['key'])[1] in symbols]
            if selected or not keyboard.all_layers:
                matches = [r for r in matches if
                           (selected <= split_shortcut(r['key'])[0] if keyboard.all_layers
                            else selected == split_shortcut(r['key'])[0])]
        return matches

    def set_all_expanded(self, expanded):
        if self.flat_list: return
        target = self.search_expanded if self.search.get_text().strip() else self.expanded_groups
        for category in {item['group'] for item in self.items}:
            target[category] = expanded
        self.save_ui_state()
        self.render()

    def group_toggled(self, section, _property, category):
        if self.search.get_text().strip():
            return
        self.expanded_groups[category] = section.get_expanded()
        self.save_ui_state()

    def open_folder(self, folder):
        try:
            folder.mkdir(parents=True, exist_ok=True)
            Gio.AppInfo.launch_default_for_uri(folder.as_uri(), None)
        except Exception as e:
            self.status.set_text('Could not open folder: ' + str(e))

    def show_management(self, *_):
        if not self.feature_enabled('manage'): return
        self.app_menu_button.popdown()
        if not hasattr(self, 'manager_panel'):
            self.manager_panel = ShortcutManagerPanel(changed=self.refresh)
            scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
            scroll.set_child(self.manager_panel)
            self.view_stack.add_named(scroll, 'manage')
        current = self.view_stack.get_visible_child_name()
        if current != 'manage':
            self.manager_previous_view = current
        self.view_stack.set_visible_child_name('manage')
        self.manager_panel.refresh()
        self.menu_button.popdown()

    def close_management(self, *_):
        self.view_stack.set_visible_child_name(getattr(self, 'manager_previous_view', 'list'))

    def show_guide(self):
        if not self.feature_enabled('guide'): return
        import guide_settings
        guide_settings.show(self)

    def guide_closed(self, *_):
        self.guide_window = None
        return False

    def show_info(self):
        import about
        about.show(self)

    def show_details(self):
        if self.info_window:
            self.info_window.close()
        self.info_window = InfoWindow(self, project_info(len(self.items)), PROJECT, STATE.parent)
        if getattr(self, 'about_window', None): self.info_window.set_transient_for(self.about_window)
        self.info_window.connect('close-request', self.info_closed)
        self.info_window.present()

    def info_closed(self, *_):
        self.info_window = None
        return False

    def shortcut_row(self, item, columns=None, preview=False):
        row = Gtk.Box(spacing=4)
        row.add_css_class('shortcut-row')
        star = Gtk.Button(label='★' if item['id'] in self.favorites else '☆')
        star.add_css_class('flat')
        star.add_css_class('small-action')
        star.set_valign(Gtk.Align.CENTER)
        action_tooltip(star, ('Remove bookmark' if item['id'] in self.favorites else 'Bookmark shortcut') + ' (Ctrl+Shift+B)')
        star.connect('clicked', lambda _, r=item: None if preview else self.favorite(r))
        learned = Gtk.ToggleButton(icon_name='view-conceal-symbolic' if item['id'] in self.learned else 'view-reveal-symbolic', active=item['id'] in self.learned)
        learned.add_css_class('flat')
        learned.add_css_class('learned-toggle')
        learned.add_css_class('small-action')
        learned.set_valign(Gtk.Align.CENTER)
        action_tooltip(learned, ('Unhide shortcut' if item['id'] in self.learned else 'Hide shortcut') + ' (Ctrl+Shift+L)')
        learned.connect('toggled', lambda _, r=item: None if preview or getattr(row, 'updating_marks', False) else self.toggle_learned(r))
        action = Gtk.Button(hexpand=True)
        action.add_css_class('flat')
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        name_row = Gtk.Box(spacing=8)
        prefs = getattr(self, 'preferences', preferences.DEFAULTS)
        app_icons, action_icons = preview or prefs['app_icons'], preview or prefs['action_icons']
        icon_column = Gtk.Box(valign=Gtk.Align.CENTER)
        icon_column.add_css_class('shortcut-icon-column')
        if item.get('app_icon') and app_icons:
            icon = application_icon(item['app_icon'])
            icon.set_pixel_size(20)
            icon_column.append(icon)
        elif item.get('type_icon') and action_icons and item.get('kind') not in ('desktopApp', 'webapp'):
            icon_column.append(Gtk.Label(label=item['type_icon'], valign=Gtk.Align.CENTER))
        reserve = preview or any((r.get('app_icon') and app_icons) or
                                (r.get('type_icon') and action_icons and r.get('kind') not in ('desktopApp','webapp'))
                                for r in self.items)
        if reserve:
            icon_column.set_size_request(22, -1)
            name_row.append(icon_column)
        label = Gtk.Label(label=item['name'], xalign=0, hexpand=True, wrap=True)
        label.add_css_class('shortcut-name')
        name_row.append(label)
        content.append(name_row)
        key = Gtk.Label(label=item.get('display_key', item['key']), xalign=0, wrap=True)
        key.add_css_class('shortcut-key')
        content.append(key)
        if self.columns if columns is None else columns:
            content.remove(name_row)
            content.remove(key)
            content = Gtk.Box(spacing=10 if getattr(getattr(self, 'system_theme', None), 'current_look', '') == 'square' else 18)
            key.remove_css_class('shortcut-key')
            key.add_css_class('column-shortcut')
            key.set_wrap(False)
            key.set_ellipsize(Pango.EllipsizeMode.END)
            key.set_max_width_chars(1)
            key.set_tooltip_text(item.get('display_key', item['key']))
            key.set_size_request(140 if preview else self.shortcut_column_width, -1)
            if preview: key.set_wrap(True)
            key.set_hexpand(False)
            content.append(key)
            content.append(Gtk.Label(label='→'))
            content.append(name_row)
        action.set_child(content)
        draggable = 'drag(' in item['arg'] or 'resize({' in item['arg'] and 'mouse:' in item['key'].lower()
        action.set_sensitive(bool(item['dispatcher']) and not draggable)
        if not action.get_sensitive(): action.add_css_class('shortcut-reference')
        note = 'Use the mouse shortcut to drag interactively.' if draggable else (
            'This action is only available through its keyboard shortcut.' if not item['dispatcher'] else '')
        attach_tooltip(row, item, note, lambda: self.preferences)
        action.connect('clicked', lambda _, r=item: None if preview else self.run_action(r))
        row.append(action)
        row.append(star)
        row.append(learned)
        star.set_visible(preview or self.feature_enabled('bookmarks'))
        learned.set_visible(preview or self.feature_enabled('hidden'))
        reveal_indicators_on_hover(row, [(star, item['id'] in self.favorites), (learned, item['id'] in self.learned)])
        if preview:
            row.set_can_target(False)
            row.reveal_indicators(True)
        row.shortcut_id = item['id']
        def update_marks():
            row.updating_marks = True
            bookmarked, hidden = item['id'] in self.favorites, item['id'] in self.learned
            star.set_label('★' if bookmarked else '☆')
            learned.set_active(hidden)
            learned.set_icon_name('view-conceal-symbolic' if hidden else 'view-reveal-symbolic')
            action_tooltip(star, ('Remove bookmark' if bookmarked else 'Bookmark shortcut') + ' (Ctrl+Shift+B)')
            action_tooltip(learned, ('Unhide shortcut' if hidden else 'Hide shortcut') + ' (Ctrl+Shift+L)')
            row.indicators[:] = [(star, bookmarked), (learned, hidden)]
            row.refresh_indicators()
            row.updating_marks = False
        row.refresh_marks = update_marks
        row.set_focusable(not preview)
        if preview:
            for control in (star, learned, action): control.set_focusable(False)
        if getattr(self, '_building_main_list' , False):
            self.navigation_rows.append((row, item, action))
        return row

    def create_shortcut_list(self):
        self.row_cache = OrderedDict()
        self.list_model = Gio.ListStore.new(ShortcutEntry)
        self.list_selection = Gtk.SingleSelection(model=self.list_model, autoselect=False, can_unselect=True)
        factory = Gtk.SignalListItemFactory()
        def setup(_factory, item):
            motion = Gtk.EventControllerMotion()
            # Hover is styled by GTK. Pointer motion must never steal keyboard
            # selection or focus (including motion caused by scrolling rows).
            # The persistent wrapper survives recycling without stale shortcut IDs.
            wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            wrapper.add_controller(motion)
            item.hover_controller = motion
            item.wrapper = wrapper
            item.set_child(wrapper)
        factory.connect('setup', setup)
        factory.connect('bind', self.bind_list_item)
        factory.connect('unbind', self.unbind_list_item)
        self.list_box = Gtk.ListView(model=self.list_selection, factory=factory)
        self.list_box.add_css_class('virtual-shortcuts')
        self.list_box.connect('activate', self.activate_list_item)

    def unbind_list_item(self, factory, list_item):
        widget = list_item.wrapper.get_first_child()
        key = getattr(list_item, 'row_cache_key', None)
        if widget is not None: list_item.wrapper.remove(widget)
        if widget is not None and key is not None:
            self.row_cache[key] = widget
            self.row_cache.move_to_end(key)
            while len(self.row_cache) > 256:
                self.row_cache.popitem(last=False)

    def bind_list_item(self, factory, list_item):
        data = list_item.get_item().data
        # Keep a bounded pool of previously displayed rows for backspacing and
        # repeated searches. Never create widgets for unseen results in advance.
        key = (repr(data), self.feature_enabled('bookmarks'), self.feature_enabled('hidden'),
               self.preferences.get('app_icons', True), self.preferences.get('action_icons', True))
        list_item.row_cache_key = key
        cached = self.row_cache.pop(key, None)
        if cached is not None:
            if hasattr(cached, 'refresh_marks'):
                cached.refresh_marks()
                cached.reveal_indicators(False)
            list_item.wrapper.append(cached)
            return
        if 'item' in data:
            widget = self.shortcut_row(data['item'])
            widget.set_focusable(False)
        elif data.get('loading'):
            widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16, margin_top=20, margin_bottom=20)
            widget.append(Gtk.Label(label=localization.text('Loading shortcuts…'), xalign=0))
            for width in (280, 210, 250):
                bar = Gtk.Box(height_request=18, width_request=width, halign=Gtk.Align.START)
                bar.add_css_class('shortcut-skeleton')
                widget.append(bar)
        elif 'category' in data:
            category = data['category']
            widget = Gtk.Button(hexpand=True)
            widget.add_css_class('category-header')
            box = Gtk.Box(spacing=16)
            kind = next((k for k, (name, _) in TYPES.items() if name == category), None)
            if kind: box.append(Gtk.Label(label=TYPES[kind][1]))
            box.append(Gtk.Label(label=category, xalign=0, hexpand=True))
            badge = Gtk.Label(label=str(data['count']))
            badge.add_css_class('count-badge')
            box.append(badge)
            box.append(Gtk.Image(icon_name='pan-down-symbolic' if data['expanded'] else 'pan-end-symbolic'))
            widget.set_child(box)
            def toggle(*_):
                target = self.search_expanded if self.search.get_text().strip() else self.expanded_groups
                target[category] = not data['expanded']
                self.save_ui_state()
                self.render()
            widget.connect('clicked', toggle)
        else:
            widget = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=24, margin_bottom=12)
            widget.add_css_class('empty-shortcuts')
            icon = Gtk.Image.new_from_icon_name('view-conceal-symbolic')
            icon.set_pixel_size(28)
            widget.append(icon)
            query = self.search.get_text()
            message = localization.text('No matches for “{query}”').format(query=query) if query else localization.text('No shortcuts match these filters.')
            widget.append(Gtk.Label(label=message, wrap=True))
        list_item.wrapper.append(widget)

    def activate_list_item(self, _view, position):
        entry = self.list_model.get_item(position)
        if not entry or 'item' not in entry.data: return
        item = entry.data['item']
        draggable = 'drag(' in item['arg'] or ('resize({' in item['arg'] and 'mouse:' in item['key'].lower())
        if item['dispatcher'] and not draggable: self.run_action(item)

    def sync_native_presentation(self, count):
        if not hasattr(self, 'system_theme') or not hasattr(self, 'status'): return
        native = self.system_theme.current_look == 'square'
        self.list_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.EXTERNAL if native else Gtk.PolicyType.AUTOMATIC)
        simple = not any(value for key, value in self.features.items() if key not in ('history', 'agent'))
        self.status.set_visible(not (native and simple))
        if not native or self.view_stack.get_visible_child_name() != 'list': return
        if self.main_pane.get_end_child() is not None: return
        from native_style import menu_tokens, folded_height
        tokens = menu_tokens()
        inset = 2*tokens['padding'] + tokens['header'] + tokens['gap']
        width, available_height = 800, 800
        surface = self.window.get_surface()
        if surface:
            monitor = self.window.get_display().get_monitor_at_surface(surface)
            if monitor:
                geometry = monitor.get_geometry()
                width, available_height = min(width, geometry.width-40), geometry.height-40
        if self.overlay_surfaces is not None:
            bounds = self.overlay_surfaces.available_bounds(self.window)
            width, available_height = min(width,bounds[0]), min(available_height,bounds[1])
        # Filtering should not move the surrounding window while the user types.
        count = max(count, len(self.items))
        rows_height = folded_height(count, min(500 + tokens['row'] + tokens['row_gap'], available_height*.8, available_height-inset), tokens)
        if count == 0:
            rows_height = max(rows_height, 24+28+8+round(tokens['title']*1.5)+12)
            self.list_scroll.get_vadjustment().set_value(0)
        desired = (width, min(inset+rows_height, available_height))
        if desired != tuple(self.window.get_default_size()):
            self._native_size = desired
            self.window.set_default_size(*desired)

    def update_column_width(self):
        # Measure the complete source, never the filtered or visible subset.
        keys = tuple(item.get('display_key', item['key']) for item in self.items)
        prefs = getattr(self, 'preferences', preferences.DEFAULTS)
        family, size = self.system_theme.typography(prefs) if hasattr(self, 'system_theme') else (prefs['font_family'], prefs['font_size'])
        chat_open = bool(getattr(self, "main_pane", None) and self.main_pane.get_end_child())
        signature = (keys, family, size, chat_open)
        if signature == self.column_signature: return
        self.column_signature = signature
        layout = self.list_box.create_pango_layout('')
        font = Pango.FontDescription(family)
        font.set_absolute_size(size * Pango.SCALE)
        layout.set_font_description(font)
        widths = []
        for key in keys:
            layout.set_text(key, -1)
            widths.append(layout.get_pixel_size()[0])
        # A multi-alternative binding must not dictate every row's geometry.
        # Use the source-wide median so filtering never shifts the columns.
        import statistics
        typical = statistics.median(widths) if widths else 0
        outlier_limit = typical + max(80, typical * .6)
        regular = [width for width in widths if width <= outlier_limit]
        self.shortcut_column_width = max(140, min(200 if chat_open else 320, max(regular, default=140) + 8))

    def render(self):
        if getattr(self, '_normalizing_marks', False): return
        if hasattr(self, 'visibility_label') and self.items:
            self._normalizing_marks = True
            ids = {item['id'] for item in self.items}
            if not self.favorites.intersection(ids): self.only_favorites.set_active(False)
            if not self.learned.intersection(ids): self.learned_filter.set_selected(0)
            self._normalizing_marks = False
            self.apply_feature_visibility()
        self.sync_live_modifier_buttons()
        trace = getattr(self, '_search_trace', None)
        render_started = phase_started = time.perf_counter() if trace is not None else 0
        matches = self.filtered_items()
        if trace is not None:
            trace['filter_ms'] = round((time.perf_counter()-phase_started)*1000, 3)
            trace['matches'] = len(matches)
            phase_started = time.perf_counter()
        self.update_column_width()
        self.sync_native_presentation(len(matches))
        if self.keyboard and self.view_stack.get_visible_child_name() == 'keyboard':
            self.keyboard.set_items(matches)
        if trace is not None:
            trace['keyboard_and_width_ms'] = round((time.perf_counter()-phase_started)*1000, 3)
            phase_started = time.perf_counter()
        if hasattr(self, 'status'):
            learned_count = sum(r['id'] in self.learned for r in self.items)
            self.status.set_text(localization.text('{shown} of {total} shortcuts').format(shown=len(matches), total=len(self.items)) + (' · ' + localization.text('{count} hidden').format(count=learned_count) if self.feature_enabled('hidden') else '') + (' · ' + localization.text(self.source_note) if getattr(self, 'source_note', '') else ''))
        entries = []
        if not matches:
            entries.append(ShortcutEntry({'loading': True}) if self.refresh_busy and not self.items else ShortcutEntry({'empty_query': self.search.get_text()}))
        elif self.flat_list:
            entries = [ShortcutEntry({'item': item}) for item in matches]
        else:
            for category in sorted({r['group'] for r in matches}):
                members = [r for r in matches if r['group'] == category]
                expanded = self.search_expanded.get(category, True) if self.search.get_text().strip() or (self.live_list_active() and (self.live_keys or self.live_mods)) else self.expanded_groups.get(category, True)
                entries.append(ShortcutEntry(dict(category=category, count=len(members), expanded=expanded)))
                if expanded: entries.extend(ShortcutEntry({'item': item}) for item in members)
        previous = self.list_selection.get_selected_item()
        identity = previous.data.get('item', {}).get('id') if previous else None
        # Preserve unchanged rows; favoriting one entry must not rebuild the list.
        for entry in entries:
            item = entry.data.get('item')
            if item:
                entry.data['appearance'] = (item['id'] in self.favorites,
                    item['id'] in self.learned, self.columns, self.shortcut_column_width)
        old_count = self.list_model.get_n_items()
        prefix = 0
        while prefix < min(old_count, len(entries)) and self.list_model.get_item(prefix).data == entries[prefix].data:
            prefix += 1
        suffix = 0
        while suffix < min(old_count, len(entries)) - prefix and self.list_model.get_item(old_count-1-suffix).data == entries[len(entries)-1-suffix].data:
            suffix += 1
        removed = old_count-prefix-suffix
        added = entries[prefix:len(entries)-suffix if suffix else len(entries)]
        if trace is not None:
            trace['model_prepare_ms'] = round((time.perf_counter()-phase_started)*1000, 3)
            phase_started = time.perf_counter()
        if removed or added:
            def entry_key(entry):
                data = entry.data
                return (data.get('item', {}).get('id'), data.get('category'))
            old = [self.list_model.get_item(i) for i in range(old_count)]
            matcher = SequenceMatcher(None, [entry_key(e) for e in old],
                                      [entry_key(e) for e in entries], autojunk=False)
            for operation, a, b, c, d in reversed(matcher.get_opcodes()):
                if operation != 'equal':
                    self.list_model.splice(a, b-a, entries[c:d])
                else:
                    for old_index, new_index in reversed(list(zip(range(a,b), range(c,d)))):
                        if old[old_index].data != entries[new_index].data:
                            self.list_model.splice(old_index, 1, [entries[new_index]])
        if identity:
            for i, entry in enumerate(entries):
                if entry.data.get('item', {}).get('id') == identity:
                    self.list_selection.set_selected(i)
                    break

        if getattr(self, '_reset_results_scroll', False):
            self._reset_results_scroll = False
            self.list_selection.set_selected(Gtk.INVALID_LIST_POSITION)
            # ListView restores its anchor during allocation; reset after model updates.
            self.list_box.scroll_to(0, Gtk.ListScrollFlags.NONE, None)
            adjustment = self.list_scroll.get_vadjustment() if hasattr(self, 'list_scroll') else None
            def reset_scroll():
                if adjustment: adjustment.set_value(0)
                return False
            GLib.idle_add(reset_scroll)
        if trace is not None:
            trace['list_update_ms'] = round((time.perf_counter()-phase_started)*1000, 3)
            trace['render_ms'] = round((time.perf_counter()-render_started)*1000, 3)
            trace['removed_rows'] = removed
            trace['added_rows'] = len(added)

    def run_action(self, item):
        self.remember_search()
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
    if len(sys.argv) > 1 and sys.argv[1] == 'ctl':
        from agent_control import main
        sys.exit(main(sys.argv[2:]))
    application=Shortcuts()
    application.run(sys.argv)
    if getattr(application,'_restart_file',None):
        os.environ['BINDLUME_RESTART_FILE']=application._restart_file
        os.execv(sys.executable,[sys.executable,str(Path(__file__).resolve())])
