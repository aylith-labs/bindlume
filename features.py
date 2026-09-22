"""Optional capabilities and an inert gallery built from the app's widgets."""
import gi
import re
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, Pango
import localization
from shortcut_data import make_switch_row, action_tooltip

FEATURES = {
    'bookmarks': ('Bookmarks', 'Keep favorite shortcuts and sources close at hand. Turning this off keeps your saved bookmarks.'),
    'hidden': ('Hide shortcuts', 'Hide shortcuts you do not want to see. Turning this off shows everything and keeps your hidden marks.'),
    'keyboard': ('Keyboard explorer', 'Explore shortcuts on a keyboard, with modifier layers and key overlays.'),
    'inputs': ('Mouse gestures & controllers', 'Explore connected input devices and assign gestures or controller buttons to Bindlume actions.'),
    'manage': ('Shortcut editor', 'Create and change supported desktop shortcuts. Disabling the editor leaves your bindings intact.'),
    'guide': ('Keyboard guide', 'Show a shortcut guide when you hold Super. Configure its appearance from App settings.'),
    'target': ('Choose a target window', 'Choose which window receives actions launched from the shortcut list.'),
    'layouts': ('Filters and layouts', 'Filter by modifier and shortcut type, group shortcuts, or change the list layout.'),
    'live': ('Live filter', 'Hold keys to filter the list. Scroll and click actions while modifiers are held; Escape exits.'),
    'appearance': ('Appearance', 'Choose a consistent look for the app and keyboard guide. Rounded uses soft corners; Square uses straight edges and monospace text.'),
    'agent': ('Agent chat', 'Ask an installed agent about shortcuts and settings. Keep conversations here and return to them later.'),
    'history': ('Recent searches', 'Keep up to 20 recent searches on this device and suggest them as you type.'),
}
DEFAULT_FEATURES = {key: key == 'agent' for key in FEATURES}
ACTION_FEATURES = {
    'chat':'agent', 'chat_history':'agent',
    'favorites':'bookmarks', 'bookmark_row':'bookmarks', 'source':'bookmarks',
    'learned':'hidden', 'learn_row':'hidden', 'view':'keyboard', 'overlay':'keyboard',
    'numpad':'keyboard', 'fit':'keyboard', 'manage':'manage', 'manage_apply':'manage', 'back':'manage',
    'guide':'guide', 'target':'target', 'filters':'layouts', 'flat':'layouts',
    'columns':'layouts', 'type':'layouts', 'expand':'layouts', 'collapse':'layouts', 'live':'live',
}

