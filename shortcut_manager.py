"""Native shortcut editor backed by the guide's transactional binding manager."""
import json
import threading
from gi.repository import Gtk, Gdk, GLib
from guide import GuideController
from shortcut_data import action_tooltip

GROUPS = ['SUPER', 'SUPER+CTRL', 'SUPER+SHIFT', 'SUPER+ALT',
          'SUPER+CTRL+SHIFT', 'SUPER+CTRL+ALT', 'SUPER+SHIFT+ALT', 'SUPER+CTRL+SHIFT+ALT']


def assignment_request(group, option, action, title, arguments, replace):
    if not option or not action:
        raise ValueError('Choose a key and an action first.')
    if not option.get('editable', False):
        raise ValueError(option.get('editReason') or 'This shortcut cannot be edited.')
    if option.get('state') == 'assigned' and not replace:
        raise ValueError('Confirm replacing the existing shortcut first.')
    kind = action.get('selectionKind', action.get('kind', 'action'))
    return dict(targetModifiers=group.split('+'), targetKey=option['key'],
                selectionKind=kind, selectionId=action.get('selectionId', action['id']),
                titleOverride=title.strip(), customArguments=arguments if kind == 'command' else '',
                targetBindingId=option.get('bindingId', ''), confirmReplace=replace)


class ShortcutPicker(Gtk.Box):
    """Shared modifier/key picker with optional physical-key capture."""
    def __init__(self, groups=GROUPS, keys=(), error=lambda message: None):
        super().__init__(spacing=8)
        self.groups = list(groups)
        self.error = error
        self.group = Gtk.DropDown.new_from_strings(self.groups)
        self.group.set_factory(self.group_factory())
        self.group.set_list_factory(self.group_factory())
        self.group.set_tooltip_text('Choose the modifier combination for the shortcut')
        self.append(self.group)
        self.key_model = Gtk.StringList.new(list(keys))
        self.key = Gtk.DropDown(model=self.key_model, enable_search=True, hexpand=True)
        self.key.set_tooltip_text('Choose a key')
        self.append(self.key)
        self.capture = Gtk.ToggleButton(label='Capture shortcut')
        self.capture.set_tooltip_text('Click, then press a shortcut. Escape cancels capture.')
        controller = Gtk.EventControllerKey()
        controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        controller.connect('key-pressed', self.capture_key)
        self.capture.add_controller(controller)
        self.capture_controller = controller
        self.capture_surface = None
        self.capture_root_handler = None
        self.capture.connect('toggled', self.capture_toggled)
        self.connect('unmap', lambda *_: self.capture.set_active(False))
        self.append(self.capture)

    def capture_toggled(self, button):
        from localization import text
        active = button.get_active()
        button.set_label(text('Press shortcut…' if active else 'Capture shortcut'))
        if active:
            button.grab_focus()
            root = self.get_root()
            if isinstance(root, Gtk.Window):
                handler = root.connect('notify::is-active', lambda window, *_: button.set_active(False) if not window.is_active() else None)
                self.capture_root_handler = (root, handler)
            native = self.get_native()
            surface = native.get_surface() if native else None
            if isinstance(surface, Gdk.Toplevel):
                self.capture_surface = surface
                surface.inhibit_system_shortcuts(None)
        else:
            if self.capture_surface is not None:
                self.capture_surface.restore_system_shortcuts()
                self.capture_surface = None
            if self.capture_root_handler:
                root, handler = self.capture_root_handler
                root.disconnect(handler)
                self.capture_root_handler = None

    @staticmethod
    def group_factory():
        factory = Gtk.SignalListItemFactory()
        def bind(_factory, item):
            box = Gtk.Box(spacing=5)
            for index, key in enumerate(item.get_item().get_string().split('+')):
                if index: box.append(Gtk.Label(label='+'))
                label = Gtk.Label(label=key.title())
                label.add_css_class('shortcut-keycap')
                box.append(label)
            item.set_child(box)
        factory.connect('bind', bind)
        return factory

    def set_chord(self, chord):
        parts = [part.strip().upper() for part in chord.split('+')]
        mods, name = parts[:-1], parts[-1]
        group = next((value for value in self.groups if set(value.split('+')) == set(mods)), None)
        if group is None: return False
        self.group.set_selected(self.groups.index(group))
        for index in range(self.key_model.get_n_items()):
            if self.key_model.get_string(index).split(' — ', 1)[0].upper() == name:
                self.key.set_selected(index)
                return True
        return False

    def get_chord(self):
        item = self.key.get_selected_item()
        if item is None: return ''
        return self.groups[self.group.get_selected()].replace('+', ' + ') + ' + ' + item.get_string().split(' — ', 1)[0]

    def capture_key(self, _controller, key, _code, state):
        if not self.capture.get_active(): return False
        if key == Gdk.KEY_Escape:
            self.capture.set_active(False)
            return True
        if key in (Gdk.KEY_Super_L, Gdk.KEY_Super_R, Gdk.KEY_Control_L, Gdk.KEY_Control_R,
                   Gdk.KEY_Shift_L, Gdk.KEY_Shift_R, Gdk.KEY_Alt_L, Gdk.KEY_Alt_R):
            return True
        mods = [name for name, flag in [('SUPER', Gdk.ModifierType.SUPER_MASK), ('CTRL', Gdk.ModifierType.CONTROL_MASK),
                                       ('SHIFT', Gdk.ModifierType.SHIFT_MASK), ('ALT', Gdk.ModifierType.ALT_MASK)] if state & flag]
        name = (Gdk.keyval_name(key) or '').upper()
        if self.set_chord('+'.join(mods + [name])):
            self.capture.set_active(False)
        else:
            self.error('Choose a supported modifier combination and key, or use the key picker.')
        return True


