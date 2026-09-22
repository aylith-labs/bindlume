"""Shortcut matching and plain-text hover details."""
import re
import textwrap

MODIFIERS = {'SUPER', 'CTRL', 'SHIFT', 'ALT'}
ALIASES = {'CONTROL': 'CTRL', 'WIN': 'SUPER', 'META': 'SUPER', 'ENTER': 'RETURN',
           'ESC': 'ESCAPE', 'PGUP': 'PRIOR', 'PAGEUP': 'PRIOR', 'PGDN': 'NEXT',
           'PAGEDOWN': 'NEXT', 'DEL': 'DELETE', 'INS': 'INSERT', ' ': 'SPACE'}

def canonical(key):
    key = key.upper()
    return ALIASES.get(key, key)

def split_shortcut(shortcut):
    parts = shortcut.rsplit(' + ', 1)
    if len(parts) == 1:
        return frozenset(), canonical(shortcut.strip())
    return frozenset(canonical(m) for m in parts[0].split()), canonical(parts[1].strip())

def matches_query(item, query):
    """@w matches a whole base key; @ctrl+w requires Ctrl, allowing extra mods."""
    query = query.strip().replace('\\@', '@')
    modifiers, key = split_shortcut(item['key'])
    text = ' '.join(item.get(k, '') for k in ('key', 'name', 'group', 'topic', 'dispatcher', 'arg')).casefold()
    for token in query.split():
        if token.startswith('@'):
            wanted = [canonical(p) for p in re.split(r'\+', token[1:]) if p]
            if not wanted:
                continue
            required = set(wanted) & MODIFIERS
            base = [p for p in wanted if p not in MODIFIERS]
            if not required.issubset(modifiers) or any(p != key for p in base):
                return False
        elif token.casefold() not in text:
            return False
    return True

def details(item):
    return (f"{item['key']}\n\nDescription: {item['name']}\nCategory: {item['group']}\n"
            f"Dispatcher: {item['dispatcher'] or '(unavailable)'}\nArguments: {item['arg'] or '(none)'}")


def tooltip_widget(items, note='', technical=True):
    """Native tooltip with aligned field labels and literal, wrapping values."""
    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import Gtk
    # GtkTooltip can measure height-for-width labels at their minimum width,
    # reserving a tall popup even after the content receives its natural width.
    # Explicit display-only line breaks give it a stable, compact requisition.
    def display_lines(value, width=60):
        return '\n'.join(textwrap.fill(line, width=width, replace_whitespace=False,
                                       expand_tabs=False, break_on_hyphens=False)
                         for line in value.split('\n'))
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                  valign=Gtk.Align.START, vexpand=False,
                  margin_top=6, margin_bottom=6, margin_start=8, margin_end=8)
    for item_index, item in enumerate(items[:6]):
        if item_index:
            box.append(Gtk.Separator(margin_top=4, margin_bottom=4))
        header = Gtk.Box(spacing=20)
        heading = Gtk.Label(label=display_lines(item.get('display_key', item['key']), 45), xalign=0, hexpand=True)
        heading.add_css_class('heading')
        header.append(heading)
        kind = item.get('kind', 'action')
        if kind != 'action':
            badge = Gtk.Label(label=item['group'], valign=Gtk.Align.CENTER)
            badge.add_css_class('tooltip-category')
            header.append(badge)
        box.append(header)
        description = Gtk.Label(label=display_lines(item['name'], 52), xalign=0, yalign=0)
        box.append(description)
        grid = Gtk.Grid(column_spacing=12, row_spacing=4, valign=Gtk.Align.START, vexpand=False)
        fields = []
        if technical:
            fields = [('Dispatcher', item['dispatcher'] or 'Unavailable'), ('Arguments', item['arg'] or 'None')]
        for index, (name, value) in enumerate(fields):
            label = Gtk.Label(label=name, xalign=1, yalign=0, width_chars=12, valign=Gtk.Align.START)
            label.add_css_class('dim-label')
            content = Gtk.Label(label=display_lines(value), xalign=0, yalign=0,
                                wrap=False, valign=Gtk.Align.START, vexpand=False)
            if name in ('Dispatcher', 'Arguments'):
                content.add_css_class('monospace')
            grid.attach(label, 0, index, 1, 1)
            grid.attach(content, 1, index, 1, 1)
        box.append(grid)
    if len(items) > 6:
        box.append(Gtk.Label(label=f'{len(items) - 6} more actions — click the key to see all.', xalign=0))
    if note:
        label = Gtk.Label(label=display_lines(note, 72), xalign=0, wrap=False)
        label.add_css_class('dim-label')
        box.append(label)
    return box


