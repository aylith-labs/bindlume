"""Keyboard-guide preferences built from the same GTK components as app settings."""
import copy
import sys
import threading
from gi.repository import Gtk, GLib, Pango
from guide import GuideController, ROOT
import settings_ui
import localization
from localization import text as tr


def defaults():
    backend = str(ROOT/'src/backend')
    if backend not in sys.path: sys.path.insert(0, backend)
    from keyguide_backend.settings import DEFAULTS
    return copy.deepcopy(DEFAULTS)


def show(app):
    if getattr(app, 'guide_window', None):
        app.guide_window.present()
        return
    parent = getattr(app, 'preferences_window', None) or app.window
    window = Gtk.Window(application=app, transient_for=parent, modal=True,
                        title='Keyboard guide settings', default_width=740, default_height=720)
    app.guide_window = window
    window.connect('close-request', lambda *_: setattr(app, 'guide_window', None) or False)
    body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16,
                   margin_top=20, margin_bottom=20, margin_start=20, margin_end=20)
    settings_ui.header(body, window, 'Keyboard guide settings')
    scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
    content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    scroll.set_child(content)
    pane = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL, wide_handle=False)
    pane.add_css_class('content-splitter')
    pane.set_start_child(scroll)
    pane.set_resize_start_child(False)
    pane.set_shrink_start_child(True)
    body.append(pane)
    pane.set_vexpand(True)
    side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, width_request=360)
    side.add_css_class('guide-side-preview')
    window.preview_side = bool(app.preferences.get('guide_preview_side', False))
    window.autosave = bool(app.preferences.get('guide_autosave', False))
    window.saving = False
    window.save_timer = 0
    def place_preview():
        if not hasattr(window, 'preview_scroll'): return
        preview = window.preview_scroll
        window.preview_heading.set_visible(not window.preview_side)
        parent = preview.get_parent()
        if parent: parent.remove(preview)
        if window.preview_side:
            pane.set_end_child(side)
            side.append(preview)
            preview.set_vexpand(True)
            display = window.get_display()
            monitor = display.get_monitor_at_surface(window.get_surface()) if window.get_surface() else None
            limit = monitor.get_geometry().width if monitor else 1200
            width = min(1200, max(740, limit-40))
            window.set_default_size(width, 720)
            window.set_size_request(width, -1)
            pane.set_position(max(320, width-480))
        else:
            pane.set_end_child(None)
            content.insert_child_after(preview, window.preview_heading)
            preview.set_vexpand(False)
            window.set_default_size(740, 720)
            window.set_size_request(-1, -1)
    def toggle_side(control, *_):
        window.preview_side = control.get_active()
        app.set_preference('guide_preview_side', window.preview_side)
        place_preview()
        refresh_preview()

    status = Gtk.Label(label='Loading…', xalign=0, wrap=True)
    status.add_css_class('dim-label')
    body.append(status)
    footer = Gtk.Box(spacing=12)
    auto = Gtk.Switch(active=window.autosave, valign=Gtk.Align.CENTER)
    auto_row = Gtk.Box(spacing=12, hexpand=True)
    auto_row.append(auto)
    auto_row.append(Gtk.Label(label='Auto-save', xalign=0, hexpand=True))
    from shortcut_data import make_switch_row
    make_switch_row(auto_row, auto)
    footer.append(auto_row)
    buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END)
    footer.append(buttons)
    reset = Gtk.Button(label='Reset guide settings', sensitive=False)
    cancel = Gtk.Button(label='Close' if window.autosave else 'Cancel')
    save = Gtk.Button(label='Save', sensitive=False)
    cancel.connect('clicked', lambda *_: window.close())
    buttons.append(reset); buttons.append(cancel); buttons.append(save)
    body.append(footer)
    window.set_child(body)
    window.controls = {}
    window.pending = {}
    window.bindings = []
    window.preview_sources = {item['id']: item for item in app.items}
    window.present()
    controller = GuideController()

    def update(key, value):
        window.pending[key] = value
        refresh_preview()
        save.set_sensitive(not window.autosave and window.pending != window.original)
        if window.autosave: schedule_save()

    def switch(title, key, description=None):
        control = Gtk.Switch(active=bool(window.pending[key]))
        settings_ui.row(content, title, control, description)
        control.connect('notify::active', lambda control, *_: update(key, control.get_active()))
        window.controls[key] = control
        return control

    def choices(title, key, options):
        if key in ('position', 'badgeMode'):
            control = settings_ui.segmented(options, window.pending[key], lambda value: update(key, value))
            settings_ui.row(content, title, control)
            window.controls[key] = control
            return
        control = Gtk.DropDown.new_from_strings([label for _, label in options])
        control.set_selected(next((i for i,(value, _) in enumerate(options) if value == window.pending[key]), 0))
        control.connect('notify::selected', lambda widget, *_: update(key, options[widget.get_selected()][0]))
        settings_ui.row(content, title, control)
        window.controls[key] = control

    def number(title, key, low, high, step=1, multiplier=1):
        control = Gtk.SpinButton.new_with_range(low, high, step)
        control.set_value(window.pending[key]*multiplier)
        control.connect('value-changed', lambda widget: update(key, widget.get_value()/multiplier if multiplier != 1 else widget.get_value_as_int()))
        settings_ui.row(content, title, control)
        window.controls[key] = control

    def refresh_preview():
        if not hasattr(window, 'preview'): return
        preview = window.preview
        while child := preview.get_first_child(): preview.remove(child)
        settings = window.pending
        preview.set_opacity(settings['opacity'])
        preview.set_spacing(3 if settings['compactView'] else 9)
        sample = window.bindings[:8] or [dict(id='terminal', key='RETURN', description='Terminal', app_id='sample-terminal'),
                                        dict(id='browser', key='B', description='Browser', app_id='sample-browser')]
        title = Gtk.Label(label='Super shortcuts', xalign=0)
        title.add_css_class('heading'); preview.append(title)
        for binding in sample:
            identity = binding.get('app_id', '')
            hidden = identity in app.learned
            if binding['id'] in settings['hiddenBindingIds'] or (hidden and not settings['showHiddenItems']): continue
            row = Gtk.Box(spacing=12)
            key = Gtk.Label(label=binding['key'], width_chars=9, xalign=.5)
            key.add_css_class('shortcut-keycap'); row.append(key)
            source = window.preview_sources.get(identity)
            if source:
                from app import application_icon
                icon_column = Gtk.Box(width_request=20)
                if source.get('app_icon') and settings['showAppIcons']:
                    icon = application_icon(source['app_icon']); icon.set_pixel_size(20); icon_column.append(icon)
                elif source.get('type_icon') and settings['showIcons'] and source.get('kind') not in ('desktopApp','webapp'):
                    icon_column.append(Gtk.Label(label=source['type_icon']))
                if settings['showAppIcons'] or settings['showIcons']: row.append(icon_column)
            label = Gtk.Label(label=tr(binding['description']) if not window.bindings else binding['description'], xalign=0, hexpand=True, wrap=True, width_chars=1, max_width_chars=18)
            label._translation_skip = bool(window.bindings)
            row.append(label)
            if settings['showSavedIndicators']:
                if identity in app.favorites: row.append(Gtk.Label(label='★'))
                if hidden: row.append(Gtk.Image(icon_name='view-conceal-symbolic'))
            if settings['badgeMode'] != 'none' and source and source.get('kind'):
                marker = Gtk.Label(label=source.get('type_icon','') if settings['badgeMode']=='icons' else tr(source.get('group','')))
                marker.set_max_width_chars(12)
                marker.set_ellipsize(Pango.EllipsizeMode.END)
                marker.add_css_class('count-badge'); row.append(marker)
            preview.append(row)
            for child in (key, label):
                attributes = Pango.AttrList()
                attributes.insert(Pango.attr_scale_new(settings['scale']))
                child.set_attributes(attributes)
        preview.set_halign({'left':Gtk.Align.START, 'right':Gtk.Align.END}.get(settings['position'], Gtk.Align.CENTER))
        preview.set_valign({'top':Gtk.Align.START, 'bottom':Gtk.Align.END}.get(settings['position'], Gtk.Align.CENTER))
        preview.set_size_request(round((350 if window.preview_side else 430)*settings['scale']), -1)
        localization.translate_tree(preview)

    def fill_bindings(*_):
        rows = window.binding_rows
        while child := rows.get_first_child(): rows.remove(child)
        query = window.search.get_text().casefold()
        for binding in window.bindings:
            chord = ' + '.join([*binding.get('modifiers', []), binding['key']])
            if query not in (binding['description']+' '+chord).casefold(): continue
            toggle = Gtk.Switch(active=binding['id'] not in window.pending['hiddenBindingIds'])
            row = settings_ui.row(rows, binding['description'], toggle, chord)
            row.get_first_child()._translation_skip = True
            def changed(widget, _, identity=binding['id']):
                values = set(window.pending['hiddenBindingIds'])
                if widget.get_active(): values.discard(identity)
                else: values.add(identity)
                update('hiddenBindingIds', sorted(values))
            toggle.connect('notify::active', changed)
        if not rows.get_first_child(): rows.append(Gtk.Label(label='No matching shortcuts.', xalign=0))

    def build():
        if hasattr(window, "preview_scroll") and window.preview_scroll.get_parent() is side:
            side.remove(window.preview_scroll)
        while child := content.get_first_child(): content.remove(child)
        window.controls = {"autosave": auto}
        side_switch = Gtk.Switch(active=window.preview_side)
        settings_ui.row(content, 'Preview on the right', side_switch)
        side_switch.connect('notify::active', toggle_side)
        window.controls['preview_side'] = side_switch
        settings_ui.section(content, 'General')
        switch('Enabled', 'enabled', 'Show the shortcut guide while Super is held.')
        choices('Position', 'position', [('center','Center'),('top','Top'),('bottom','Bottom'),('left','Left'),('right','Right')])
        number('Scale (%)', 'scale', 75, 150, 5, 100)
        number('Opacity (%)', 'opacity', 20, 100, 1, 100)
        number('Show delay (milliseconds; 0 = instant)', 'showDelayMs', 0, 5000, 50)
        number('Fade duration (milliseconds; 0 = instant)', 'fadeDurationMs', 0, 2000, 50)
        settings_ui.section(content, 'Shortcut list')
        switch('Compact view', 'compactView', 'Reduce spacing and padding.')
        switch('Desktop and web app icons', 'showAppIcons')
        switch('Action icons', 'showIcons')
        choices('Category markers', 'badgeMode', [('badges','Badges'),('icons','Icons'),('none','None')])
        switch('Bookmark and hidden indicators', 'showSavedIndicators')
        if app.learned: switch('Show hidden shortcuts', 'showHiddenItems')
        switch('Follow theme', 'followTheme')
        window.preview_heading = settings_ui.section(content, 'Live HUD preview')
        window.preview = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        window.preview.add_css_class('feature-preview')
        preview_scroll = Gtk.ScrolledWindow(min_content_height=210, max_content_height=360,
                                            propagate_natural_height=True, hscrollbar_policy=Gtk.PolicyType.AUTOMATIC)
        preview_scroll.set_child(window.preview); content.append(preview_scroll)
        window.preview_scroll = preview_scroll
        place_preview()
        settings_ui.section(content, 'Modifier groups')
        groups = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=3, min_children_per_line=2)
        for name in defaults()['groups']:
            toggle = Gtk.CheckButton(label=name, active=name in window.pending['groups'])
            def group_changed(widget, group=name):
                values = set(window.pending['groups'])
                if widget.get_active(): values.add(group)
                else: values.discard(group)
                update('groups', sorted(values))
            toggle.connect('toggled', group_changed)
            groups.insert(toggle, -1)
        content.append(groups)
        settings_ui.section(content, 'Shortcut visibility in the guide')
        window.search = Gtk.SearchEntry(placeholder_text='Find registered shortcuts')
        content.append(window.search)
        window.binding_rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        content.append(window.binding_rows)
        window.search.connect('search-changed', fill_bindings)
        fill_bindings()
        if app.feature_enabled('manage'):
            edit = Gtk.Button(label='Manage shortcuts')
            edit.connect('clicked', lambda *_: (window.close(), app.show_management()))
            content.append(edit)
        refresh_preview()
        reset.set_sensitive(True)
        save.set_sensitive(not window.autosave and window.pending != window.original)
        if window.autosave: schedule_save()
        localization.translate_tree(window)

    def loaded(values, bindings, error, sources=None):
        if not window.get_visible(): return False
        if error:
            status.set_text(error)
            return False
        window.original = copy.deepcopy(values)
        window.pending = copy.deepcopy(values)
        window.bindings = bindings
        if sources is not None: window.preview_sources = {item['id']: item for item in sources}
        status.set_text('')
        build()
        return False

    def load():
        try:
            values = controller.read()
            try: bindings = controller.backend('bindings', '--json')
            except (OSError, RuntimeError): bindings = []
            sources = None
            if app.source_name != 'Omarchy':
                from app import records
                try: sources = records()
                except (OSError, RuntimeError): pass
            GLib.idle_add(loaded, values, bindings, '', sources)
        except Exception as error: GLib.idle_add(loaded, {}, [], str(error))
    threading.Thread(target=load, daemon=True).start()

    def restore(*_):
        window.pending = defaults()
        window.pending['language'] = __import__('localization').resolve_language(app.preferences['language'])
        build()
    reset.connect('clicked', restore)

    def schedule_save():
        if window.save_timer: GLib.source_remove(window.save_timer)
        window.save_timer = GLib.timeout_add(350, automatic_commit)

    def automatic_commit():
        window.save_timer = 0
        if window.autosave: commit(close=False)
        return False

    def saved(error, snapshot, close):
        window.saving = False
        if error:
            status.set_text(error)
        else:
            window.original = snapshot
            status.set_text('Saved')
        if window.get_visible():
            content.set_sensitive(True)
            save.set_sensitive(not window.autosave and window.pending != window.original)
            if not error and close: window.close()
        if not error and window.autosave and window.pending != window.original: schedule_save()
        elif not error and getattr(window, 'close_after_save', False):
            window.close_after_save = False
            window.close()
        return False

    def commit(*_, close=True):
        if window.saving: return
        snapshot = copy.deepcopy(window.pending)
        patch = {key:value for key,value in snapshot.items() if value != window.original.get(key)}
        if not patch:
            if close: window.close()
            return
        window.saving = True
        save.set_sensitive(False)
        if close: content.set_sensitive(False)
        status.set_text('Saving…')
        def worker():
            try: controller.patch(**patch); error = ''
            except Exception as exception: error = str(exception)
            GLib.idle_add(saved, error, snapshot, close)
        threading.Thread(target=worker, daemon=True).start()
    save.connect('clicked', commit)
    def autosave_changed(control, *_):
        window.autosave = control.get_active()
        app.set_preference('guide_autosave', window.autosave)
        cancel.set_label('Close' if window.autosave else 'Cancel')
        save.set_sensitive(not window.autosave and hasattr(window, 'original') and window.pending != window.original)
        if window.autosave and hasattr(window, 'original'): schedule_save()
    auto.connect('notify::active', autosave_changed)
    def closing(*_):
        if window.autosave and hasattr(window, 'original') and (window.saving or window.pending != window.original):
            app.guide_window = window
            window.close_after_save = True
            if not window.saving: commit(close=False)
            return True
        return False
    window.connect('close-request', closing)
