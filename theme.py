"""Follow the installed Omarchy palette, falling back to GTK system settings."""
from pathlib import Path
import re
import tomllib
import json
from native_style import menu_tokens, SHELL_THEME
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, GLib

PALETTE = Path.home() / '.local/state/omarchy/current/theme/colors.toml'
DEFAULT = dict(background='#242424', foreground='#eeeeee', accent='#78aeed',
               lighter_background='#343434', selection='#454545', muted='#9a9a9a')

TOAST_CSS = """
.usage-meter trough { min-height: 4px; background: alpha(@theme_fg_color, .18); border: none; border-radius: 3px; }
.usage-meter progress { min-height: 4px; background: @theme_fg_color; border: none; border-radius: 3px; }
.hotkey-caps .shortcut-keycap { padding: 5px 8px; min-width: 18px; font-weight: 500; }
.shortcut-details-tooltip > contents { padding: 12px; }
.main-root { margin: 8px; }
.switch-row { border-radius: 8px; padding: 6px; }
.switch-row:hover { background: alpha(@theme_fg_color, 0.07); }
.switch-row:focus-visible { outline: 2px solid @accent_color; outline-offset: -2px; }

list.choice-menu { background: transparent; }
.shortcuts-app list.choice-menu > row { padding: 2px; min-height: 0; background: transparent; border-radius: 4px; }
.shortcuts-app list.choice-menu button { min-height: 0; min-width: 18px; padding: 2px 4px; }
.shortcuts-app list.choice-menu .count-badge { padding: 2px 6px; min-width: 16px; min-height: 0; border-radius: 10px; }
.feature-card { padding: 14px; border: 1px solid alpha(@theme_fg_color, 0.15); border-radius: 12px; }
.shortcuts-app expander.config-files { padding: 12px; border: 1px solid alpha(@theme_fg_color, 0.12); border-radius: 10px; background: alpha(@theme_fg_color, 0.025); }
.shortcuts-app expander.config-files > title { border-radius: 6px; padding: 4px; }
.shortcuts-app expander.config-files > title:hover { background: alpha(@theme_fg_color, 0.07); }
.shortcuts-app .chat-panel { border: none; outline: none; box-shadow: none; }
.shortcuts-app .chat-panel scrolledwindow, .shortcuts-app .chat-panel viewport { border: none; outline: none; box-shadow: none; }
.shortcuts-app paned.chat-splitter > separator, .shortcuts-app paned.content-splitter > separator { min-width: 8px; margin: 12px 4px; background-color: transparent; border: none; border-radius: 3px; box-shadow: none; background-image: linear-gradient(alpha(@theme_fg_color,.30), alpha(@theme_fg_color,.30)); background-size: 3px 48px; background-position: center; background-repeat: no-repeat; }
.shortcuts-app paned.chat-splitter > separator:hover, .shortcuts-app paned.content-splitter > separator:hover { background-image: linear-gradient(@accent_bg_color, @accent_bg_color); }
.shortcuts-app .markdown-table { padding: 10px; background: alpha(@theme_fg_color,.05); }
.shortcuts-app .markdown-code { padding: 10px; background: alpha(@theme_fg_color,.06); border-radius: 6px; }
.shortcuts-app .guide-side-preview { padding: 8px; }
.shortcuts-app .companion-editor { padding: 10px; border: 1px solid alpha(@theme_fg_color,.25); border-radius: 6px; }
.shortcuts-app paned > separator { background: transparent; background-image: none; box-shadow: none; border: none; min-width: 1px; }
.shortcuts-app .chat-panel .chat-input { border: 1px solid alpha(@theme_fg_color, 0.25); border-radius: 8px; }
.shortcuts-app button:disabled, .shortcuts-app dropdown:disabled,
.shortcuts-app entry:disabled, .shortcuts-app textview:disabled,
.shortcuts-app switch:disabled, .shortcuts-app checkbutton:disabled,
.shortcuts-app spinbutton:disabled, .shortcuts-app scale:disabled { opacity: .45; }
.shortcuts-app dropdown:disabled button:disabled, .shortcuts-app spinbutton:disabled button:disabled { opacity: 1; }
/* Reference-only shortcut rows stay readable; their action is not a form control. */
.shortcuts-app button.shortcut-reference:disabled { opacity: 1; }
.shortcuts-app .shortcut-skeleton { background: alpha(@theme_fg_color,.10); border-radius: 4px; }
.shortcuts-app .chat-input textview, .shortcuts-app .chat-input text { background: transparent; }
.shortcuts-app .chat-panel .chat-input:focus-within { border-color: @accent_bg_color; }
.shortcuts-app .scrim-scroll > undershoot, .shortcuts-app .scrim-scroll > overshoot { background: none; border: none; box-shadow: none; }
.shortcuts-app .chat-message { padding: 12px 14px; border-radius: 10px; }
.shortcuts-app .chat-user { background: alpha(@accent_color, .12); }
.shortcuts-app .chat-assistant { background: alpha(@theme_fg_color, .035); }
.shortcuts-app .chat-notice { background: alpha(@theme_fg_color, .07); }
.shortcuts-app .chat-queued { padding: 2px 8px; background: alpha(@accent_color, .08); border-radius: 6px; }
.shortcuts-app .chat-message .heading { font-size: 12px; opacity: .75; }
.shortcuts-app .chat-panel .suggestion { padding: 10px 12px; }
.shortcuts-app .config-path { font-family: monospace; font-size: 12px; }
.feature-preview { padding: 12px; border-radius: 8px; background: alpha(@theme_fg_color, 0.04); }
list.choice-menu > row:selected { background: alpha(@accent_color, 0.20); }
list.choice-menu > row:hover { background: alpha(@accent_color, 0.12); }

.shortcuts-app .column-shortcut { font-family: monospace; font-size: 16px; opacity: 1; }
.shortcuts-app listview.virtual-shortcuts { background: transparent; }
.shortcuts-app listview.virtual-shortcuts > row { padding: 0; background: transparent; border-bottom: 1px solid alpha(@theme_fg_color, 0.06); }
.shortcuts-app listview.virtual-shortcuts .shortcut-row > button.flat:hover { background: transparent; }
.shortcuts-app listview.virtual-shortcuts > row:selected { background: alpha(@accent_color, 0.14); }

tooltip .tooltip-category { border-radius: 10px; padding: 3px 8px; background: alpha(@theme_fg_color, 0.09); font-size: 11px; }

.shortcuts-app .linked > button:checked { outline: none; box-shadow: none; }
.shortcuts-app .linked > button:focus-visible { outline: none; box-shadow: inset 0 -2px alpha(@theme_fg_color, 0.5); }

window.shortcuts-app { border: 2px solid @theme_fg_color; border-radius: 0; }
.shortcuts-app .shortcut-row:focus { background: alpha(@accent_color, 0.14); outline: none; }

.shortcuts-app .linked > button { border-radius: 0; }
.shortcuts-app .linked > button:first-child { border-radius: 9px 0 0 9px; }
.shortcuts-app .linked > button:last-child { border-radius: 0 9px 9px 0; }

.shortcuts-app button.learned-toggle:checked { outline: none; border-color: transparent; box-shadow: none; background: transparent; }
.shortcuts-app button.learned-toggle:focus-visible { outline: 2px solid @accent_color; outline-offset: -2px; }

.shortcut-keycap { font-family: monospace; font-weight: 600; font-size: 12px; padding: 3px 7px; min-width: 12px; border-radius: 5px; border: 1px solid alpha(@theme_fg_color, 0.25); border-bottom-width: 2px; background: alpha(@theme_fg_color, 0.08); }

.shortcuts-app .category-card { border: 1px solid alpha(@theme_fg_color, 0.16); border-radius: 12px; background: alpha(@theme_fg_color, 0.025); }
.shortcuts-app button.category-header { min-height: 32px; padding: 10px 16px; border-radius: 11px; border: none; box-shadow: none; font-weight: 600; }
.shortcuts-app button.category-header:checked { border-radius: 11px 11px 0 0; border-bottom: 1px solid alpha(@theme_fg_color, 0.12); }
.shortcuts-app button.category-header:focus-visible { outline-offset: -3px; }
.shortcuts-app .category-card .shortcut-list { border: none; border-radius: 0 0 11px 11px; background: transparent; }
.shortcuts-app button.category-header:checked { outline: none; }
.shortcuts-app .count-badge { border-radius: 20px; padding: 3px 10px; min-width: 20px; background: alpha(@theme_fg_color, 0.10); font-size: 12px; font-weight: 700; }

button.preview-navigation:disabled { opacity: 0.3; background: transparent; border-color: transparent; box-shadow: none; }

.shortcuts-app .app-title { font-size: 23px; font-weight: 700; letter-spacing: -0.5px; }
.shortcuts-app button { border-radius: 9px; padding: 6px 10px; }
.shortcuts-app button.flat { background: transparent; border-color: transparent; box-shadow: none; }
.shortcuts-app button.flat:hover { background: alpha(@theme_fg_color, 0.07); }
.shortcuts-app searchentry { border-radius: 12px; padding: 8px 10px; }
.shortcuts-app flowboxchild { padding: 0; background: transparent; }
.shortcuts-app .shortcut-section > title { padding: 9px 2px; font-weight: 600; }
.shortcuts-app .shortcut-list { border-radius: 12px; border: 1px solid alpha(@theme_fg_color, 0.10); background: alpha(@theme_fg_color, 0.025); }
.shortcuts-app .shortcut-list > row { background: transparent; border-bottom: 1px solid alpha(@theme_fg_color, 0.06); padding: 0; }
.shortcuts-app .shortcut-list > row:last-child { border-bottom: none; }
.shortcuts-app .shortcut-row { padding: 9px 10px; }
.shortcuts-app .small-action { min-width: 22px; min-height: 22px; padding: 4px; }
.shortcuts-app .shortcut-key { font-family: monospace; font-size: 11px; opacity: 0.65; }
.shortcuts-app .dim-label { font-size: 12px; }

.copy-toast {
    background: @theme_bg_color;
    color: @theme_fg_color;
    border: 1px solid alpha(@theme_fg_color, 0.25);
    border-radius: 12px;
    padding: 14px 18px;
    box-shadow: 0 4px 16px alpha(black, 0.22);
}
"""

