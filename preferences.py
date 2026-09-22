"""App-wide presentation preferences and a single settings surface."""
from gi.repository import Gtk, Gdk
from theme import LOOKS, detected_look
import localization
import settings_ui
from shortcut_data import make_switch_row, action_tooltip

DEFAULTS = dict(chat_connections={}, remember_search=False, shortcut_tooltips=False, tooltip_delay=700, language='system', theme='system', app_icons=False, action_icons=False,
                system_typography=True, font_family='sans-serif', font_size=14, compact=False,
                global_hotkey='SUPER + SHIFT + K', window_animations='off', app_animations='system', agent_provider='auto',
                guide_preview_side=False, guide_autosave=False, chat_snippets=False, chat_vignette=True,
                chat_memory_enabled=False, chat_instructions_enabled=False, chat_instructions='', chat_token_usage=False)
LANGUAGES = [('system', 'System'), ('en', 'English'), ('de', 'Deutsch'), ('fr', 'Français'),
             ('es', 'Español'), ('uk', 'Українська'), ('hu', 'Magyar'),
             ('ko', '한국어'), ('ja', '日本語'), ('zh_CN', '简体中文')]

def show(app):
    existing = getattr(app, 'preferences_window', None)
    if existing:
        existing.present()
        return
    app.menu_button.popdown()
    app.app_menu_button.popdown()
    window = Gtk.Window(application=app, transient_for=app.window, modal=True,
                        title='Settings', default_width=780, default_height=650)
    app.preferences_window = window
    window.add_css_class('shortcuts-app')
    body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16,
                   margin_top=20, margin_bottom=20, margin_start=20, margin_end=20)
    settings_ui.header(body, window, 'Settings')
    content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
    scroll.set_child(content)
    body.append(scroll)
    controls = {}
    def section(title):
        return settings_ui.section(content, title)
    def row(label, control):
        return settings_ui.row(content, label, control)
    def choice(label, key, values):
        control = Gtk.DropDown.new_from_strings([name for value, name in values])
        current = app.preferences.get(key, DEFAULTS.get(key))
        control.set_selected(next((i for i,(value,_) in enumerate(values) if value == current), 0))
        control.connect('notify::selected', lambda widget,*_: None if getattr(window, '_refreshing_system_choices', False) else app.set_preference(key, values[widget.get_selected()][0]))
        row(label, control)
        controls[key] = control
    def switch(label, key):
        control = Gtk.Switch(active=bool(app.preferences[key]))
        row(label, control)
        control.connect('notify::active', lambda widget,*_: app.set_preference(key, widget.get_active()))
        controls[key] = control
    section('General')
    choice('Language', 'language', LANGUAGES)
    from shortcut_manager import ShortcutPicker, GROUPS
    hotkey = ShortcutPicker(groups=GROUPS + ['CTRL', 'CTRL+SHIFT', 'ALT', 'ALT+SHIFT', 'CTRL+ALT', 'CTRL+ALT+SHIFT'],
                            keys=list('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789') + [f'F{i}' for i in range(1,13)] + ['SPACE', 'RETURN'],
                            error=lambda message: note.set_text(message))
    hotkey.set_chord(app.preferences['global_hotkey'])
    controls['global_hotkey'] = hotkey
    hotkey_row = Gtk.Box(spacing=8)
    hotkey_row.append(hotkey)
    apply_hotkey = Gtk.Button(label='Apply')
    hotkey_row.append(apply_hotkey)
    row('Global shortcut', hotkey_row)
    note = Gtk.Label(label='Default: Win+Shift+K. Win+K is a convenient alternative, but replaces the Omarchy shortcut.',
                     xalign=0, wrap=True, max_width_chars=65)
    note.add_css_class('dim-label')
    content.append(note)
    def apply_binding(*_):
        try:
            from global_shortcut import apply
            value = apply(hotkey.get_chord())
            app.set_preference('global_hotkey', value)
            hotkey.set_chord(value)
            note.set_text('Global shortcut updated.')
        except (OSError, ValueError, RuntimeError) as error:
            note.set_text(str(error))
    apply_hotkey.connect('clicked', apply_binding)
    section('Search')
    switch('Remember last search', 'remember_search')
    section('Tooltips')
    switch('Show shortcut details on hover', 'shortcut_tooltips')
    delay = Gtk.SpinButton.new_with_range(0, 5000, 100)
    delay.set_value(app.preferences['tooltip_delay'])
    delay.connect('value-changed', lambda widget: app.set_preference('tooltip_delay', widget.get_value_as_int()))
    row('Shortcut tooltip delay (milliseconds)', delay)
    controls['tooltip_delay'] = delay
    section('Appearance')
    choice('Theme', 'theme', [('system','Follow system'), ('dark','Dark'), ('light','Light')])
    look = Gtk.DropDown.new_from_strings([value['name'] for value in LOOKS.values()])
    look.set_selected(list(LOOKS).index(app.look if app.feature_enabled('appearance') else 'system'))
    def style_changed(widget, *_):
        if getattr(window, '_refreshing_system_choices', False): return
        app.set_feature('appearance', True)
        app.look_picker.set_selected(widget.get_selected())
    look.connect('notify::selected', style_changed)
    row('Style', look)
    controls['look'] = look
    choice('Window animations', 'window_animations', [('system', 'Follow system'), ('on', 'Enabled'), ('off', 'Disabled')])
    choice('In-app animations', 'app_animations', [('system', 'Follow system'), ('on', 'Enabled'), ('off', 'Disabled')])
    section('Shortcut list')
    switch('Use system typography', 'system_typography')
    switch('Compact view', 'compact')
    switch('Desktop and web app icons', 'app_icons')
    switch('Action icons', 'action_icons')
    font = Gtk.FontButton()
    font.set_use_size(False)
    font.set_level(Gtk.FontChooserLevel.FAMILY)
    controls['font'] = font
    family, resolved_size = app.system_theme.typography(app.preferences)
    font.set_font(f'{family} {resolved_size}')
    def font_changed(widget):
        description = widget.get_font_desc()
        controls['system_typography'].set_active(False)
        app.set_preference('font_family', description.get_family())
        app.set_preference('font_size', max(9, min(28, round(description.get_size()/1024))))
    font.connect('font-set', font_changed)
    row('Label font', font)
    size = Gtk.SpinButton.new_with_range(9, 28, 1)
    size.set_value(resolved_size)
    def size_changed(widget):
        if getattr(window, '_refreshing_font', False): return
        controls['system_typography'].set_active(False)
        app.set_preference('font_size', widget.get_value_as_int())
    size.connect('value-changed', size_changed)
    row('Label size', size)
    def sync_typography(*_):
        window._refreshing_font = True
        family, resolved_size = app.system_theme.typography(app.preferences)
        font.set_font(f'{family} {resolved_size}')
        size.set_value(resolved_size)
        enabled = not controls['system_typography'].get_active()
        font.set_sensitive(enabled); size.set_sensitive(enabled)
        window._refreshing_font = False
    controls['system_typography'].connect('notify::active', sync_typography)
    sync_typography()
    stock = Gtk.Button(label='Use Omarchy-style typography')
    def stock_typography(*_):
        app.set_preference('font_family', 'monospace')
        app.set_preference('font_size', 14)
        for key in ('app_icons','action_icons'):
            controls[key].set_active(False)
        size.set_value(14)
        font.set_font('monospace 14')
        controls['system_typography'].set_active(True)
    stock.connect('clicked', stock_typography)
    content.append(stock)
    if app.feature_enabled('guide'):
        section('Keyboard guide')
        guide = Gtk.Button(label='Keyboard guide settings')
        guide.connect('clicked', lambda *_: app.show_guide())
        content.append(guide)
    if app.feature_enabled('agent'):
        section('Agent chat')
        companion = Gtk.Button(label='AI companion settings')
        companion.connect('clicked', lambda *_: __import__('companion').show(app, getattr(app, 'chat_panel', None)))
        content.append(companion)
        from chat import available_agents, PROVIDERS
        choice('Default agent', 'agent_provider', [('auto', 'Automatic')] + [(key, PROVIDERS[key]) for key in available_agents(app.preferences)])
    window.controls = controls
    def resolve_choices():
        window._refreshing_system_choices = True
        import json, os, subprocess
        settings = Gtk.Settings.get_default()
        animations = settings.get_property('gtk-enable-animations')
        if os.environ.get('HYPRLAND_INSTANCE_SIGNATURE') and os.environ.get('GDK_BACKEND') != 'broadway':
            try:
                value = json.loads(subprocess.check_output(['hyprctl','-j','getoption','animations:enabled'], timeout=1))
                animations = value.get('bool', animations)
            except (OSError, ValueError, subprocess.SubprocessError): pass
        background = app.system_theme.colors['background']
        dark = sum(int(background[i:i+2],16) for i in (1,3,5))/3 < 128
        for key, resolved in [('language', localization.LANGUAGE_NAMES[localization.detected_language()]), ('look', 'Omarchy → ' + localization.text('Square') if detected_look() == 'square' else LOOKS[detected_look()]['name']), ('theme', 'Dark' if dark else 'Light'),
                              ('window_animations', 'Enabled' if animations else 'Disabled'),
                              ('app_animations', 'Enabled' if settings.get_property('gtk-enable-animations') else 'Disabled')]:
            control = controls[key]
            model = control.get_model()
            # Splice only the displayed label; stable setting values stay separate.
            model.splice(0, 1, [localization.text('System ({value})').format(value=localization.text(resolved))])
        window._refreshing_system_choices = False
    resolve_choices()
    window.refresh_system_choices = resolve_choices
    window.set_child(body)
    keys = Gtk.EventControllerKey()
    keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
    def key_pressed(_controller, key, _code, state):
        if hotkey.capture.get_active():
            return hotkey.capture_key(_controller, key, _code, state)
        if key == Gdk.KEY_Escape:
            window.close()
            return True
        return False
    keys.connect('key-pressed', key_pressed)
    window.add_controller(keys)
    window.connect('close-request', lambda *_: setattr(app, 'preferences_window', None) or False)
    window.present()
