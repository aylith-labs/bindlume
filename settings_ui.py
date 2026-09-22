"""Shared GTK settings components used by app and keyboard-guide preferences."""
from gi.repository import Gtk
from shortcut_data import make_switch_row, action_tooltip


def section(content, title):
    label = Gtk.Label(label=title, xalign=0, margin_top=8)
    label.add_css_class('heading')
    content.append(label)
    return label


def row(content, title, control, description=None):
    box = Gtk.Box(spacing=16)
    box.add_css_class('preference-row')
    labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, hexpand=True)
    label = Gtk.Label(label=title, xalign=0, wrap=True)
    labels.append(label)
    if description:
        detail = Gtk.Label(label=description, xalign=0, wrap=True, max_width_chars=48)
        detail.add_css_class('dim-label')
        labels.append(detail)
    box.append(labels)
    control.set_valign(Gtk.Align.CENTER)
    box.append(control)
    content.append(box)
    if isinstance(control, Gtk.Switch): make_switch_row(box, control)
    return box


def header(body, window, title):
    box = Gtk.Box(spacing=12)
    label = Gtk.Label(label=title, xalign=0, hexpand=True)
    label.add_css_class('title-1')
    box.append(label)
    close = Gtk.Button(icon_name='window-close-symbolic')
    action_tooltip(close, 'Close (Esc)')
    close.connect('clicked', lambda *_: window.close())
    box.append(close)
    body.append(box)
    return box


def segmented(options, selected, changed):
    box = Gtk.Box()
    box.add_css_class('linked')
    first = None
    for value, title in options:
        button = Gtk.ToggleButton(label=title)
        if first is None: first = button
        else: button.set_group(first)
        button.set_active(value == selected)
        button.connect('toggled', lambda widget, key=value: changed(key) if widget.get_active() else None)
        box.append(button)
    return box
