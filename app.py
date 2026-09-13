#!/usr/bin/python
"""Persistent shortcut browser using the installed Omarchy dispatch adapter."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import threading
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gio, GLib

APP_ID = 'local.omarchy.Shortcuts'
STATE = Path.home() / '.config/omarchy-shortcuts/favorites.json'
SOURCE = Path('/usr/share/omarchy/bin/omarchy-menu-keybindings')

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
        try:
            self.favorites = set(json.loads(STATE.read_text()))
        except (OSError, ValueError):
            self.favorites = set()

    def activate(self, *_):
        if self.window:
            self.window.present()
            return
        self.window = Gtk.ApplicationWindow(application=self, title='Omarchy Shortcuts')
        self.window.set_default_size(880, 700)
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
        root.append(header)
        self.search = Gtk.SearchEntry(placeholder_text='Search actions or shortcuts…', hexpand=True)
        self.search.connect('search-changed', lambda *_: self.render())
        self.only_favorites = Gtk.ToggleButton(label='★ Favorites')
        self.only_favorites.connect('toggled', lambda *_: self.render())
        controls = Gtk.Box(spacing=10)
        controls.append(self.search)
        controls.append(self.only_favorites)
        root.append(controls)
        target_row = Gtk.Box(spacing=10)
        target_row.append(Gtk.Label(label='Target window'))
        self.target_model = Gtk.StringList.new([])
        self.target = Gtk.DropDown(model=self.target_model, hexpand=True)
        target_row.append(self.target)
        root.append(target_row)
        note = Gtk.Label(label='Click an action to run it. Star shortcuts to keep them in Favorites.', xalign=0, wrap=True)
        note.add_css_class('dim-label')
        root.append(note)
        scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        scroll.set_child(self.list_box)
        root.append(scroll)
        self.status = Gtk.Label(label='Loading shortcuts…', xalign=0, wrap=True)
        self.status.add_css_class('dim-label')
        root.append(self.status)
        self.refresh_targets()
        self.window.present()
        self.refresh()
        GLib.timeout_add_seconds(3, self.refresh_targets)

    def refresh_targets(self):
        try:
            selected = self.target.get_selected()
            old = self.targets[selected]['address'] if selected < len(self.targets) else None
            updated = sorted([c for c in clients() if c['class'] != APP_ID and c['mapped']], key=lambda c: c.get('focusHistoryID', 999))
            labels = [f"{c['title'][:65]}  ·  workspace {c['workspace']['name']}" for c in updated]
            if [(c['address'], c['title']) for c in updated] != [(c['address'], c['title']) for c in self.targets]:
                self.targets = updated
                self.target_model.splice(0, self.target_model.get_n_items(), labels)
                self.target.set_selected(next((i for i,c in enumerate(updated) if c['address'] == old), 0))
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
        self.render()
        self.status.set_text(f'{len(items)} shortcuts · Favorites are saved automatically')

    def favorite(self, item):
        if item['id'] in self.favorites:
            self.favorites.remove(item['id'])
        else:
            self.favorites.add(item['id'])
        STATE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE.with_suffix('.tmp')
        tmp.write_text(json.dumps(sorted(self.favorites)))
        tmp.replace(STATE)
        self.render()

    def render(self):
        while child := self.list_box.get_first_child():
            self.list_box.remove(child)
        query = self.search.get_text().casefold()
        matches = [r for r in self.items if query in (r['key'] + ' ' + r['name'] + ' ' + r['group']).casefold() and (not self.only_favorites.get_active() or r['id'] in self.favorites)]
        if not matches:
            self.list_box.append(Gtk.Label(label='No matching shortcuts. Star an action to add a favorite.' if self.only_favorites.get_active() else 'No matching shortcuts.', margin_top=30))
        for category in sorted({r['group'] for r in matches}):
            members = [r for r in matches if r['group'] == category]
            section = Gtk.Expander(label=f'{category}  ·  {len(members)}', expanded=True)
            rows = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
            rows.add_css_class('boxed-list')
            for item in members:
                row = Gtk.Box(spacing=8, margin_top=4, margin_bottom=4, margin_start=8, margin_end=8)
                star = Gtk.Button(label='★' if item['id'] in self.favorites else '☆')
                star.set_tooltip_text('Remove favorite' if item['id'] in self.favorites else 'Add favorite')
                star.connect('clicked', lambda _, r=item: self.favorite(r))
                row.append(star)
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
                action.set_tooltip_text('Use the mouse shortcut to drag interactively' if draggable else ('This action is only available through its keyboard shortcut' if not item['dispatcher'] else 'Run ' + item['name']))
                action.connect('clicked', lambda _, r=item: self.run_action(r))
                row.append(action)
                rows.append(row)
            section.set_child(rows)
            self.list_box.append(section)

    def run_action(self, item):
        index = self.target.get_selected()
        target = self.targets[index] if index < len(self.targets) else None
        self.status.set_text('Running ' + item['name'] + '…')
        def work():
            try:
                if target:
                    current = {c['address'] for c in clients()}
                    if target['address'] not in current:
                        raise RuntimeError('Target window has closed. Select another window.')
                    selector = json.dumps('address:' + target['address'])
                    subprocess.run(['hyprctl', 'eval', 'hl.dispatch(hl.dsp.focus({ window = ' + selector + ' }))'], check=True, capture_output=True, text=True, timeout=3)
                elif item['dispatcher'] != 'exec':
                    raise RuntimeError('Select a target window first.')
                adapter('dispatch_binding "$1" "$2"', item['dispatcher'], item['arg'])
                GLib.idle_add(self.status.set_text, 'Ran ' + item['name'])
            except Exception as e:
                GLib.idle_add(self.status.set_text, 'Action failed: ' + str(e))
        threading.Thread(target=work, daemon=True).start()

if __name__ == '__main__':
    Shortcuts().run()