def attach_tooltip(widget, item, note='', preferences=lambda: {}):
    """Non-interactive hover details with an explicit, app-owned delay."""
    from gi.repository import Gtk, GLib
    state = {'timer': None, 'popover': None, 'hovered': False}
    def close(*_):
        state['hovered'] = False
        if state['timer'] is not None:
            GLib.source_remove(state['timer']); state['timer'] = None
        if state['popover'] is not None:
            state['popover'].popdown(); state['popover'].unparent(); state['popover'] = None
    def reveal():
        state['timer'] = None
        if not state['hovered'] or not widget.get_mapped() or not preferences().get('shortcut_tooltips', False): return False
        popover = Gtk.Popover(autohide=False, has_arrow=False, can_focus=False, can_target=False)
        popover.add_css_class('shortcut-details-tooltip')
        popover.set_child(tooltip_widget([item], note))
        popover.set_parent(widget)
        state['popover'] = popover
        popover.popup()
        return False
    def enter(*_):
        close()
        if not preferences().get('shortcut_tooltips', False): return
        state['hovered'] = True
        state['timer'] = GLib.timeout_add(max(0, int(preferences().get('tooltip_delay', 700))), reveal)
    motion = Gtk.EventControllerMotion()
    motion.connect('enter', enter); motion.connect('leave', close)
    widget.add_controller(motion)
    widget.connect('unmap', close)
    widget.shortcut_tooltip = state
    widget.shortcut_tooltip_motion = motion
    widget.close_shortcut_tooltip = close


def action_tooltip(widget, text):
    """Show an action description and separate, styled accelerator keycaps."""
    from gi.repository import Gtk
    match = re.search(r' \(([^()]*)\)$', text)
    if not match:
        widget.set_tooltip_text(text)
        return
    description, shortcut = text[:match.start()], match.group(1)
    widget._action_tooltip = (description, shortcut)
    widget.set_has_tooltip(True)
    if getattr(widget, '_action_tooltip_connected', False):
        return
    widget._action_tooltip_connected = True
    def show(_widget, _x, _y, _keyboard, tooltip):
        description, shortcut = widget._action_tooltip
        from localization import text as translated
        description = translated(description)
        box = Gtk.Box(spacing=14, margin_top=4, margin_bottom=4,
                      margin_start=6, margin_end=6, halign=Gtk.Align.START)
        box.append(Gtk.Label(label=description, xalign=0, wrap=True, max_width_chars=55))
        keys = Gtk.Box(spacing=4, valign=Gtk.Align.CENTER, halign=Gtk.Align.START)
        for key in shortcut.split('+'):
            label = Gtk.Label(label=key)
            label.add_css_class('shortcut-keycap')
            keys.append(label)
        box.append(keys)
        tooltip.set_custom(box)
        return True
    widget.connect('query-tooltip', show)


def reveal_indicators_on_hover(row, indicators):
    """Reserve control space; reveal unset states on pointer or keyboard focus."""
    from gi.repository import Gtk
    hovered = False
    focus = Gtk.EventControllerFocus()
    def update():
        for widget, active in indicators:
            widget.set_opacity(1 if active or hovered or focus.contains_focus() else 0)
    def hover(value):
        nonlocal hovered
        hovered = value
        update()
    motion = Gtk.EventControllerMotion()
    motion.connect('enter', lambda *_: hover(True))
    motion.connect('leave', lambda *_: hover(False))
    focus.connect('enter', lambda *_: update())
    focus.connect('leave', lambda *_: update())
    row.add_controller(motion)
    row.add_controller(focus)
    row.refresh_indicators = update
    row.reveal_indicators = hover
    row.indicators = indicators
    update()


def make_switch_row(row, switch):
    """Give label and switch one hit target and one keyboard focus stop."""
    from gi.repository import Gtk, Gdk
    if getattr(row, '_switch_row_control', None) is switch: return row
    row._switch_row_control = switch
    row.add_css_class('switch-row')
    row.set_focusable(True)
    switch.set_focusable(False)
    if hasattr(switch, '_action_tooltip'):
        description, shortcut = switch._action_tooltip
        action_tooltip(row, f'{description} ({shortcut})')
    elif switch.get_tooltip_text():
        row.set_tooltip_text(switch.get_tooltip_text())
    click = Gtk.GestureClick(button=1)
    click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
    def enabled():
        return row.is_sensitive() and switch.is_sensitive()
    def pointer_pressed(gesture, *_):
        if enabled():
            row.grab_focus()
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)
    click.connect('pressed', pointer_pressed)
    def released(_gesture, _count, x, y):
        # Event coordinates include CSS padding outside the content dimensions.
        # Use GTK's hit test so the complete painted hover area is clickable.
        if enabled() and row.contains(x, y):
            switch.set_active(not switch.get_active())
    click.connect('released', released)
    row.add_controller(click)
    keys = Gtk.EventControllerKey()
    def pressed(_controller, key, _code, state):
        if enabled() and key in (Gdk.KEY_space, Gdk.KEY_Return, Gdk.KEY_KP_Enter) and not (state & Gtk.accelerator_get_default_mod_mask()):
            switch.set_active(not switch.get_active())
            return True
        return False
    keys.connect('key-pressed', pressed)
    row.add_controller(keys)
    return row


def hotkey_caps(shortcut):
    """Semantic keycaps; preserve literal plus keys and alternative chords."""
    from gi.repository import Gtk
    box = Gtk.Box(spacing=4, halign=Gtk.Align.END, valign=Gtk.Align.CENTER)
    box.add_css_class('hotkey-caps')
    for alternative_index, alternative in enumerate(shortcut.split(' / ')):
        if alternative_index: box.append(Gtk.Label(label='/'))
        parts = alternative.split('+')
        if alternative.endswith('+'):
            parts = parts[:-2] + ['+']
        for key in filter(None, (part.strip() for part in parts)):
            label = Gtk.Label(label=key)
            label.add_css_class('shortcut-keycap')
            box.append(label)
    return box