LOOKS = json.loads(Path(__file__).with_name('looks.json').read_text())

def detected_look():
    return 'square' if Path('/usr/share/omarchy').is_dir() or (Path.home()/'.local/share/omarchy').is_dir() else 'rounded'

def resolve_look(name):
    if name == 'square': name = 'square'
    return detected_look() if name == 'system' else name if name in LOOKS else detected_look()

class SystemTheme:
    def __init__(self, changed=lambda: None):
        self.provider = Gtk.CssProvider()
        self.colors = dict(DEFAULT)
        self.changed = changed
        self.last = None
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self.provider,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        settings = Gtk.Settings.get_default()
        for name in ('gtk-theme-name', 'gtk-application-prefer-dark-theme', 'gtk-font-name'):
            settings.connect('notify::' + name, self.desktop_changed)
        self.poll()
        self.timer = GLib.timeout_add_seconds(1, self.poll)

    def typography(self, values):
        if values.get('system_typography', True):
            if getattr(self, 'current_look', '') == 'square':
                tokens = menu_tokens(); return tokens['family'], tokens['size']
            from gi.repository import Pango
            desc = Pango.FontDescription.from_string(Gtk.Settings.get_default().get_property('gtk-font-name'))
            return desc.get_family(), desc.get_size()/Pango.SCALE*96/72
        return values['font_family'], values['font_size']

    def menu_background(self):
        mode = getattr(self, 'preferences', {}).get('theme', 'system')
        if mode in ('dark','light'): return '#1e1e2e' if mode == 'dark' else '#eff1f5'
        return menu_tokens()['menu'].get('background', self.colors['background'])

    def set_preferences(self, values):
        self.preferences = dict(values)
        settings = Gtk.Settings.get_default()
        if not hasattr(self, 'system_animations'): self.system_animations = settings.get_property('gtk-enable-animations')
        animation = values.get('app_animations', 'system')
        settings.set_property('gtk-enable-animations', self.system_animations if animation == 'system' else animation == 'on')
        if not hasattr(self, 'preferences_provider'):
            self.preferences_provider = Gtk.CssProvider()
            Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self.preferences_provider,
                                                      Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 2)
        family = str(values.get('font_family', 'sans-serif')).replace('"', '').replace('\\', '')
        size = max(9, min(28, int(values.get('font_size', 14))))
        native = getattr(self, 'current_look', '') == 'square'
        tokens = menu_tokens()
        family, size = self.typography(values)
        css = f'.shortcut-name, .column-shortcut {{ font-family: "{family}"; font-size: {size}px; }}'
        css += '.shortcuts-app .main-search image.right { margin-right: 12px; margin-left: 8px; }'
        if values.get('app_animations') == 'off':
            css += '.shortcuts-app * { transition: none; animation: none; }'
        if values.get('compact'):
            css += '.shortcut-row { padding: 0; } .shortcut-row button { padding-top: 3px; padding-bottom: 3px; min-height: 0; }'
        mode = values.get('theme', 'system')
        if mode in ('dark','light'):
            background, foreground, surface = ('#1e1e2e','#cdd6f4','#313244') if mode == 'dark' else ('#eff1f5','#303446','#dce0e8')
            css += f"""
            .shortcuts-app, popover > contents, tooltip {{ background: {background}; color: {foreground}; }}
            .shortcuts-app label, .shortcuts-app entry, .shortcuts-app text {{ color: {foreground}; }}
            .shortcuts-app button, .shortcuts-app entry, .shortcuts-app searchentry,
            .shortcuts-app list, .shortcuts-app listview, .shortcuts-app row,
            popover listview, popover row {{ background: {surface}; color: {foreground}; }}
            .shortcuts-app .virtual-shortcuts, .shortcuts-app .virtual-shortcuts > row, .shortcuts-app button.flat {{ background: transparent; }}
            .shortcuts-app switch {{ background: {surface}; border-color: alpha({foreground}, .4); }}
            .shortcuts-app switch slider {{ background: {foreground}; }}
            .shortcuts-app switch:checked {{ background: #3578d4; border-color: #3578d4; }}
            .shortcuts-app switch:checked slider {{ background: #ffffff; }}
            .shortcuts-app spinbutton, .shortcuts-app spinbutton text {{ background: {surface}; color: {foreground}; }}
            .shortcuts-app paned > separator {{ background: transparent; min-width: 1px; }}
            .shortcuts-app paned.chat-splitter > separator, .shortcuts-app paned.content-splitter > separator {{ min-width: 8px; background-color: transparent; background-image: linear-gradient(alpha({foreground}, .30), alpha({foreground}, .30)); background-size: 3px 48px; background-position: center; background-repeat: no-repeat; }}
            .shortcuts-app paned.chat-splitter > separator:hover, .shortcuts-app paned.content-splitter > separator:hover {{ background-image: linear-gradient(#3578d4,#3578d4); }}
            .shortcuts-app .markdown-table, .shortcuts-app .markdown-code {{ background: alpha({foreground}, .06); }}
            .shortcuts-app .companion-editor, .shortcuts-app .companion-editor text {{ background: {surface}; color: {foreground}; border-color: alpha({foreground}, .25); }}
            .shortcuts-app .feature-preview, .shortcuts-app .count-badge {{ background: alpha({foreground}, .10); }}
            .shortcuts-app .feature-card, .shortcuts-app .chat-input {{ border-color: alpha({foreground}, .22); }}
            .shortcuts-app .chat-input {{ background: {surface}; }}
            .shortcuts-app button:checked {{ background: alpha(#3578d4, .20); border-color: #3578d4; }}
            .shortcuts-app .linked > button:checked {{ box-shadow: inset 0 -2px #3578d4; }}
            tooltip .shortcut-keycap {{ background: alpha({foreground}, .08); border-color: alpha({foreground}, .3); }}
            popover label, tooltip label {{ color: {foreground}; }}
            """
            if getattr(self, 'current_look', '') == 'neo-brutalism':
                css += f'.shortcuts-app button, .shortcuts-app entry, .shortcuts-app searchentry, .shortcuts-app .feature-card, popover > contents {{ border-color: {foreground}; box-shadow: 3px 3px {background}, 7px 7px #3578d4; }} .shortcuts-app button.flat {{ border-color: transparent; box-shadow: none; }}'
        if mode == 'system':
            from native_style import border_css
            css += border_css()
        if native:
            menu = tokens['menu']
            bg = self.menu_background()
            fg = menu.get('text', self.colors['foreground']) if mode == 'system' else foreground
            selected = menu.get('selected-text', self.colors['accent'])
            selected_bg = menu.get('selected-background', fg)
            alpha = float(menu.get('selected-background-alpha', .08))
            menu_family = tokens['family'].replace('"','')
            css += f"""
            .shortcuts-app {{ font-family: "{menu_family}"; font-size: {tokens['size']}px; background: {bg}; color: {fg}; }}
            .shortcuts-app .main-root {{ margin: {tokens['padding']}px; }}
            .shortcuts-app .main-status {{ font-size: 10px; opacity: .65; }}
            .shortcuts-app .main-toolbar {{ min-height: {tokens['header']}px; }}
            .shortcuts-app .main-search, .shortcuts-app .main-search:focus-within {{ background: transparent; border: none; outline: none; box-shadow: none; padding: 0; min-height: {tokens['header']}px; border-radius: 0; font-size: {tokens['size']}px; }}
            .shortcuts-app .main-search placeholder {{ opacity: .58; }}
            .shortcuts-app .main-toolbar button {{ background: transparent; border-color: transparent; box-shadow: none; padding: 0 8px; }}
            .shortcuts-app .main-toolbar button:hover {{ background: alpha({selected_bg}, {alpha}); }}
            .shortcuts-app .main-root .virtual-shortcuts > row {{ border: none; margin-bottom: {tokens['row_gap']}px; }}
            .shortcuts-app .main-root .shortcut-row {{ padding: 0; min-height: {tokens['row']}px; }}
            .shortcuts-app .main-root .shortcut-row > button.flat {{ padding: 0 {tokens['inset']}px; min-height: {tokens['row']}px; border: none; border-radius: 0; }}
            .shortcuts-app .main-root .shortcut-row > button.flat label {{ font-weight: 500; }}
            .shortcuts-app .main-root .virtual-shortcuts > row:selected {{ background: alpha({selected_bg}, {alpha}); }}
            .shortcuts-app .main-root .virtual-shortcuts > row:selected label {{ color: {selected}; }}
            .shortcuts-app .empty-shortcuts {{ min-height: 50px; color: {fg}; }}
            .shortcuts-app .empty-shortcuts label {{ opacity: .7; font-size: {tokens['title']}px; }}
            .shortcuts-app .empty-shortcuts image {{ color: {selected}; opacity: .8; }}
            """
        if values.get('compact'):
            css += '.shortcuts-app .main-root .shortcut-row, .shortcuts-app .main-root .shortcut-row > button.flat { min-height: 30px; }'
        self.preferences_provider.load_from_data(css.encode())

    def set_look(self, name):
        name = resolve_look(name)
        self.current_look = name
        if not hasattr(self, 'look_provider'):
            self.look_provider = Gtk.CssProvider()
            Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self.look_provider,
                                                      Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
        css = """
        .shortcuts-app, tooltip { font-family: monospace; }
        .shortcuts-app button, .shortcuts-app entry, .shortcuts-app searchentry,
        .shortcuts-app switch, .shortcuts-app switch slider, .shortcuts-app .feature-card,
        .shortcuts-app .category-card, .shortcuts-app .category-header,
        .shortcuts-app .feature-preview, .shortcuts-app .count-badge,
        popover > contents, tooltip, .shortcut-keycap { border-radius: 0; }
        """ if name == 'square' else ""
        tokens = LOOKS.get(name, LOOKS['rounded'])
        family = tokens['font'].replace('"', '')
        radius = max(0, int(tokens['radius']))
        css += f"""
        .shortcuts-app {{ font-family: "{family}"; }}
        .shortcuts-app button, .shortcuts-app entry, .shortcuts-app searchentry,
        .shortcuts-app .feature-card, .shortcuts-app .category-card,
        popover > contents {{ border-radius: {radius}px; }}
        .shortcuts-app .chat-message, .shortcuts-app .chat-input {{ border-radius: {radius}px; }}
        .shortcuts-app spinbutton {{ border: 1px solid alpha(@theme_fg_color, .25); border-radius: {radius}px; }}
        .shortcuts-app spinbutton > text {{ border: none; box-shadow: none; padding: 5px 8px; }}
        .shortcuts-app spinbutton > button {{ border: none; border-radius: 0; box-shadow: none; }}
        .shortcuts-app spinbutton > button:last-child {{ border-radius: 0 {radius}px {radius}px 0; }}
        .shortcuts-app .linked > button {{ border-radius: 0; }}
        .shortcuts-app .linked > button:first-child {{ border-radius: {radius}px 0 0 {radius}px; }}
        .shortcuts-app .linked > button:last-child {{ border-radius: 0 {radius}px {radius}px 0; }}
        .shortcuts-app .linked > button:only-child {{ border-radius: {radius}px; }}
        .shortcuts-app .linked > button:checked {{ background: alpha(@accent_bg_color, .25); box-shadow: inset 0 -2px @accent_bg_color; }}
        """
        css += f"""
        .shortcuts-app switch {{ background: alpha(@theme_fg_color, .08); border: 1px solid alpha(@theme_fg_color, .4); border-radius: {20 if radius else 0}px; }}
        .shortcuts-app switch:checked {{ background: @accent_bg_color; border-color: @accent_bg_color; }}
        .shortcuts-app switch slider {{ background: @theme_fg_color; border: none; border-radius: {20 if radius else 0}px; }}
        .shortcuts-app switch:checked slider {{ background: white; }}
        .shortcuts-app .preference-row {{ padding-left: 0; padding-right: 0; }}
        """
        if name == 'neo-brutalism':
            css += '''
            .shortcuts-app button, .shortcuts-app entry, .shortcuts-app searchentry,
            .shortcuts-app .feature-card, popover > contents {
                border: 2px solid @theme_fg_color; box-shadow: 3px 3px @theme_bg_color, 7px 7px @accent_bg_color; margin-right: 8px; margin-bottom: 8px;
            }
            .shortcuts-app button.flat { box-shadow: none; border-color: transparent; margin: 0; }
            .shortcuts-app button:active { box-shadow: 1px 1px @theme_bg_color, 3px 3px @accent_bg_color; }
            '''
        self.look_provider.load_from_data(css.encode())

    def desktop_changed(self, *_):
        if not PALETTE.exists():
            self.last = None
            GLib.idle_add(self.poll)

    def poll(self):
        try:
            data = PALETTE.read_bytes()
        except OSError:
            data = b''
        try: shell_data = SHELL_THEME.read_bytes()
        except OSError: shell_data = b''
        signature = (data, shell_data)
        if signature == self.last:
            return True
        self.last = signature
        try:
            values = tomllib.loads(data.decode())
        except (ValueError, UnicodeError):
            values = {}
        colors = {k: v for k, v in values.items() if isinstance(v, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', v)}
        settings = Gtk.Settings.get_default()
        if not colors:
            self.provider.load_from_data(TOAST_CSS.encode())
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
        @define-color theme_bg_color {c['background']};
        @define-color theme_fg_color {c['foreground']};
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
        dropdown {{ background: transparent; }}
        dropdown popover > contents {{ padding: 4px; }}
        dropdown popover listview {{ background: transparent; padding: 0; }}
        dropdown popover row,
        dropdown popover row:first-child,
        dropdown popover row:last-child {{
            background: transparent;
            border-radius: 4px;
            margin: 0;
            padding: 8px 12px;
            border: none;
            box-shadow: none;
        }}
        dropdown popover row:selected {{ background: alpha({c['accent']}, 0.12); }}
        dropdown popover row:hover,
        dropdown popover row:focus {{
            background: alpha({c['accent']}, 0.22);
            outline: none;
        }}
        dropdown popover row image {{ margin-left: 16px; }}
        .dim-label {{ opacity: 0.75; }}
        .keyboard-map {{ background: {c['background']}; }}
        '''
        self.provider.load_from_data((TOAST_CSS + css + f' .copy-toast {{ background: {c["lighter_background"]}; }}').encode())
        if hasattr(self, 'preferences'): self.set_preferences(self.preferences)
        self.changed()
        return True
