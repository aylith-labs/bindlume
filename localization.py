"""Shared source-text catalogs; shortcut names and user content stay untouched."""
import json
import os
import locale
from pathlib import Path
from gi.repository import Gtk, GObject
CATALOG = json.loads(Path(__file__).with_name('translations.json').read_text())
LANGUAGE_NAMES = {'en':'English','de':'Deutsch','fr':'Français','es':'Español','uk':'Українська','hu':'Magyar','ko':'한국어','ja':'日本語','zh_CN':'简体中文'}
def detected_language():
    candidates = [os.environ.get('LC_ALL'), os.environ.get('LC_MESSAGES'), os.environ.get('LANG')]
    # LANGUAGE is a preference list; C/POSIX explicitly selects untranslated text.
    effective = next((v for v in candidates if v), '')
    if effective.split('.')[0] in ('C','POSIX'): return 'en'
    candidates = os.environ.get('LANGUAGE','').split(':') + candidates + [locale.getlocale()[0]]
    for value in candidates:
        code = (value or '').split('.')[0].split('@')[0].replace('-', '_')
        if code in LANGUAGE_NAMES: return code
        base = code.split('_')[0]
        if base in LANGUAGE_NAMES: return base
        if base == 'zh': return 'zh_CN'
    return 'en'

def resolve_language(value):
    return detected_language() if value == 'system' else value if value in LANGUAGE_NAMES else 'en'

language = 'system'
_map_hook = None

def text(source):
    return CATALOG.get(source, {}).get(resolve_language(language), source)

def install(app):
    def translate_window(_app, window):
        global _map_hook
        window.add_css_class('shortcuts-app')
        if _map_hook is None:
            # Menus, dropdown rows and chat messages can be created after the
            # window maps. Translate each widget once as it becomes visible.
            def mapped(_hint, _count, values):
                translate_widget(values[0])
                return True
            _map_hook = GObject.signal_add_emission_hook(GObject.signal_lookup('map', Gtk.Widget), 0, mapped)
        window.connect('map', lambda *_: translate_tree(window))
    app.connect('window-added', translate_window)

def translate_widget(widget):
    if getattr(widget, '_translation_skip', False): return
    if isinstance(widget, Gtk.Window) and widget.get_application() is None:
        parent = widget.get_transient_for()
        if parent and parent.get_application(): widget.set_application(parent.get_application())
    if isinstance(widget, Gtk.Label) and not widget.has_css_class('shortcut-name'):
        current = widget.get_label()
        original = getattr(widget, '_translation_source', current)
        if current != text(original) and current != original and current not in CATALOG.get(original, {}).values():
            original = current
        if original not in CATALOG and widget.get_use_underline() and original.replace('_', '') in CATALOG:
            original = original.replace('_', '')
        if original in CATALOG:
            widget._translation_source = original
            translated = text(original)
            if translated != current: widget.set_label(translated)
    tooltip = widget.get_tooltip_text()
    original_tooltip = getattr(widget, '_translation_tooltip', tooltip)
    if original_tooltip in CATALOG:
        widget._translation_tooltip = original_tooltip
        widget.set_tooltip_text(text(original_tooltip))
    if isinstance(widget, (Gtk.Entry, Gtk.SearchEntry, Gtk.Text)):
        source = getattr(widget, '_translation_placeholder', widget.get_placeholder_text())
        if source in CATALOG:
            widget._translation_placeholder = source
            widget.set_placeholder_text(text(source))
    if not getattr(widget, '_translation_connected', False):
        widget._translation_connected = True
        if isinstance(widget, Gtk.Label) and not widget.has_css_class('shortcut-name'):
            widget.connect('notify::label', lambda current, *_: translate_widget(current))

def translate_tree(widget):
    if getattr(widget, '_translation_skip', False): return
    translate_widget(widget)
    child = widget.get_first_child()
    while child:
        translate_tree(child)
        child = child.get_next_sibling()

def set_language(app, value):
    global language
    language = value
    for window in app.get_windows():
        translate_tree(window)
        if hasattr(window, 'refresh_system_choices'): window.refresh_system_choices()
