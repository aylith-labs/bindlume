"""Follow the installed Omarchy palette, falling back to GTK system settings."""
from pathlib import Path
import re
import tomllib
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, GLib

PALETTE = Path.home() / '.local/state/omarchy/current/theme/colors.toml'
DEFAULT = dict(background='#242424', foreground='#eeeeee', accent='#78aeed',
               lighter_background='#343434', selection='#454545', muted='#9a9a9a')

class SystemTheme:
    def __init__(self, changed=lambda: None):
        self.provider = Gtk.CssProvider()
        self.colors = dict(DEFAULT)
        self.changed = changed
        self.last = None
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self.provider,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.poll()
        self.timer = GLib.timeout_add_seconds(1, self.poll)

    def poll(self):
        try:
            data = PALETTE.read_bytes()
        except OSError:
            data = b''
        if data == self.last:
            return True
        self.last = data
        try:
            values = tomllib.loads(data.decode())
        except (ValueError, UnicodeError):
            values = {}
        colors = {k: v for k, v in values.items() if isinstance(v, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', v)}
        settings = Gtk.Settings.get_default()
        if not colors:
            self.provider.load_from_data(b'')
            settings.reset_property('gtk-application-prefer-dark-theme')
            context = Gtk.Label().get_style_context()
            for target, role in [('background','theme_bg_color'), ('foreground','theme_fg_color'), ('accent','accent_bg_color')]:
                found, rgba = context.lookup_color(role)
                if found:
                    self.colors[target] = '#%02x%02x%02x' % tuple(round(v * 255) for v in (rgba.red, rgba.green, rgba.blue))
            self.changed()
            return True
        self.colors = dict(DEFAULT, **colors)
        c = self.colors
        rgb = [int(c['background'][i:i+2], 16) / 255 for i in (1,3,5)]
        dark = values.get('mode', 'dark' if sum(rgb) / 3 < .5 else 'light') != 'light'
        settings.set_property('gtk-application-prefer-dark-theme', dark)
        css = f'''
        @define-color accent_color {c['accent']};
        @define-color accent_bg_color {c['accent']};
        @define-color theme_selected_bg_color {c['selection']};
        @define-color theme_selected_fg_color {c['foreground']};
        window, popover > contents, tooltip {{ background: {c['background']}; color: {c['foreground']}; }}
        label, entry, text {{ color: {c['foreground']}; }}
        button, entry, searchentry, dropdown, list, row {{ background: {c['lighter_background']}; color: {c['foreground']}; }}
        button {{ background-image: none; border-color: alpha({c['foreground']}, 0.2); }}
        button:hover, row:hover {{ background: {c['selection']}; }}
        button:checked {{ background: {c['selection']}; outline: 1px solid {c['accent']}; }}
        button:focus-visible, entry:focus-within, searchentry:focus-within {{ outline: 2px solid {c['accent']}; }}
        popover > contents {{ border-radius: 10px; }}
        /* The selected-value row sits inside the button, not the menu. */
        dropdown > button row,
        dropdown > button row:hover,
        dropdown > button row:selected,
        dropdown > button row label {{
            background: transparent;
            box-shadow: none;
            border: none;
        }}
        dropdown popover listview {{ background: transparent; padding: 4px; }}
        dropdown popover row,
        dropdown popover row:first-child,
        dropdown popover row:last-child,
        dropdown popover row:hover,
        dropdown popover row:selected {{
            border-radius: 6px;
            margin: 2px;
            padding: 6px 8px;
            border: none;
            box-shadow: none;
        }}
        .dim-label {{ opacity: 0.75; }}
        .keyboard-map {{ background: {c['background']}; }}
        '''
        self.provider.load_from_data(css.encode())
        self.changed()
        return True
