"""Shortcut-set selection and data-only plugin import."""
from pathlib import Path
from gi.repository import Gtk, Gio, Gdk
import shortcut_sets
from binding_sources import SOURCES
from shortcut_data import make_switch_row, action_tooltip
from localization import text as tr


def show(app):
    existing = getattr(app, 'source_library_window', None)
    if existing:
        existing.present(); return
    app.dismiss_choice()
    app.menu_button.popdown()
    app.app_menu_button.popdown()
    window = Gtk.Window(application=app, transient_for=app.window, modal=True,
                        title='Shortcut sets', default_width=920, default_height=620)
    window.add_css_class('shortcuts-app')
    body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14,
                   margin_top=20, margin_bottom=20, margin_start=20, margin_end=20)
    header = Gtk.Box(spacing=12)
    title = Gtk.Label(label='Choose shortcut sets', xalign=0, hexpand=True)
    title.add_css_class('title-2'); header.append(title)
    close = Gtk.Button(icon_name='window-close-symbolic')
    action_tooltip(close, 'Close (Esc)')
    close.connect('clicked', lambda *_: window.close()); header.append(close)
    body.append(header)
    body.append(Gtk.Label(label='Installed apps with available shortcuts appear in the source menu. Turning a set off keeps its bookmarks and hidden shortcuts.', xalign=0, wrap=True))
    search = Gtk.SearchEntry(placeholder_text='Find a shortcut set…')
    body.append(search)
    rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
    scroll.set_child(rows); body.append(scroll)
    message = Gtk.Label(xalign=0, wrap=True, selectable=True)
    message.add_css_class('dim-label'); body.append(message)
    def confirm_remove(source):
        path=shortcut_sets.custom_file(source)
        if path is None:return
        snapshot=path.read_bytes()
        data=shortcut_sets.read(path)
        dialog=Gtk.Window(application=app,transient_for=window,modal=True,title=tr('Remove shortcut set'),default_width=580,default_height=480)
        dialog.set_destroy_with_parent(True)
        content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12,margin_top=20,margin_bottom=20,margin_start=20,margin_end=20)
        import settings_ui
        settings_ui.header(content,dialog,tr('Remove shortcut set'))
        content.append(Gtk.Label(label=source,xalign=0))
        content.append(Gtk.Label(label=tr('Move this custom set to Trash? Saved marks are kept.'),xalign=0,wrap=True))
        filename=Gtk.Label(label=str(path),xalign=0,wrap=True,selectable=True,max_width_chars=48)
        content.append(filename)
        preview=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8)
        for item in data['shortcuts']:
            preview.append(Gtk.Label(label=item['title']+' — '+item['keys'],xalign=0,wrap=True,max_width_chars=48))
        scroller=Gtk.ScrolledWindow(vexpand=True,hscrollbar_policy=Gtk.PolicyType.NEVER);scroller.set_child(preview);content.append(scroller)
        error=Gtk.Label(xalign=0,wrap=True);content.append(error)
        actions=Gtk.Box(spacing=10,halign=Gtk.Align.END)
        cancel=Gtk.Button(label=tr('Cancel'));cancel.connect('clicked',lambda *_:dialog.close());actions.append(cancel)
        remove=Gtk.Button(label=tr('Move to Trash'));remove.add_css_class('destructive-action')
        def apply(*_):
            try:shortcut_sets.remove_custom(source,snapshot)
            except Exception as exc:error.set_text(str(exc));return
            app.reload_source_registry();app.ensure_available_source();fill();dialog.close()
        remove.connect('clicked',apply);actions.append(remove);content.append(actions)
        dialog.set_child(content);dialog.present();cancel.grab_focus()
    window.confirm_remove = confirm_remove
    def fill(*_):
        child=rows.get_first_child()
        while child:
            next_child=child.get_next_sibling(); rows.remove(child); child=next_child
        window.source_switches = {}
        window.switch_sizes = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.BOTH)
        window.category_grids = {}
        query = search.get_text().casefold()
        ordered = sorted(SOURCES, key=lambda name: (tr(shortcut_sets.CATEGORIES[shortcut_sets.category(name)]).casefold(), name.casefold()))
        for source in ordered:
            category = shortcut_sets.category(source)
            label = shortcut_sets.CATEGORIES[category]
            if query not in (source+' '+tr(label)).casefold(): continue
            if category not in window.category_grids:
                heading = Gtk.Label(label=tr(label), xalign=0, margin_top=12)
                heading._translation_source = label
                heading.add_css_class('heading')
                rows.append(heading)
                grid = Gtk.Grid(column_spacing=24, row_spacing=12, column_homogeneous=True, valign=Gtk.Align.START)
                grid.empty_column=Gtk.Box(hexpand=True)
                grid.attach(grid.empty_column,1,0,1,1)
                rows.append(grid)
                window.category_grids[category] = (grid, [])
            grid, members = window.category_grids[category]
            present=shortcut_sets.installed(source)
            count=app.source_counts.get(source)
            status = ('Not installed on this system' if not present else
                      tr('{count} shortcut' if count == 1 else '{count} shortcuts').format(count=count) if count else
                      'Checking shortcuts…' if app.counts_busy else 'No shortcuts available')
            row=Gtk.Box(spacing=16)
            labels=Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, hexpand=True)
            name = Gtk.Label(label=source, xalign=0, wrap=True)
            name._translation_skip = True
            labels.append(name)
            detail=Gtk.Label(label=status, xalign=0, wrap=True); detail.add_css_class('dim-label')
            labels.append(detail)
            toggle=Gtk.Switch(active=present and bool(count) and source not in app.disabled_sources, valign=Gtk.Align.CENTER, halign=Gtk.Align.START, hexpand=False, vexpand=False)
            window.switch_sizes.add_widget(toggle)
            toggle.set_sensitive(present and bool(count))
            toggle.set_tooltip_text('Include this set in the source menu. Saved marks are kept when disabled.')
            toggle.connect('notify::active', lambda control, _, name=source: app.set_source_enabled(name, control.get_active()))
            row.append(toggle); row.append(labels); make_switch_row(row,toggle)
            row.set_sensitive(present and bool(count))
            cell=Gtk.Box(spacing=8,hexpand=True)
            row.set_hexpand(True);cell.append(row)
            if shortcut_sets.custom_file(source):
                remove=Gtk.Button(icon_name='user-trash-symbolic',valign=Gtk.Align.CENTER,halign=Gtk.Align.END)
                remove.set_tooltip_text(tr('Remove shortcut set'))
                remove.connect('clicked',lambda _,name=source:confirm_remove(name))
                cell.append(remove)
            if len(members)==1:grid.remove(grid.empty_column)
            grid.attach(cell, len(members)%2, len(members)//2, 1, 1)
            members.append(source)
            window.source_switches[source]=toggle
        if shortcut_sets.ERRORS: message.set_text('Some sets could not be loaded:\n'+'\n'.join(shortcut_sets.ERRORS))
    search.connect('search-changed', fill)
    window.refresh_sources = fill
    window.source_search = search
    controls=Gtk.Box(spacing=8)
    def refresh(*_):
        app.reload_source_registry(); app.refresh_source_counts(); fill()
    refresh_button=Gtk.Button(label='Refresh')
    refresh_button.connect('clicked', refresh); controls.append(refresh_button)
    def imported(dialog, response):
        if response == Gtk.ResponseType.ACCEPT:
            file=dialog.get_file()
            try:
                if not file or not file.get_path(): raise ValueError('Choose a local JSON file')
                target=shortcut_sets.install_file(file.get_path())
                message.set_text(tr('Added {name}').format(name=target.name)); refresh()
            except (ValueError,OSError) as error: message.set_text(str(error))
        dialog.destroy()
    def choose(*_):
        dialog=Gtk.FileChooserNative(title='Import shortcut set', transient_for=window,
                                    action=Gtk.FileChooserAction.OPEN, accept_label='Import')
        filter=Gtk.FileFilter(); filter.set_name('Shortcut sets (*.json)'); filter.add_pattern('*.json')
        dialog.add_filter(filter); dialog.connect('response', imported); dialog.show()
    import_button=Gtk.Button(label='Import set…'); import_button.connect('clicked',choose); controls.append(import_button)
    def create(*_):
        try:
            path=shortcut_sets.create_template(); refresh()
            message.set_text(tr('Created {path}. Edit the JSON file, then press Refresh.').format(path=path))
            Gio.AppInfo.launch_default_for_uri(path.as_uri(), None)
        except Exception as error: message.set_text(str(error))
    create_button=Gtk.Button(label='Create a set…'); create_button.connect('clicked',create); controls.append(create_button)
    def folder(*_):
        path=shortcut_sets.user_directory(); path.mkdir(parents=True,exist_ok=True)
        Gio.AppInfo.launch_default_for_uri(path.as_uri(),None)
    folder_button=Gtk.Button(icon_name='folder-open-symbolic', tooltip_text='Open shortcut-set folder')
    folder_button.connect('clicked',folder); controls.append(folder_button)
    body.append(controls)
    guide=Gtk.Button(label='How to create shortcut sets')
    def open_guide(*_):
        existing = getattr(window, 'guide_window', None)
        if existing:
            existing.present()
            return
        from info_view import MarkdownWindow
        window.guide_window = MarkdownWindow(app, window, Path(__file__).with_name('SHORTCUT_SETS.md'), 'Create shortcut sets')
        window.guide_window.connect('close-request', lambda *_: setattr(window, 'guide_window', None) or False)
        window.guide_window.set_destroy_with_parent(True)
        window.guide_window.present()
    guide.connect('clicked', open_guide)
    window.open_guide = open_guide
    guide.set_halign(Gtk.Align.START); body.append(guide)
    window.set_child(body)
    keys=Gtk.EventControllerKey()
    keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
    keys.connect('key-pressed', lambda _,key,*args: (window.close() or True) if key==Gdk.KEY_Escape else False)
    window.add_controller(keys)
    window.connect('close-request',lambda *_: setattr(app,'source_library_window',None) or False)
    app.source_library_window=window
    window.set_focus(search)
    refresh(); window.present()
    search.grab_focus()