class ShortcutManagerPanel(Gtk.Box):
    def __init__(self, changed=lambda: None, controller=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                         margin_start=16, margin_end=16, margin_top=12, margin_bottom=16)
        self.controller = controller or GuideController()
        self.changed = changed
        self.busy = False
        self.snapshot = {}
        self.actions = []
        self.options = []
        self.bindings = []
        heading = Gtk.Label(label='Manage shortcuts', xalign=0)
        heading.add_css_class('title-2')
        self.append(heading)
        self.append(Gtk.Label(label='Choose a modifier group and key, then choose what it should do. Changes apply to your live Hyprland bindings.', xalign=0, wrap=True))
        self.form = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.append(self.form)
        self.picker = ShortcutPicker(error=lambda message: self.status.set_text(message))
        self.group, self.key_model, self.key, self.capture = (self.picker.group, self.picker.key_model,
                                                            self.picker.key, self.picker.capture)
        self.form.append(self.picker)
        self.current = Gtk.Label(xalign=0, wrap=True)
        self.form.append(self.current)
        self.form.append(Gtk.Label(label='Action or application', xalign=0))
        self.action_model = Gtk.StringList.new([])
        self.action = Gtk.DropDown(model=self.action_model, enable_search=True, hexpand=True)
        self.form.append(self.action)
        self.title = Gtk.Entry(placeholder_text='Custom title (optional)')
        self.arguments = Gtk.Entry(placeholder_text='Command arguments (optional)')
        self.form.append(self.title)
        self.form.append(self.arguments)
        self.confirm = Gtk.CheckButton(label='Confirm replacing or removing the current shortcut')
        self.form.append(self.confirm)
        buttons = Gtk.Box(spacing=10)
        self.apply_button = Gtk.Button(label='Apply shortcut')
        self.apply_button.add_css_class('suggested-action')
        action_tooltip(self.apply_button, 'Apply shortcut (Ctrl+Enter)')
        self.apply_button.connect('clicked', self.assign)
        buttons.append(self.apply_button)
        self.remove_button = Gtk.Button(label='Remove shortcut')
        self.remove_button.connect('clicked', self.remove)
        self.remove_button.set_tooltip_text('Remove this binding. Select the confirmation checkbox to allow removal.')
        buttons.append(self.remove_button)
        refresh = Gtk.Button(label='Refresh')
        refresh.connect('clicked', lambda *_: self.refresh())
        buttons.append(refresh)
        self.form.append(buttons)
        self.status = Gtk.Label(xalign=0, wrap=True)
        self.append(self.status)
        self.group.connect('notify::selected', self.group_changed)
        self.key.connect('notify::selected', self.key_changed)
        self.action.connect('notify::selected', self.action_changed)

    def run(self, work):
        if self.busy: return
        self.busy = True
        self.form.set_sensitive(False)
        self.status.set_text('Loading…')
        def worker():
            try: result, error = work(), ''
            except Exception as exc: result, error = None, str(exc)
            GLib.idle_add(self.finished, result, error)
        threading.Thread(target=worker, daemon=True).start()

    def refresh(self):
        self.run(self.load)

    def load(self):
        return (self.controller.backend('shortcuts', 'status'),
                self.controller.backend('catalog', 'list', '--language', 'en'),
                self.controller.backend('bindings', '--json'))

    def finished(self, result, error):
        self.busy = False
        self.form.set_sensitive(True)
        if error:
            self.status.set_text(error)
            return False
        self.snapshot, catalog, self.bindings = result
        self.actions = self.snapshot['actions'] + catalog.get('items', [])
        self.action_model.splice(0, self.action_model.get_n_items(),
                                 [a.get('title', a['id']) for a in self.actions])
        self.group_changed()
        self.status.set_text(self.snapshot.get('discoveryError', '') or 'Live shortcut configuration loaded.')
        return False

    def group_changed(self, *_):
        group = GROUPS[self.group.get_selected()]
        previous = self.selected_option().get('key')
        self.options = self.snapshot.get('keyOptionsByGroup', {}).get(group, [])
        self.key_model.splice(0, self.key_model.get_n_items(),
                              [o['key'] + (' — ' + o['title'] if o.get('title') else ' — Available') for o in self.options])
        self.key.set_selected(next((i for i, o in enumerate(self.options) if o['key'] == previous), 0))
        self.key_changed()

    def selected_option(self):
        index = self.key.get_selected()
        return self.options[index] if index < len(self.options) else {}

    def key_changed(self, *_):
        option = self.selected_option()
        self.confirm.set_active(False)
        self.confirm.set_visible(option.get('state') == 'assigned')
        self.current.set_text(('Current action: ' + option.get('title', '')) if option.get('state') == 'assigned' else 'This key is available.')
        self.apply_button.set_sensitive(bool(option.get('editable')))
        self.remove_button.set_sensitive(bool(option.get('removable')))
        self.title.set_text('')
        action_id = option.get('actionId')
        if action_id:
            for index, action in enumerate(self.actions):
                if action['id'] == action_id:
                    self.action.set_selected(index)
                    break

    def action_changed(self, *_):
        i = self.action.get_selected()
        action = self.actions[i] if i < len(self.actions) else {}
        self.arguments.set_visible(action.get('selectionKind', action.get('kind')) == 'command')

    def capture_key(self, *args):
        return self.picker.capture_key(*args)

    def assign(self, *_):
        try:
            index = self.action.get_selected()
            action = self.actions[index] if index < len(self.actions) else None
            request = assignment_request(GROUPS[self.group.get_selected()], self.selected_option(), action,
                                         self.title.get_text(), self.arguments.get_text(), self.confirm.get_active())
        except ValueError as error:
            self.status.set_text(str(error))
            return
        self.mutate('assign', request)

    def remove(self, *_):
        option = self.selected_option()
        binding = next((b for b in self.bindings if b['id'] == option.get('bindingId')), None)
        if not binding or not self.confirm.get_active():
            self.status.set_text('Select the confirmation checkbox before removing this shortcut.')
            return
        request = dict(targetModifiers=GROUPS[self.group.get_selected()].split('+'), targetKey=option['key'],
                       targetBindingId=binding['id'], title=binding['description'], dispatcher=binding['dispatcher'],
                       argument=binding['argument'], confirmRemove=True)
        self.mutate('remove', request)

    def mutate(self, operation, request):
        def work():
            self.controller.backend('shortcuts', operation, json.dumps(request))
            try: self.controller.ipc('keyguide', 'refresh')
            except (OSError, RuntimeError): pass
            result = self.load()
            GLib.idle_add(self.changed)
            return result
        self.run(work)
