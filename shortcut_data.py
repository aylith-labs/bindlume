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
    text = ' '.join(item.get(k, '') for k in ('key', 'name', 'group', 'dispatcher', 'arg')).casefold()
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
    for item in items[:6]:
        heading = Gtk.Label(label=item['key'], xalign=0)
        heading.add_css_class('heading')
        box.append(heading)
        grid = Gtk.Grid(column_spacing=12, row_spacing=4, valign=Gtk.Align.START, vexpand=False)
        fields = [('Description', item['name']), ('Category', item['group'])]
        if technical:
            fields += [('Dispatcher', item['dispatcher'] or 'Unavailable'), ('Arguments', item['arg'] or 'None')]
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


def attach_tooltip(widget, item, note=''):
    widget.set_has_tooltip(True)
    def show(_widget, _x, _y, _keyboard, tooltip):
        tooltip.set_custom(tooltip_widget([item], note))
        return True
    widget.connect('query-tooltip', show)