def gallery(app):
    window = Gtk.Window(application=app, transient_for=app.window, modal=True,
                        title='Features', default_width=920, default_height=700)
    window.add_css_class('shortcuts-app')
    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16,
                    margin_top=20, margin_bottom=20, margin_start=20, margin_end=20)
    heading = Gtk.Box(spacing=12)
    title = Gtk.Label(label='Make it yours', xalign=0, hexpand=True)
    title.add_css_class('title-1')
    heading.append(title)
    close = Gtk.Button(icon_name='window-close-symbolic')
    action_tooltip(close, 'Close Features (Esc)')
    close.connect('clicked', lambda *_: window.close())
    heading.append(close)
    outer.append(heading)
    outer.append(Gtk.Label(label='Start simple. Enable the tools you need. Previews use sample shortcuts.', xalign=0, wrap=True))
    search = Gtk.SearchEntry(placeholder_text='Search features…', hexpand=True)
    window.feature_search = search
    window.set_focus(search)
    scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
    cards = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=False,
                        min_children_per_line=1, max_children_per_line=2, row_spacing=14, column_spacing=14)
    view_controls = Gtk.Box(spacing=16)
    view_controls.append(search)
    previews = []
    descriptions = []
    layout_row = Gtk.Box(spacing=10)
    layout_row.append(Gtk.Label(label='Grid view', xalign=0))
    layout = Gtk.Switch(active=True, valign=Gtk.Align.CENTER)
    layout.set_tooltip_text('Show feature cards in a grid. Turn off for a single list.')
    layout.connect('notify::active', lambda toggle, _: cards.set_max_children_per_line(2 if toggle.get_active() else 1))
    layout_row.append(layout)
    make_switch_row(layout_row, layout)
    preview_row = Gtk.Box(spacing=10)
    preview_row.append(Gtk.Label(label='Previews', xalign=0))
    show_previews = Gtk.Switch(active=True, valign=Gtk.Align.CENTER)
    show_previews.set_tooltip_text('Show sample previews inside feature cards.')
    show_previews.connect('notify::active', lambda toggle, _: [preview.set_visible(toggle.get_active()) for preview in previews])
    preview_row.append(show_previews)
    make_switch_row(preview_row, show_previews)
    view_controls.append(preview_row)
    description_row = Gtk.Box(spacing=10)
    description_row.append(Gtk.Label(label='Descriptions', xalign=0))
    show_descriptions = Gtk.Switch(active=True, valign=Gtk.Align.CENTER)
    show_descriptions.set_tooltip_text('Show explanatory text inside feature cards. Search still matches descriptions when hidden.')
    show_descriptions.connect('notify::active', lambda toggle, _: [label.set_visible(toggle.get_active()) for label in descriptions])
    description_row.append(show_descriptions)
    make_switch_row(description_row, show_descriptions)
    view_controls.append(description_row)
    view_controls.append(layout_row)
    window.description_switch = show_descriptions
    window.feature_descriptions = descriptions
    outer.append(view_controls)
    window.preview_switch = show_previews
    window.feature_previews = previews
    window.layout_switch = layout
    window.feature_cards = cards
    switches = {}
    headers = []
    feature_labels = []
    window.feature_labels = feature_labels
    preview_keyboards = []
    def build_preview(feature):
        preview = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        preview.add_css_class('feature-preview')
        preview.set_can_target(False)
        sample = dict(id='__preview_'+feature, key='SUPER + T', name='Terminal', group='Command',
                      kind='command', dispatcher='exec', arg='', type_icon='⌘', app_icon='utilities-terminal')
        if feature == 'keyboard':
            from keyboard_view import KeyboardView
            keyboard = KeyboardView(lambda *_: None, lambda: app.system_theme.colors, preview=True)
            preview_keyboards.append(keyboard)
            keyboard.set_items([sample, dict(sample, id='__preview_browser', key='SUPER SHIFT + B', name='Browser')])
            keyboard.toolbar.set_visible(False)
            keyboard.caption.set_visible(False)
            keyboard.legend.set_visible(False)
            keyboard.extras_host.set_visible(False)
            preview.append(keyboard)
        elif feature == 'inputs':
            preview.append(Gtk.Label(label='Mouse · Controller · Azeron', xalign=0))
            preview.append(Gtk.Label(label='←  ↑  →  ↓', xalign=0))
        elif feature == 'agent':
            preview.append(Gtk.Label(label='Help me find a shortcut', xalign=0))
            preview.append(Gtk.Entry(placeholder_text='Ask about shortcuts…'))
        elif feature == 'history':
            preview.append(Gtk.SearchEntry(text='term', placeholder_text='Search shortcuts…'))
            for text in ('terminal', 'terminal tabs'):
                suggestion = Gtk.Button(label=text)
                suggestion.add_css_class('flat')
                preview.append(suggestion)
        elif feature == 'target':
            preview.append(Gtk.DropDown.new_from_strings(['Browser — Example workspace', 'Current window']))
            example = app.shortcut_row(dict(sample, name='Move to workspace 2', app_icon='', type_icon='↦'), columns=False, preview=True)
            example.get_last_child().set_visible(False)
            example.get_last_child().get_prev_sibling().set_visible(False)
            preview.append(example)
        elif feature == 'manage':
            preview.append(Gtk.Entry(text='SUPER + T'))
            preview.append(Gtk.DropDown.new_from_strings(['Open Terminal', 'Open Browser']))
        else:
            if feature == 'live':
                modifiers = Gtk.Box()
                modifiers.add_css_class('linked')
                for name in ('Super', 'Ctrl', 'Shift', 'Alt'):
                    modifiers.append(Gtk.ToggleButton(label=name, active=name == 'Super'))
                preview.append(modifiers)
            row = app.shortcut_row(sample, columns=feature in ('layouts','guide'), preview=True)
            row.get_last_child().set_visible(feature == 'hidden')
            row.get_last_child().get_prev_sibling().set_visible(feature == 'bookmarks')
            if feature == 'bookmarks':
                row.get_last_child().get_prev_sibling().set_label('★')
            if feature == 'hidden': row.get_last_child().set_icon_name('view-conceal-symbolic')
            preview.append(row)
        def unfocus(widget):
            if widget.has_css_class('shortcut-name'):
                widget.remove_css_class('shortcut-name')
                widget.add_css_class('preview-name')
            widget.set_focusable(False)
            child = widget.get_first_child()
            while child:
                unfocus(child)
                child = child.get_next_sibling()
        unfocus(preview)
        from localization import translate_tree
        translate_tree(preview)
        return preview
    for feature, (name, description) in FEATURES.items():
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        card.add_css_class('feature-card')
        row = Gtk.Box(spacing=12)
        label = Gtk.Label(label=name, xalign=0, hexpand=True)
        label.add_css_class('heading')
        row.append(label)
        switch = Gtk.Switch(active=app.feature_enabled(feature), valign=Gtk.Align.CENTER)
        row.append(switch)
        headers.append((row, label, switch))
        make_switch_row(card, switch)
        switches[feature] = switch
        switch.connect('notify::active', lambda toggle, _, key=feature: app.set_feature(key, toggle.get_active()))
        card.append(row)
        description_label = Gtk.Label(label=description, xalign=0, wrap=True, max_width_chars=40)
        card.append(description_label)
        descriptions.append(description_label)
        feature_labels.extend((label, description_label))
        preview = build_preview(feature)
        previews.append(preview)
        card.append(preview)
        tooltip_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        tooltip_description = Gtk.Label(label=description, xalign=0, wrap=True, max_width_chars=48)
        tooltip_content.append(tooltip_description)
        def query_tooltip(_card, _x, _y, _keyboard, tooltip, content=tooltip_content,
                          explanation=tooltip_description, key=feature):
            missing_description = not show_descriptions.get_active()
            missing_preview = not show_previews.get_active()
            if not (missing_description or missing_preview):
                return False
            explanation.set_visible(missing_description)
            example = getattr(content, 'example', None)
            if missing_preview and example is None:
                example = content.example = build_preview(key)
                example.set_size_request(360, -1)
                content.append(example)
            if example is not None:
                example.set_visible(missing_preview)
            tooltip.set_custom(content)
            return True
        card.set_has_tooltip(True)
        card.connect('query-tooltip', query_tooltip)
        card.query_feature_tooltip = query_tooltip
        cards.append(card)
        card.get_parent().search_text = (name + ' ' + description + ' ' + localization.text(name) + ' ' + localization.text(description)).casefold()
    def update_presentation(*_):
        compact = not show_previews.get_active() and not show_descriptions.get_active()
        cards.set_valign(Gtk.Align.START)
        cards.set_row_spacing(4 if compact else 14)
        child = cards.get_first_child()
        list_index = 0
        while child:
            card = child.get_child()
            row, title_label, switch = headers[list_index]
            row.reorder_child_after(switch, None if compact else title_label)
            title_label.set_hexpand(not compact)
            if compact:
                card.remove_css_class('feature-card')
                title_label.remove_css_class('heading')
            else:
                card.add_css_class('feature-card')
                title_label.add_css_class('heading')
            card.set_spacing(0 if compact else 12)
            list_index += 1
            child = child.get_next_sibling()
    show_previews.connect('notify::active', update_presentation)
    show_descriptions.connect('notify::active', update_presentation)
    preferences = getattr(app, 'feature_view', {})
    layout.set_active(preferences.get('grid', True))
    show_previews.set_active(preferences.get('previews', True))
    show_descriptions.set_active(preferences.get('descriptions', True))
    cards.set_max_children_per_line(2 if layout.get_active() else 1)
    update_presentation()
    def save_presentation(*_):
        app.feature_view = dict(grid=layout.get_active(), previews=show_previews.get_active(),
                                descriptions=show_descriptions.get_active())
        app.save_ui_state()
    for control in (layout, show_previews, show_descriptions):
        control.connect('notify::active', save_presentation)
    empty = Gtk.Label(label='No features match your search.', margin_top=20, margin_bottom=20, visible=False)
    outer.append(empty)
    window.search_empty = empty
    def matches(child):
        return all(word in child.search_text for word in search.get_text().casefold().split())
    cards.set_filter_func(matches)
    def filter_features(*_):
        words = sorted(set(search.get_text().split()), key=len, reverse=True)
        pattern = re.compile('|'.join(re.escape(word) for word in words), re.IGNORECASE) if words else None
        color = Gdk.RGBA()
        color.parse(app.system_theme.colors['selection'])
        for label in feature_labels:
            attributes = Pango.AttrList()
            text = label.get_text()
            for match in pattern.finditer(text) if pattern else ():
                start, end = len(text[:match.start()].encode()), len(text[:match.end()].encode())
                for attribute in (Pango.attr_weight_new(Pango.Weight.BOLD),
                                  Pango.attr_background_new(int(color.red*65535), int(color.green*65535), int(color.blue*65535))):
                    attribute.start_index, attribute.end_index = start, end
                    attributes.insert(attribute)
            label.set_attributes(attributes)
        cards.invalidate_filter()
        child = cards.get_first_child()
        found = False
        while child:
            found = found or matches(child)
            child = child.get_next_sibling()
        empty.set_visible(not found)
        scroll.set_visible(found)
        scroll.get_vadjustment().set_value(0)
    search.connect('changed', filter_features)
    scroll.set_child(cards)
    outer.append(scroll)
    window.set_child(outer)
    window.set_focus(search)
    keys = Gtk.EventControllerKey()
    keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
    keys.connect('key-pressed', lambda _, key, *_args: (window.close() or True) if key == Gdk.KEY_Escape else False)
    window.add_controller(keys)
    window.connect('close-request', lambda *_: [keyboard.layout.close() for keyboard in preview_keyboards] and False)
    window.feature_switches = switches
    return window
