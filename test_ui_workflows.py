"""Mapped GTK regression workflows. Isolated preferences; no desktop actions."""
import gc
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import app
from app import Gtk, GLib, Gdk
from keyboard_view import KeyboardView


def pump(seconds=.08):
    deadline = time.monotonic() + seconds
    context = GLib.MainContext.default()
    while time.monotonic() < deadline:
        if context.pending(): context.iteration(False)
        else: time.sleep(.002)


@unittest.skipUnless(os.environ.get('GDK_BACKEND') == 'broadway',
                     'Run mapped UI tests with python tests/run.py (private display)')
class UiWorkflows(unittest.TestCase):
    def setUp(self):
        cls = self
        cls.temp = tempfile.TemporaryDirectory()
        cls.patches = []
        cls.patches.append(patch('chat_view.ChatPanel.refresh_quota'))
        for name in ('STATE', 'UI_STATE', 'LEARNED_STATE'):
            cls.patches.append(patch.object(app, name, Path(cls.temp.name) / name))
        for method in ('renew_lease', 'listen_modifiers', 'refresh_layout'):
            cls.patches.append(patch.object(KeyboardView, method, return_value=True))
        for method in ('refresh', 'refresh_targets', 'refresh_source_counts', 'focus_search', 'sync_guide_feature', 'sync_window_animations'):
            cls.patches.append(patch.object(app.Shortcuts, method, return_value=False))
        cls.patches.append(patch.object(app.shortcut_sets, 'installed', return_value=True))
        for p in cls.patches: p.start()
        cls.ui = app.Shortcuts()
        cls.ui.features = {key: True for key in app.FEATURES}
        cls.ui.set_application_id('com.aylith.Bindlume.RegressionTests.t' + str(time.monotonic_ns()))
        cls.ui.register()
        cls.ui.activate()
        cls.ui.window.present()
        pump(.2)
        self.reset_ui()

    def test_session_rename_is_inline_apply_cancel_and_empty(self):
        with patch('chat_view.available_agents', return_value=['codex']):
            self.ui.show_chat(True)
        panel = self.ui.chat_panel
        session = panel.store.create('codex', 'Original title')
        row = panel.history_row(session)
        panel.append(row)
        rename = row.get_last_child()
        windows = len(self.ui.get_windows())
        rename.emit('clicked')
        self.assertEqual(len(self.ui.get_windows()), windows)
        self.assertIs(row.rename_entry.get_parent(), row)
        row.rename_entry.set_text('   ')
        self.assertFalse(row.rename_apply.get_sensitive())
        row.rename_entry.set_text('Changed title')
        row.rename_apply.emit('clicked')
        self.assertEqual(panel.store.load(session['id'])['title'], 'Changed title')
        self.assertIsNone(row.rename_entry)
        rename.emit('clicked')
        row.rename_entry.set_text('Discard this')
        row.rename_cancel.emit('clicked')
        self.assertEqual(panel.store.load(session['id'])['title'], 'Changed title')
        rename.emit('clicked')
        row.rename_entry.set_text('Escape this')
        self.assertTrue(row.rename_keys.emit('key-pressed', Gdk.KEY_Escape, 0, Gdk.ModifierType(0)))
        self.assertEqual(panel.store.load(session['id'])['title'], 'Changed title')

    def test_search_clear_icon_tracks_text_and_resets_query(self):
        entry = self.ui.search
        position = Gtk.EntryIconPosition.SECONDARY
        entry.set_text('theme')
        self.assertEqual(entry.get_icon_name(position), 'edit-clear-symbolic')
        entry.emit('icon-release', position)
        self.assertEqual(entry.get_text(), '')
        self.assertIsNone(entry.get_icon_name(position))
        entry.set_text('@ctrl')
        self.assertEqual(entry.get_icon_name(position), 'edit-clear-symbolic')

    def tearDown(self):
        cls = self
        ui = cls.ui
        if getattr(ui, 'choice_popover', None):
            ui.choice_popover.popdown()
            ui.choice_popover.unparent()
            ui.choice_popover = None
        ui.menu_button.popdown()
        ui.app_menu_button.popdown()
        if ui.history_timer: GLib.source_remove(ui.history_timer)
        if getattr(ui, 'history_popover', None): ui.history_popover.unparent()
        for name in ('features_window','reset_window','source_library_window','preferences_window'):
            child = getattr(ui, name, None)
            if child: child.destroy()
        if getattr(ui, 'shortcuts_window', None):
            ui.shortcuts_window.destroy()
        if getattr(ui,'chat_panel',None) and ui.chat_panel.history_window: ui.chat_panel.history_window.destroy()
        ui.keyboard.stop()
        GLib.source_remove(ui.system_theme.timer)
        ui.window.destroy()
        pump()
        for p in reversed(cls.patches): p.stop()
        cls.temp.cleanup()

    def reset_ui(self):
        self.ui.source_counts = {name: 42 for name in app.SOURCES}
        self.ui.dismiss_choice()
        self.ui.menu_button.popdown()
        self.ui.window.set_visible(False)
        pump(.03)
        self.ui.window.present()
        self.ui.view_toggle.set_active(False)
        self.ui.view_stack.set_visible_child_name('list')
        self.ui.live_switch.set_active(False)
        self.ui.view_changed()
        self.ui.only_favorites.set_active(False)
        self.ui.search.set_text('')
        self.ui.learned_filter.set_selected(0)
        self.ui.type_filter.set_selected(0)
        self.ui.keyboard.manual.clear()
        self.ui.keyboard.all_button.set_active(True)
        self.ui.items = [
            dict(id='one',key='SUPER + A',name='Alpha',group='Action',kind='action',dispatcher='',arg=''),
            dict(id='two',key='SUPER SHIFT + B',name='Beta',group='Desktop App',kind='desktopApp',dispatcher='',arg='')]
        self.ui.favorites = {'one'}
        self.ui.learned = {'two'}
        self.ui.render()
        self.ui.search.grab_focus()
        pump(.15)

    def trigger(self, accelerator):
        valid, key, modifiers = Gtk.accelerator_parse(accelerator)
        self.assertTrue(valid)
        self.assertTrue(self.ui.close_on_escape(None, key, 0, modifiers))
        pump()

    def assert_choice(self, dropdown):
        self.assertTrue(self.ui.choice_popover.get_mapped())
        row = self.ui.choice_list.get_selected_row()
        self.assertEqual(row.choice_index, dropdown.get_selected())
        self.assertEqual(self.ui.window.get_focus(), row)

    def test_empty_mark_filters_disappear_and_clear(self):
        self.ui.features = {key: False for key in app.FEATURES}
        self.ui.features.update(bookmarks=True, hidden=True)
        self.ui.apply_features()
        self.ui.only_favorites.set_active(True)
        self.ui.favorite(self.ui.items[0])
        self.assertFalse(self.ui.only_favorites.get_active())
        self.assertFalse(self.ui.only_favorites.get_visible())
        self.ui.learned_filter.set_selected(1)
        self.ui.toggle_learned(self.ui.items[1])
        self.assertEqual(self.ui.learned_filter.get_selected(), 0)
        self.assertFalse(self.ui.visibility_label.get_visible())
        self.assertFalse(self.ui.menu_button.get_visible())
        self.assertEqual(len(self.ui.filtered_items()), 2)
        self.assertFalse(self.ui.action_enabled('favorites'))
        self.assertFalse(self.ui.action_enabled('learned'))

    def test_feature_presentation_persists_and_tooltip_only_fills_gaps(self):
        from unittest.mock import Mock
        self.ui.show_features()
        gallery = self.ui.features_window
        card = gallery.feature_cards.get_first_child().get_child()
        tooltip = Mock()
        self.assertFalse(card.query_feature_tooltip(card, 0, 0, False, tooltip))
        gallery.preview_switch.set_active(False)
        self.assertTrue(card.query_feature_tooltip(card, 0, 0, False, tooltip))
        content = tooltip.set_custom.call_args.args[0]
        self.assertFalse(content.get_first_child().get_visible())
        self.assertTrue(content.example.get_visible())
        gallery.description_switch.set_active(False)
        self.assertTrue(card.query_feature_tooltip(card, 0, 0, False, tooltip))
        self.assertTrue(content.get_first_child().get_visible())
        header = card.get_first_child()
        self.assertIs(header.get_first_child(), gallery.feature_switches['bookmarks'])
        gallery.layout_switch.set_active(False)
        restored = app.Shortcuts()
        self.assertEqual(restored.feature_view, dict(grid=False, previews=False, descriptions=False))
        gallery.preview_switch.set_active(True)
        card.query_feature_tooltip(card, 0, 0, False, tooltip)
        self.assertFalse(content.example.get_visible())
        self.assertTrue(content.get_first_child().get_visible())

    def test_appearance_is_optional_and_persists(self):
        self.ui.set_feature('appearance', True)
        import preferences
        preferences.show(self.ui)
        self.assertIn('look', self.ui.preferences_window.controls)
        self.ui.look_picker.set_selected(list(app.LOOKS).index('square'))
        self.assertEqual(app.Shortcuts().look, 'square')
        self.ui.set_feature('appearance', False)
        self.assertFalse(self.ui.appearance_row.get_visible())
        self.assertEqual(self.ui.look, 'square')
        self.assertEqual(self.ui.command_buttons['Features'].get_parent().get_first_child().get_next_sibling().get_next_sibling(),
                         self.ui.command_buttons['Features'])

    def test_settings_shortcuts_and_icon_columns(self):
        import preferences
        for accelerator in ('<Control>comma', '<Control><Alt>s'):
            self.trigger(accelerator)
            self.assertIsNotNone(self.ui.preferences_window)
            self.ui.preferences_window.close()
        self.ui.items[0]['type_icon'] = '⚙'
        self.ui.preferences['action_icons'] = True
        rows = [self.ui.shortcut_row(item, columns=True) for item in self.ui.items]
        for row in rows:
            content = row.get_first_child().get_child()
            name_row = content.get_last_child()
            self.assertTrue(name_row.get_first_child().has_css_class('shortcut-icon-column'))
        self.ui.set_preference('app_icons', False)
        self.ui.set_preference('action_icons', False)
        row = self.ui.shortcut_row(self.ui.items[0], columns=True)
        self.assertTrue(row.get_first_child().get_child().get_last_child().get_first_child().has_css_class('shortcut-name'))

    def test_cached_icons_disappear_after_preferences_change(self):
        self.ui.items[0]['type_icon'] = '⚙'
        self.ui.columns = True
        self.ui.flat_list = True
        self.ui.set_preference('action_icons', True)
        self.ui.set_preference('app_icons', True)
        pump()
        def descendants(widget):
            yield widget
            child = widget.get_first_child()
            while child:
                yield from descendants(child)
                child = child.get_next_sibling()
        def icons():
            return [w for w in descendants(self.ui.list_box) if w.has_css_class('shortcut-icon-column')]
        self.assertTrue(icons())
        for _ in range(2):
            self.ui.search.set_text('Beta')
            self.ui.render()
            pump()
            self.ui.search.set_text('')
            self.ui.render()
            pump()
        self.ui.set_preference('app_icons', False)
        self.ui.set_preference('action_icons', False)
        pump()
        self.assertFalse(icons())
        self.ui.search.set_text('Beta')
        self.ui.render()
        pump()
        self.ui.search.set_text('')
        self.ui.render()
        pump()
        self.assertFalse(icons())
        self.ui.set_preference('action_icons', True)
        pump()
        self.assertTrue(icons())

    def test_agent_inputs_and_surface_navigation(self):
        from agent_control import execute
        def call(operation, **arguments): return execute(self.ui,dict(operation=operation,arguments=arguments))
        self.ui.features = app.DEFAULT_FEATURES.copy(); self.ui.apply_features()
        before = dict(self.ui.input_controls.config)
        with self.assertRaises(ValueError): call('inputs',gestures={'left':'invalid'},controller=True)
        self.assertEqual(before,self.ui.input_controls.config)
        result=call('inputs',gestures={'left':'search'},buttons={'0':'clear'})
        self.assertEqual(result['settings']['gestures']['left'],'search')
        self.assertTrue(self.ui.feature_enabled('inputs'))
        call('open',surface='settings')
        self.assertIsNotNone(self.ui.preferences_window)
        call('view',modifiers=['CTRL'],all_layers=False)
        self.assertEqual(self.ui.keyboard.manual,{'CTRL'})
        self.assertTrue(self.ui.feature_enabled('layouts'))
        self.assertFalse(self.ui.keyboard.all_layers)

    def test_search_and_feature_changes_preserve_window_geometry(self):
        self.ui.features = app.DEFAULT_FEATURES.copy(); self.ui.apply_features()
        self.ui.items = [dict(id=str(i),key=f'F{i}',name=f'Action {i}',kind='action',group='Action',dispatcher='',arg='') for i in range(60)]
        self.ui.render(); pump(.15)
        before=tuple(self.ui.window.get_default_size())
        self.ui.search.set_text('no matches'); pump(.15)
        self.assertEqual(before,tuple(self.ui.window.get_default_size()))
        self.ui.show_chat(); pump(.15)
        chat_size=tuple(self.ui.window.get_default_size())
        self.ui.set_feature('layouts',True); pump(.15)
        self.assertEqual(chat_size,tuple(self.ui.window.get_default_size()))
        self.ui.show_chat(False); pump(.1)
        self.assertEqual(before,tuple(self.ui.window.get_default_size()))

    def test_agent_type_filter_enables_prerequisites_and_validates_atomically(self):
        from agent_control import execute
        def view(**args): return execute(self.ui, {'operation':'view','arguments':args})
        self.ui.features = app.DEFAULT_FEATURES.copy()
        self.ui.items.append(dict(id='web',key='SUPER + Y',name='YouTube',kind='webapp',group='Web App',dispatcher='',arg=''))
        self.ui.apply_features()
        before = self.ui.features.copy()
        with self.assertRaises(ValueError): view(type='invalid', search='bad')
        self.assertEqual(before, self.ui.features)
        self.assertEqual(self.ui.search.get_text(), '')
        result = view(type='webapp')
        self.assertEqual(result['enabled_features'], ['layouts'])
        self.assertTrue(self.ui.filter_bar.get_visible())
        self.assertEqual([r['id'] for r in self.ui.filtered_items()], ['web'])
        self.assertEqual(result['filters']['type'], 'webapp')
        self.assertFalse(self.ui.preferences['chat_memory_enabled'])
        view(layout='keyboard')
        self.assertTrue(self.ui.feature_enabled('keyboard'))

    def test_search_returns_to_top_and_hover_preserves_selection(self):
        self.ui.window.set_size_request(900, 560)
        self.ui.flat_list = True
        self.ui.items = [dict(id=str(i),key=f'F{i}',name=f'Match {i}',kind='action',group='Action',dispatcher='',arg='') for i in range(80)]
        self.ui.render(); pump(.2)
        # Broadway has no browser client in CI; allocate the content explicitly.
        self.ui.main_pane.allocate(900, 560, -1, None); pump(.2)
        self.ui.list_selection.set_selected(50)
        self.ui.list_scroll.get_vadjustment().set_value(400); pump(.15)
        self.assertGreater(self.ui.list_scroll.get_vadjustment().get_value(), 0)
        self.ui.search.set_text('Match'); pump(.2)
        self.assertAlmostEqual(self.ui.list_scroll.get_vadjustment().get_value(), 0, delta=1)
        self.assertEqual(self.ui.list_selection.get_selected(), Gtk.INVALID_LIST_POSITION)
        # Pointer motion must preserve keyboard selection and input focus.
        wrappers=[]
        def scan(widget):
            controllers=widget.observe_controllers()
            for i in range(controllers.get_n_items()):
                c=controllers.get_item(i)
                if isinstance(c, Gtk.EventControllerMotion) and isinstance(widget,Gtk.Box) and widget.get_parent() and widget.get_parent().get_css_name()=='row': wrappers.append(c)
            child=widget.get_first_child()
            while child: scan(child); child=child.get_next_sibling()
        scan(self.ui.list_box)
        self.assertGreaterEqual(len(wrappers),2)
        self.ui.list_selection.set_selected(1)
        self.ui.search.grab_focus()
        focus = self.ui.window.get_focus()
        wrappers[0].emit('motion',10.,10.)
        wrappers[1].emit('motion',10.,10.)
        pump(.1)
        self.assertEqual(self.ui.list_selection.get_selected(), 1)
        self.assertEqual(self.ui.window.get_focus(), focus)

    def test_set_library_categories_two_columns_and_translated_search(self):
        import source_library, localization
        self.ui.source_counts.update({'Chromium':30,'Google Chrome':30})
        self.ui.set_preference('language','hu')
        source_library.show(self.ui); window=self.ui.source_library_window; pump(.15)
        grid,members=window.category_grids['browsers']
        self.assertEqual(members,['Chromium','Google Chrome'])
        self.assertIsNotNone(grid.get_child_at(0,0))
        self.assertIsNotNone(grid.get_child_at(1,0))
        window.source_search.set_text('Böngészők'); pump(.3)
        self.assertEqual(set(window.category_grids),{'browsers'})
        self.ui.set_preference('language','en')

    def test_agent_api_updates_running_state_and_rejects_invalid_changes(self):
        from agent_control import execute
        def call(operation, **arguments): return execute(self.ui,dict(operation=operation,arguments=arguments))
        self.assertEqual(call('search',query='Alpha',source=self.ui.source_name)[0]['id'],'one')
        call('bookmark',id='two',enabled=True)
        self.assertIn('two',app.Shortcuts().favorites)
        call('hide',id='one',enabled=True)
        self.assertIn('one',app.Shortcuts().learned)
        self.assertEqual(self.ui.learned_filter.get_selected(),2)
        call('features',name='all',enabled=False)
        self.assertFalse(any(self.ui.features.values()))
        self.assertIn('one',self.ui.learned)
        call('features',name='all',enabled=True)
        self.assertTrue(all(self.ui.features.values()))
        call('settings',key='app_icons',value=False)
        self.assertFalse(app.Shortcuts().preferences['app_icons'])
        with self.assertRaises(ValueError): call('settings',key='font_size',value=-10)
        with self.assertRaises(ValueError): call('bookmark',id='missing',enabled=True)
        with self.assertRaises(ValueError): call('features',name='not-real',enabled=True)
        before = self.ui.search.get_text()
        with self.assertRaises(ValueError): call('view',search='changed',visibility='wrong')
        self.assertEqual(self.ui.search.get_text(),before)
        preview = call('reset')
        self.assertTrue(preview)
        self.assertTrue(self.ui.learned)
        call('reset',apply=True,categories=[row['id'] for row in preview])
        self.assertFalse(call('reset'))

    def test_chat_panel_history_focus_and_persistence(self):
        from chat import SessionStore
        with patch('chat_view.available_agents',return_value=['codex']):
            self.ui.set_feature('agent',True)
            self.trigger('<Control>j')
            panel = self.ui.chat_panel
            self.assertIs(self.ui.window.get_focus(),panel.input)
            self.assertIs(self.ui.main_pane.get_end_child(),panel)
            saved = panel.store.create('codex','Screenshot tips')
            saved['messages'].append(dict(role='assistant',content='Use Print.',created_at=saved['created_at']))
            panel.store.save(saved)
            self.trigger('<Control><Shift>h')
            history = panel.history_window
            self.assertTrue(history.get_focus().is_ancestor(history.search))
            history.search.set_text('Screenshot')
            pump(.2)
            history.search.emit('activate')
            pump()
            self.assertEqual(panel.session['id'],saved['id'])
            self.assertIsNone(panel.history_window)
            self.assertIs(self.ui.window.get_focus(),panel.input)
            panel.store.rename(panel.session,'Capture reference')
            self.ui.show_chat(False)
            self.assertIsNone(self.ui.main_pane.get_end_child())
            self.ui.set_feature('agent',False)
            self.assertEqual(SessionStore(panel.store.root).list()[0]['title'],'Capture reference')
            self.assertFalse(self.ui.chat_button.get_visible())

    def test_dialog_escape_preserves_focus_and_falls_back_to_search(self):
        import preferences, source_library
        self.ui.chat_button.grab_focus()
        before = self.ui.window.get_focus()
        preferences.show(self.ui)
        window = self.ui.preferences_window
        window.dialog_keys.emit('key-pressed', Gdk.KEY_Escape, 0, Gdk.ModifierType(0))
        pump()
        self.assertFalse(window.get_visible())
        self.assertIs(self.ui.window.get_focus(), before)
        self.ui.window.set_focus(None)
        source_library.show(self.ui)
        window = self.ui.source_library_window
        self.assertTrue(window.get_focus().is_ancestor(window.search) if hasattr(window, 'search') else True)
        window.dialog_keys.emit('key-pressed', Gdk.KEY_Escape, 0, Gdk.ModifierType(0))
        pump()
        focus = self.ui.window.get_focus()
        self.assertTrue(focus is self.ui.search or focus.is_ancestor(self.ui.search))

    def test_restart_label_resets_when_release_reaches_main_window(self):
        button=self.ui.command_buttons['Quit']
        self.ui.restart_shift_key(Gdk.KEY_Shift_L,True)
        self.assertEqual(button.get_label(),'Restart')
        self.ui.live_key_released(None,Gdk.KEY_Shift_L,0,0)
        self.assertEqual(button.get_label(),'Quit')
        self.ui.restart_shift_key(Gdk.KEY_Shift_L,True)
        self.ui.stop_restart_watch()
        self.assertEqual(button.get_label(),'Quit')

    def test_shift_changes_quit_label_and_restart_preserves_draft(self):
        import json,stat
        button=self.ui.command_buttons['Quit']
        self.ui.restart_shift_key(Gdk.KEY_Shift_L,True)
        self.assertEqual(button.get_label(),'Restart')
        self.ui.restart_shift_key(Gdk.KEY_Shift_L,False)
        self.assertEqual(button.get_label(),'Quit')
        with patch('chat_view.available_agents',return_value=['codex']):self.ui.show_chat(True)
        self.ui.chat_panel.input.get_buffer().set_text('Unsent héllo\nsecond line')
        with patch.object(self.ui,'quit') as quit:
            self.ui.restart_modifiers_changed(None,Gdk.ModifierType.SHIFT_MASK)
            button.emit('clicked')
            quit.assert_called_once()
        path=Path(self.ui._restart_file)
        try:
            self.assertEqual(json.loads(path.read_text())['draft'],'Unsent héllo\nsecond line')
            self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)
            with patch.dict(os.environ,{'BINDLUME_RESTART_FILE':str(path)}):
                self.ui.chat_panel.input.get_buffer().set_text('')
                self.ui.restore_restart()
            buffer=self.ui.chat_panel.input.get_buffer()
            self.assertEqual(buffer.get_text(buffer.get_start_iter(),buffer.get_end_iter(),True),'Unsent héllo\nsecond line')
            self.assertFalse(path.exists())
        finally:path.unlink(missing_ok=True)

    def test_chat_line_editing_shortcuts_are_unicode_safe_and_undoable(self):
        with patch('chat_view.available_agents',return_value=['codex']):self.ui.show_chat(True)
        panel=self.ui.chat_panel;buffer=panel.input.get_buffer();buffer.set_enable_undo(True)
        buffer.set_text('first\nhéllo world\nlast')
        buffer.place_cursor(buffer.get_iter_at_offset(11))
        panel.input_key(None,Gdk.KEY_u,0,Gdk.ModifierType.CONTROL_MASK)
        self.assertEqual(buffer.get_text(buffer.get_start_iter(),buffer.get_end_iter(),True),'first\n world\nlast')
        buffer.undo()
        buffer.place_cursor(buffer.get_iter_at_offset(11))
        panel.input_key(None,Gdk.KEY_k,0,Gdk.ModifierType.CONTROL_MASK)
        self.assertEqual(buffer.get_text(buffer.get_start_iter(),buffer.get_end_iter(),True),'first\nhéllo\nlast')
        panel.input_key(None,Gdk.KEY_k,0,Gdk.ModifierType.CONTROL_MASK)
        self.assertEqual(buffer.get_text(buffer.get_start_iter(),buffer.get_end_iter(),True),'first\nhéllolast')

    def test_chat_split_is_saved_and_restored(self):
        with patch('chat_view.available_agents',return_value=['codex']):
            self.ui.show_chat(True);pump(.3)
        self.ui.main_pane.set_position(round(self.ui.main_pane.get_width()*.5));pump()
        saved=self.ui.chat_split_ratio
        self.assertAlmostEqual(saved,.5,delta=.03)
        restored=app.Shortcuts()
        self.assertAlmostEqual(restored.chat_split_ratio,saved,delta=.01)
        self.ui.show_chat(False);pump()
        self.ui.show_chat(True);pump(.3)
        self.assertAlmostEqual(self.ui.chat_split_ratio,saved,delta=.03)

    def test_harness_paths_are_collapsed_and_versions_load_on_demand(self):
        import companion
        with patch('chat.available_agents',return_value=['codex']),patch('companion.harness_version',return_value='codex 1.2.3') as version:
            companion.show(self.ui);pump()
            window=self.ui.companion_window
            group=window.harness_details['codex']
            self.assertFalse(group.get_expanded());version.assert_not_called()
            group.set_expanded(True);pump(.2)
            version.assert_called_once()
            window.close()

    def test_source_footer_reachable_with_arrow_keys(self):
        self.ui.open_choice(self.ui.source_picker,from_control=True);pump()
        self.ui.choice_key_handler(None,Gdk.KEY_End,0,0)
        focus=self.ui.window.get_focus()
        self.assertIsInstance(focus,Gtk.Button)
        self.assertEqual(focus.get_label(),'Choose shortcut sets…')
        self.ui.choice_key_handler(None,Gdk.KEY_Up,0,0)
        self.assertIsInstance(self.ui.window.get_focus(),Gtk.ListBoxRow)
        self.ui.choice_key_handler(None,Gdk.KEY_Down,0,0)
        self.assertIs(self.ui.window.get_focus(),focus)
        for button in self.ui.command_buttons.values():self.assertEqual(button.get_child().get_xalign(),0)

    def test_conversation_provider_unlocks_and_selection_applies_next_turn(self):
        from unittest.mock import Mock
        with patch('chat_view.available_agents',return_value=['codex','claude']):
            self.ui.show_chat(True);pump()
        panel=self.ui.chat_panel
        panel.session=panel.store.create('codex','Provider switching')
        panel.run=Mock();panel.update_busy()
        self.assertFalse(panel.agent.get_sensitive())
        panel.event('done',dict(panel.session,status='ready'))
        self.assertTrue(panel.agent.get_sensitive())
        panel.agent.set_selected(panel.agent_choices.index('claude'))
        self.assertEqual(panel.session['selection'],'claude')
        with patch.object(panel,'begin_send') as send:
            panel.dispatch('Continue')
            send.assert_called_once_with('Continue','claude','claude')

    def test_usage_selector_shows_one_provider_and_preserves_choice(self):
        with patch('chat_view.available_agents',return_value=['codex','claude']):
            self.ui.show_chat(True);pump()
        panel=self.ui.chat_panel
        quotas={'codex':{'windows':[{'name':'weekly','remaining_percent':84}]},'claude':{'windows':[{'name':'weekly','remaining_percent':62}]}}
        panel.quota_ready(quotas)
        self.assertIn('84% left',panel.usage_picker.get_model().get_string(0))
        panel.usage_picker.set_selected(1)
        self.assertEqual(panel.usage_provider,'claude')
        panel.quota_ready(quotas)
        self.assertEqual(panel.usage_picker.get_selected(),1)

    def test_chat_with_outlier_stays_inside_available_bounds(self):
        from unittest.mock import Mock
        long_key=' / '.join('PREFIX + CTRL + '+d for d in ('LEFT','DOWN','UP','RIGHT'))
        self.ui.items=[dict(id=str(i),key=k,name='Resize pane',group='Panes',dispatcher='',arg='')
                       for i,k in enumerate(['CTRL + LEFT','CTRL + RIGHT',long_key])]
        self.ui.columns=True;self.ui.render();pump()
        previous=self.ui.overlay_surfaces
        self.ui.overlay_surfaces=Mock()
        self.ui.overlay_surfaces.available_bounds.return_value=(900,650)
        try:
            with patch('chat_view.available_agents',return_value=['codex']):
                self.ui.show_chat(True);pump(.3)
            self.assertLessEqual(self.ui.window.get_default_size()[0],860)
            self.assertLessEqual(self.ui.main_pane.measure(Gtk.Orientation.HORIZONTAL,-1)[0],860)
            self.assertLessEqual(self.ui.window.get_default_size()[1],610)
            self.assertLessEqual(self.ui.shortcut_column_width,320)
            self.assertIsNotNone(self.ui.main_pane.get_end_child())
        finally:self.ui.overlay_surfaces=previous

    def test_chat_toggle_width_queue_and_history_escape(self):
        from unittest.mock import Mock
        with patch('chat_view.available_agents', return_value=['codex']):
            before = self.ui.window.get_default_size()
            self.trigger('<Control>j')
            panel = self.ui.chat_panel
            self.assertFalse(panel.copy_button.get_visible())
            monitor = self.ui.window.get_display().get_monitor_at_surface(self.ui.window.get_surface())
            self.assertEqual(self.ui.window.get_default_size()[0], min(before[0]+400,monitor.get_geometry().width-40))
            self.trigger('<Control>j')
            self.assertIsNone(self.ui.main_pane.get_end_child())
            self.assertEqual(self.ui.window.get_default_size(), before)
            self.ui.chat_button.emit('clicked'); pump()
            self.assertIs(self.ui.main_pane.get_end_child(), panel)
            panel.history(); pump()
            history = panel.history_window
            self.assertTrue(history.get_focus().is_ancestor(history.search))
            history.dialog_keys.emit('key-pressed', Gdk.KEY_Escape, 0, Gdk.ModifierType(0));pump()
            self.assertIsNone(panel.history_window)
            panel.session = panel.store.create('codex','Queued test')
            panel.run = Mock()
            panel.reply = Mock()
            panel.event('reply','One')
            panel.event('reply','One two')
            pump(.07)
            panel.reply.set_text.assert_called_once_with('One two')
            panel.input.get_buffer().set_text('First queued request');panel.send()
            panel.input.get_buffer().set_text('Second queued request');panel.send()
            self.assertEqual(panel.pending,['First queued request','Second queued request'])
            self.assertTrue(panel.input_placeholder.get_visible())
            self.assertFalse(panel.send_button.get_sensitive())
            panel.input.get_buffer().set_text('  ')
            self.assertFalse(panel.send_button.get_sensitive())
            panel.input.get_buffer().set_text('Next question')
            self.assertTrue(panel.send_button.get_sensitive())
            self.assertFalse(panel.input_placeholder.get_visible())
            panel.input.get_buffer().set_text('')
            self.assertTrue(panel.input.get_sensitive())
            self.assertTrue(panel.spinner.get_spinning())
            self.assertEqual(panel.store.load(panel.session['id'])['queued_messages'], panel.pending)
            panel.remove_queued(1)
            panel.session['status'] = 'ready'
            with patch.object(panel,'dispatch') as dispatch:
                panel.event('done',panel.session)
                dispatch.assert_called_once_with('First queued request')
            self.assertFalse(panel.spinner.get_spinning())

    def test_dynamic_translations_and_common_guide_controls(self):
        import localization, preferences, guide_settings
        try:
            localization.set_language(self.ui,'hu')
            preferences.show(self.ui);pump()
            theme = self.ui.preferences_window.controls['theme']
            for key in ('look', 'theme', 'window_animations'):
                resolved = self.ui.preferences_window.controls[key].get_model().get_string(0)
                self.assertTrue(resolved.startswith('Rendszer ('), resolved)
                self.assertTrue(resolved.endswith(')'), resolved)
            from theme import LOOKS, detected_look
            self.assertEqual(self.ui.preferences_window.controls['look'].get_model().get_string(0),
                             'Rendszer (' + ('Omarchy → ' if detected_look() == 'square' else '') + localization.text(LOOKS[detected_look()]['name']) + ')')
            theme.set_selected(2);pump()
            def labels(widget):
                result = [widget.get_text()] if isinstance(widget,Gtk.Label) else []
                child = widget.get_first_child()
                while child: result += labels(child);child=child.get_next_sibling()
                return result
            self.assertIn('Világos',labels(theme))
            self.assertIn('look',self.ui.preferences_window.controls)
            self.ui.preferences_window.close();pump()
            with patch('guide_settings.GuideController.read',return_value=guide_settings.defaults()),patch('guide_settings.GuideController.backend',return_value=[]):
                self.ui.show_guide();pump(.3)
                window=self.ui.guide_window
                self.assertIsInstance(window.controls['showIcons'],Gtk.Switch)
                self.assertIn('showHiddenItems',window.controls)
                self.assertIn('Műveletikonok',labels(window))
                window.dialog_keys.emit('key-pressed',Gdk.KEY_Escape,0,Gdk.ModifierType(0));pump()
                self.assertIsNone(self.ui.guide_window)
        finally:
            localization.set_language(self.ui,'en')

    def test_shared_global_picker_and_guide_overlay(self):
        import preferences, source_library
        from shortcut_manager import ShortcutPicker
        preferences.show(self.ui)
        picker = self.ui.preferences_window.controls['global_hotkey']
        self.assertIsInstance(picker, ShortcutPicker)
        self.assertEqual(picker.get_chord(), 'SUPER + SHIFT + K')
        pump()
        picker.capture.set_active(True)
        pump()
        self.assertEqual(picker.capture.get_label(), 'Press shortcut…')
        self.assertTrue(picker.capture.has_focus())
        picker.capture_controller.emit('key-pressed', Gdk.KEY_Control_L, 0, Gdk.ModifierType.CONTROL_MASK)
        self.assertTrue(picker.capture.get_active())
        picker.capture_controller.emit('key-pressed', Gdk.KEY_k, 0, Gdk.ModifierType.SUPER_MASK)
        self.assertEqual(picker.get_chord(), 'SUPER + K')
        self.assertFalse(picker.capture.get_active())
        self.assertIsNone(picker.capture_surface)
        picker.capture.set_active(True)
        self.ui.preferences_window.dialog_keys.emit('key-pressed', Gdk.KEY_Escape, 0, Gdk.ModifierType(0))
        self.assertFalse(picker.capture.get_active())
        self.assertTrue(self.ui.preferences_window.get_visible())
        picker.capture.set_active(True)
        self.ui.preferences_window.close()
        self.assertFalse(picker.capture.get_active())
        self.assertIsNone(picker.capture_surface)
        source_library.show(self.ui)
        library = self.ui.source_library_window
        library.open_guide()
        guide = library.guide_window
        pump()
        self.assertTrue(guide.get_mapped())
        self.assertIn('Read the guide at this local path first:', guide.copy_values['agent-path'])
        self.assertNotIn('## Format', guide.copy_values['agent-path'])
        self.assertIn('## Format', guide.copy_values['agent-content'])
        self.assertEqual(guide.copy_values['content'], guide.path.read_text())
        for kind in guide.copy_values:
            guide.copy(kind)
            result = []
            clipboard = guide.get_clipboard()
            clipboard.read_text_async(None, lambda obj, value: result.append(obj.read_text_finish(value)))
            pump()
            self.assertEqual(result, [guide.copy_values[kind]])
        controllers = guide.observe_controllers()
        keys = next(controllers.get_item(i) for i in range(controllers.get_n_items())
                    if isinstance(controllers.get_item(i), Gtk.EventControllerKey))
        self.assertTrue(keys.emit('key-pressed', Gdk.KEY_Escape, 0, Gdk.ModifierType(0)))
        pump()
        self.assertIsNone(library.guide_window)

    def test_language_roundtrip_and_source_trigger_without_count(self):
        import preferences, localization
        preferences.show(self.ui)
        with patch.object(app.GuideController, 'patch'):
            self.ui.set_preference('language', 'hu')
            pump()
            label = self.ui.command_buttons['Features'].get_child()
            self.assertEqual(label.get_text(), 'Funkciók')
            self.ui.set_preference('language', 'en')
            pump()
            self.assertEqual(label.get_text(), 'Features')
        for box in self.ui.source_badges:
            if not hasattr(box, 'star'):
                self.assertFalse(box.badge.get_visible())

    def test_new_profile_is_clean_and_target_popup_anchors_to_view_settings(self):
        with patch.object(app, 'UI_STATE', Path(self.temp.name) / 'fresh-profile'):
            fresh = app.Shortcuts()
        self.assertEqual(fresh.features, app.DEFAULT_FEATURES)
        self.assertTrue(fresh.flat_list and fresh.columns)
        self.ui.features = app.DEFAULT_FEATURES.copy()
        self.ui.apply_features()
        self.assertFalse(self.ui.only_favorites.get_visible())
        self.assertFalse(self.ui.view_toggle.get_visible())
        self.assertFalse(self.ui.menu_button.get_visible())
        self.ui.set_feature('target', True)
        self.trigger('<Alt>w')
        self.assert_choice(self.ui.target)
        self.assertEqual(self.ui.choice_popover.get_parent(), self.ui.menu_button)
        self.ui.dismiss_choice()
        self.trigger('F10')
        self.ui.open_choice(self.ui.target, from_control=True)
        pump()
        self.assertEqual(self.ui.choice_popover.get_parent(), self.ui.target)
        self.ui.menu_button.popdown()
        pump()
        self.assertFalse(self.ui.choice_popover.get_visible())

    def test_features_keep_marks_but_remove_filters_and_shortcuts(self):
        self.ui.favorites = {'one'}
        self.ui.learned = {'two'}
        self.ui.only_favorites.set_active(True)
        self.ui.learned_filter.set_selected(1)
        self.ui.set_feature('bookmarks', False)
        self.ui.set_feature('hidden', False)
        self.assertEqual(self.ui.favorites, {'one'})
        self.assertEqual(self.ui.learned, {'two'})
        self.assertFalse(self.ui.only_favorites.get_active())
        self.assertFalse(self.ui.only_favorites.get_visible())
        self.assertEqual(self.ui.learned_filter.get_selected(), 0)
        self.assertFalse(self.ui.learned_filter.get_visible())
        self.assertEqual(len(self.ui.filtered_items()), 2)
        self.assertFalse(self.ui.action_enabled('bookmark_row'))
        self.assertFalse(self.ui.action_enabled('learn_row'))
        self.ui.shortcut_action('favorites')
        self.assertFalse(self.ui.only_favorites.get_active())
        row = self.ui.shortcut_row(self.ui.items[0])
        self.assertFalse(row.get_last_child().get_visible())
        self.assertFalse(row.get_last_child().get_prev_sibling().get_visible())
        self.ui.set_feature('bookmarks', True)
        self.assertEqual(self.ui.favorites, {'one'})

    def test_feature_gallery_uses_inert_sample_rows(self):
        self.ui.show_features()
        pump(.2)
        window = self.ui.features_window
        self.assertEqual(set(window.feature_switches), set(app.FEATURES))
        with patch.object(self.ui, 'run_action') as run:
            row = self.ui.shortcut_row(self.ui.items[0], preview=True)
            row.get_first_child().emit('clicked')
            run.assert_not_called()
        window.close()

    def test_search_history_suggestions_persist_and_keyboard_focus(self):
        self.ui.search.set_text('terminal')
        self.ui.remember_search()
        self.ui.search.set_text('term')
        pump()
        self.assertTrue(self.ui.history_popover.get_visible())
        self.trigger('Down')
        self.assertEqual(self.ui.window.get_focus(), self.ui.history_buttons[0])
        self.ui.history_buttons[0].emit('clicked')
        self.assertEqual(self.ui.search.get_text(), 'terminal')
        self.assertFalse(self.ui.history_popover.get_visible())
        restored = app.Shortcuts()
        self.assertIn('terminal', restored.search_history)
        self.ui.set_feature('history', False)
        self.ui.search.set_text('other')
        self.ui.remember_search()
        self.assertNotIn('other', self.ui.search_history)

    def test_selective_reset_counts_hover_and_clear_all(self):
        self.ui.favorites = {'one'}
        self.ui.learned = {'two'}
        self.ui.search_history = []
        self.ui.show_reset()
        window = self.ui.reset_window
        self.assertNotIn('history', window.reset_switches)
        self.assertEqual(window.reset_counts['bookmarks'], 1)
        self.assertEqual(window.reset_counts['hidden'], 1)
        window.clear_all_switch.set_active(False)
        self.assertFalse(any(toggle.get_active() for toggle in window.reset_switches.values()))
        self.assertFalse(window.confirm_button.get_sensitive())
        window.reset_switches['bookmarks'].set_active(True)
        self.assertFalse(window.clear_all_switch.get_active())
        self.assertTrue(window.confirm_button.get_sensitive())
        row = window.reset_rows['bookmarks']
        controllers = row.observe_controllers()
        motion = next(controllers.get_item(i) for i in range(controllers.get_n_items()) if isinstance(controllers.get_item(i), Gtk.EventControllerMotion))
        motion.emit('enter', 1.0, 1.0)
        self.assertIn('Alpha', window.reset_preview.get_text())
        window.confirm_button.emit('clicked')
        self.assertFalse(self.ui.favorites)
        self.assertEqual(self.ui.learned, {'two'})
        self.assertTrue(self.ui.feature_enabled('hidden'))

    def test_reset_badges_remain_aligned_when_preview_and_selection_change(self):
        self.ui.favorites = {'one'}
        self.ui.learned = {'two'}
        self.ui.show_reset()
        pump(.2)
        window = self.ui.reset_window
        def badge_positions():
            return [row.get_last_child().compute_bounds(window)[1].get_x()
                    for row in window.reset_rows.values()]
        for key, row in window.reset_rows.items():
            self.assertIs(row.get_first_child(), window.reset_switches[key])
        self.assertIs(window.clear_all_switch.get_parent().get_first_child(), window.clear_all_switch)
        before = badge_positions()
        self.assertTrue(all(abs(x-before[0]) < 1 for x in before))
        row = window.reset_rows['bookmarks']
        controllers = row.observe_controllers()
        motion = next(controllers.get_item(i) for i in range(controllers.get_n_items()) if isinstance(controllers.get_item(i), Gtk.EventControllerMotion))
        motion.emit('enter', 1.0, 1.0)
        pump()
        window.reset_switches['bookmarks'].set_active(False)
        pump()
        self.assertEqual(badge_positions(), before)
        window.clear_all_switch.set_active(False)
        pump()
        self.assertEqual(badge_positions(), before)

    def test_empty_reset_has_no_switches_and_cannot_confirm(self):
        self.ui.reset_defaults()
        self.ui.show_reset()
        self.assertEqual(self.ui.reset_window.reset_switches, {})
        self.assertFalse(self.ui.reset_window.clear_all_switch.get_parent().get_visible())
        self.assertFalse(self.ui.reset_window.confirm_button.get_sensitive())
        self.assertFalse(self.ui.reset_window.confirm_button.get_visible())
        controls = self.ui.reset_window.get_child().get_last_child()
        self.assertEqual(controls.get_first_child().get_label(), 'Close')
        self.assertLess(self.ui.reset_window.get_default_size().height, 400)

    def test_reset_review_is_non_destructive_until_confirmed(self):
        self.ui.favorites = {'one'}
        self.ui.learned = {'two'}
        self.ui.search_history = ['terminal']
        details = str(self.ui.reset_changes())
        self.assertIn('Alpha', details)
        self.assertIn('Beta', details)
        self.assertIn('terminal', details)
        self.ui.show_reset()
        self.ui.reset_window.close()
        self.assertEqual(self.ui.favorites, {'one'})
        self.ui.reset_defaults()
        self.assertFalse(self.ui.favorites or self.ui.learned or self.ui.search_history)
        self.assertEqual(self.ui.features, app.DEFAULT_FEATURES)
        self.assertTrue(self.ui.flat_list and self.ui.columns)
        self.assertFalse(self.ui.view_toggle.get_visible())

    def test_live_list_filters_modifiers_keys_and_releases(self):
        self.ui.live_switch.set_active(True)
        self.assertTrue(self.ui.keyboard.suppress_guide)
        self.assertTrue(self.ui.close_on_escape(None, Gdk.KEY_Super_L, 133, Gdk.ModifierType(0)))
        self.ui.close_on_escape(None, Gdk.KEY_Shift_L, 50, Gdk.ModifierType.SUPER_MASK)
        self.assertEqual([r['id'] for r in self.ui.filtered_items()], ['two'])
        self.ui.close_on_escape(None, Gdk.KEY_B, 56, Gdk.ModifierType.SUPER_MASK | Gdk.ModifierType.SHIFT_MASK)
        self.assertEqual([r['id'] for r in self.ui.filtered_items()], ['two'])
        self.assertEqual(self.ui.search.get_text(), '')
        self.ui.live_key_released(None, Gdk.KEY_B, 56, 0)
        self.ui.live_key_released(None, Gdk.KEY_Shift_L, 50, 0)
        self.assertEqual(len(self.ui.filtered_items()), 2)
        self.ui.close_on_escape(None, Gdk.KEY_Escape, 9, 0)
        self.assertFalse(self.ui.live_view)
        self.assertFalse(self.ui.keyboard.suppress_guide)
        self.assertFalse(self.ui.live_keys or self.ui.live_mods)

    def test_live_modifiers_only_and_shifted_key_use_native_state(self):
        self.ui.live_switch.set_active(True)
        self.ui.live_modifiers_changed(None, Gdk.ModifierType.SUPER_MASK | Gdk.ModifierType.SHIFT_MASK)
        self.assertEqual([r['id'] for r in self.ui.filtered_items()], ['two'])
        self.ui.live_key(10, Gdk.KEY_exclam, True, Gdk.KEY_1)
        self.assertEqual(set(self.ui.live_keys.values()), {'1'})
        self.ui.live_key_released(None, Gdk.KEY_Shift_L, 50, 0)
        self.assertNotIn('SHIFT', self.ui.live_mods.values())
        self.ui.live_key_released(None, Gdk.KEY_exclam, 10, 0)
        self.ui.live_modifiers_changed(None, Gdk.ModifierType(0))
        self.assertEqual(len(self.ui.filtered_items()), 2)

    def test_live_modifier_buttons_temporarily_reflect_held_keys(self):
        buttons = self.ui.keyboard.buttons
        buttons['ALT'].set_active(True)
        self.ui.live_switch.set_active(True)
        self.ui.live_key(133, Gdk.KEY_Super_L, True)
        self.ui.live_key(50, Gdk.KEY_Shift_L, True)
        for modifier in ('SUPER', 'SHIFT', 'ALT'):
            self.assertTrue(buttons[modifier].get_state_flags() & Gtk.StateFlags.CHECKED)
        self.assertFalse(buttons['SUPER'].get_active())
        self.assertFalse(buttons['SHIFT'].get_active())
        self.assertEqual(self.ui.keyboard.manual, {'ALT'})
        self.ui.live_key_released(None, Gdk.KEY_Shift_L, 50, 0)
        self.assertFalse(buttons['SHIFT'].get_state_flags() & Gtk.StateFlags.CHECKED)
        self.assertTrue(buttons['SUPER'].get_state_flags() & Gtk.StateFlags.CHECKED)
        self.ui.live_switch.set_active(False)
        self.assertFalse(buttons['SUPER'].get_state_flags() & Gtk.StateFlags.CHECKED)
        self.assertTrue(buttons['ALT'].get_active())
        self.assertTrue(buttons['ALT'].get_state_flags() & Gtk.StateFlags.CHECKED)
        self.assertEqual(self.ui.keyboard.manual, {'ALT'})

    def test_live_click_dispatches_while_modifiers_held(self):
        self.ui.live_switch.set_active(True)
        self.ui.live_key(133, Gdk.KEY_Super_L, True)
        self.ui.live_key(37, Gdk.KEY_Control_L, True)
        item = dict(self.ui.items[0], dispatcher='exec', arg='test-action')
        row = self.ui.shortcut_row(item)
        action = row.get_first_child()
        with patch.object(self.ui, 'run_action') as run:
            action.emit('clicked')
            run.assert_called_once_with(item)

    def test_direct_choice_from_settings_survives_parent_close(self):
        self.trigger('F10')
        self.trigger('<Alt>l')
        self.assert_choice(self.ui.learned_filter)

    def test_settings_hotkey_toggles_and_nested_choice_closes_with_parent(self):
        self.trigger('F10')
        self.trigger('F10')
        self.assertFalse(self.ui.menu_button.get_popover().get_visible())
        self.trigger('F10')
        self.ui.open_choice(self.ui.learned_filter, from_control=True)
        pump()
        self.ui.menu_button.popdown()
        pump()
        self.assertFalse(self.ui.choice_popover.get_visible())
        self.trigger('F10')
        self.assertTrue(self.ui.menu_button.get_popover().get_visible())

    def test_switch_row_label_and_switch_share_one_toggle_target(self):
        self.trigger('F10')
        row = self.ui.settings_rows['Columns']
        switch = self.ui.settings_switches['Columns']
        self.assertTrue(row.has_css_class('switch-row'))
        self.assertTrue(row.get_has_tooltip())
        controls = row.observe_controllers()
        click = next(controls.get_item(i) for i in range(controls.get_n_items())
                     if isinstance(controls.get_item(i), Gtk.GestureClick))
        deadline = time.monotonic() + 3
        while row.get_width() <= 10 and time.monotonic() < deadline: pump(.05)
        self.assertGreater(row.get_width(), 10)
        self.assertGreater(row.get_height(), 0)
        before = switch.get_active()
        click.emit('released', 1, 8.0, row.get_height()/2)
        self.assertEqual(switch.get_active(), not before)
        click.emit('released', 1, row.get_width()-10.0, row.get_height()/2)
        self.assertEqual(switch.get_active(), before)
        # CSS padding is painted and hoverable but lies outside content bounds.
        for x, y in [(-3.0, row.get_height()/2), (row.get_width()+3.0, row.get_height()/2),
                     (row.get_width()/2, -3.0), (row.get_width()/2, row.get_height()+3.0)]:
            self.assertTrue(row.contains(x,y))
            previous = switch.get_active()
            click.emit('released', 1, x, y)
            self.assertEqual(switch.get_active(), not previous)
        previous = switch.get_active()
        click.emit('released', 1, row.get_width()+30.0, row.get_height()/2)
        self.assertEqual(switch.get_active(), previous)
        switch.set_sensitive(False)
        click.emit('released', 1, 8.0, row.get_height()/2)
        self.assertEqual(switch.get_active(), previous)

    def test_marking_scrolled_row_preserves_position_and_control(self):
        self.ui.settings_switches['Flat list'].set_active(True)
        self.ui.learned_filter.set_selected(0)
        self.ui.items = [dict(id=f'scroll-{i}',key='SUPER + A',name=f'Action {i}',
                              group='Action',kind='action',dispatcher='',arg='') for i in range(300)]
        self.ui.render()
        pump(.6)
        self.ui.search.grab_focus()
        pump(.15)
        self.ui.list_box.scroll_to(30, Gtk.ListScrollFlags.NONE, None)
        pump(.2)
        adjustment = self.ui.list_scroll.get_vadjustment()
        deadline = time.monotonic() + 3
        while adjustment.get_upper() <= adjustment.get_page_size() and time.monotonic() < deadline: pump(.05)
        adjustment.set_value(2200)
        pump()
        before = adjustment.get_value()
        self.assertGreater(before, 100)
        with patch.object(self.ui, 'render', wraps=self.ui.render) as render:
            self.ui.favorite(self.ui.items[30])
            self.ui.toggle_learned(self.ui.items[30])
            pump()
            render.assert_not_called()
        self.assertAlmostEqual(adjustment.get_value(),before,delta=2)
        self.ui.learned_filter.set_selected(2)
        pump()
        deadline = time.monotonic() + 3
        while adjustment.get_upper() <= adjustment.get_page_size() and time.monotonic() < deadline: pump(.05)
        adjustment.set_value(2200)
        pump()
        before = adjustment.get_value()
        self.ui.toggle_learned(self.ui.items[31])
        pump()
        self.assertAlmostEqual(adjustment.get_value(),before,delta=2)
        self.ui.favorites.discard('scroll-30')
        self.ui.learned.difference_update({'scroll-30','scroll-31'})

    def test_settings_stays_open(self):
        self.trigger('F10')
        self.assertTrue(self.ui.menu_button.get_popover().get_mapped())
        self.assertEqual(self.ui.menu_pages.get_visible_child_name(), 'settings')

    def test_commands_shortcut_opens_submenu(self):
        self.trigger('<Shift>F10')
        self.assertTrue(self.ui.app_menu_button.get_popover().get_mapped())
        self.assertFalse(self.ui.menu_button.get_popover().get_visible())

    def test_show_filters_is_list_only_switch(self):
        self.assertIsInstance(self.ui.settings_switches['Show filters'], Gtk.Switch)
        self.assertTrue(self.ui.show_filters_row.get_visible())
        self.ui.view_toggle.set_active(True)
        self.assertFalse(self.ui.show_filters_row.get_visible())
        self.assertTrue(self.ui.filter_bar.get_visible() is False)
        self.ui.view_toggle.set_active(False)
        self.assertTrue(self.ui.show_filters_row.get_visible())

    def test_every_settings_switch_explains_itself(self):
        for title, switch in self.ui.settings_switches.items():
            self.assertGreater(len(switch.get_tooltip_text() or getattr(switch, '_action_tooltip', ('', ''))[0]), 30, title)

    def test_context_settings_and_icon_only_bookmarks(self):
        self.assertEqual(self.ui.only_favorites.get_icon_name(), 'starred-symbolic')
        self.assertEqual(self.ui.menu_button.get_popover().get_halign(), Gtk.Align.END)
        for keyboard in (False, True, False):
            self.ui.view_toggle.set_active(keyboard)
            for title in ('Flat list', 'Columns', 'Show filters'):
                self.assertEqual(self.ui.settings_rows[title].get_visible(), not keyboard)
            for title in ('Numpad', 'Fit width'):
                self.assertEqual(self.ui.settings_rows[title].get_visible(), keyboard)
                self.assertIsInstance(self.ui.settings_switches[title], Gtk.Switch)

    def test_keyboard_options_still_support_hotkeys(self):
        self.ui.view_toggle.set_active(True)
        for title, shortcut in (('Numpad', '<Control><Shift>n'), ('Fit width', '<Control><Shift>w')):
            button = self.ui.settings_switches[title]
            before = button.get_active()
            self.trigger(shortcut)
            self.assertEqual(button.get_active(), not before)
            self.trigger(shortcut)
            self.assertEqual(button.get_active(), before)
        self.assertEqual(self.ui.keyboard.legend.get_margin_top() + 2, self.ui.keyboard.legend.get_margin_bottom())
        self.assertNotIn('Keypresses are not saved', self.ui.keyboard.caption.get_text())
        self.assertIn('most recently focused', self.ui.target._action_tooltip[0])

    def test_ctrl_b_toggles_bookmarks_and_persists(self):
        self.trigger('<Control>b')
        self.assertTrue(self.ui.only_favorites.get_active())
        self.assertTrue(app.Shortcuts().saved_filters['favorites_only'])
        self.trigger('<Control>b')
        self.assertFalse(self.ui.only_favorites.get_active())

    def test_clicked_nested_dropdown_keeps_settings_and_anchors_to_control(self):
        self.trigger('F10')
        self.ui.open_choice(self.ui.learned_filter, from_control=True)
        pump()
        self.assert_choice(self.ui.learned_filter)
        self.assertTrue(self.ui.menu_button.get_popover().get_mapped())
        self.assertEqual(self.ui.choice_popover.get_parent(), self.ui.learned_filter)

    def test_management_command_enters_and_returns_to_current_view(self):
        from shortcut_manager import ShortcutManagerPanel
        self.ui.view_toggle.set_active(True)
        with patch.object(ShortcutManagerPanel, 'refresh'):
            self.trigger('<Control>m')
            self.assertEqual(self.ui.view_stack.get_visible_child_name(), 'manage')
            self.assertFalse(self.ui.keyboard.live)
            self.ui.management_back.emit('clicked')
            self.assertEqual(self.ui.view_stack.get_visible_child_name(), 'keyboard')

    def test_alt_l_is_direct_overlay_with_current_item_focused(self):
        self.ui.learned_filter.set_selected(2)
        self.trigger('<Alt>l')
        self.assert_choice(self.ui.learned_filter)
        self.assertFalse(self.ui.menu_button.get_popover().get_visible())

    def test_alt_t_opens_when_list_filters_hidden(self):
        self.ui.settings_switches['Show filters'].set_active(False)
        self.trigger('<Alt>t')
        self.assert_choice(self.ui.type_filter)
        self.assertFalse(self.ui.filter_bar.get_visible())

    def test_alt_t_opens_in_keyboard(self):
        self.ui.view_toggle.set_active(True)
        self.trigger('<Alt>t')
        self.assert_choice(self.ui.type_filter)
        self.assertEqual(self.ui.view_stack.get_visible_child_name(), 'keyboard')
        self.assertTrue(self.ui.keyboard.suppress_guide)

    def test_choice_arrows_enter_commit_and_escape_cancel(self):
        self.ui.learned_filter.set_selected(1)
        self.trigger('<Alt>l')
        self.ui.choice_key_handler(None,Gdk.KEY_Down,0,0)
        self.ui.choice_key_handler(None,Gdk.KEY_Return,0,0)
        self.assertEqual(self.ui.learned_filter.get_selected(),2)
        self.trigger('<Alt>l')
        self.ui.choice_key_handler(None,Gdk.KEY_Up,0,0)
        self.ui.choice_key_handler(None,Gdk.KEY_Escape,0,0)
        self.assertEqual(self.ui.learned_filter.get_selected(),2)
        self.assertTrue(self.ui.window.get_visible())

    def test_escape_settings_does_not_close_app(self):
        self.trigger('F10')
        self.trigger('Escape')
        self.assertFalse(self.ui.menu_button.get_popover().get_visible())
        self.assertTrue(self.ui.window.get_visible())

    def test_source_menu_current_focus(self):
        self.trigger('<Alt><Shift>s')
        self.assert_choice(self.ui.source_picker)

    def test_added_shortcuts_toggle_context_options(self):
        for shortcut, title in (('<Alt>f','Show filters'), ('<Alt>g','Flat list'), ('<Alt>c','Columns')):
            button = self.ui.settings_switches[title]
            before = button.get_active()
            self.trigger(shortcut)
            self.assertEqual(button.get_active(), not before)
            self.trigger(shortcut)
        self.ui.view_toggle.set_active(True)
        button = self.ui.keyboard.option_buttons['key_overlay']
        before = button.get_active()
        self.trigger('<Control><Shift>o')
        self.assertEqual(button.get_active(), not before)
        self.trigger('<Control><Shift>o')

    def test_row_indicators_are_right_aligned_and_revealed_on_hover(self):
        item = self.ui.items[0]
        self.ui.favorites.discard(item['id'])
        self.ui.learned.discard(item['id'])
        row = self.ui.shortcut_row(item)
        star, eye = [widget for widget, _ in row.indicators]
        self.assertIs(row.get_last_child(), eye)
        self.assertIs(eye.get_prev_sibling(), star)
        self.assertEqual(eye.get_icon_name(), 'view-reveal-symbolic')
        self.assertEqual([w.get_opacity() for w, _ in row.indicators], [0, 0])
        row.reveal_indicators(True)
        self.assertEqual([w.get_opacity() for w, _ in row.indicators], [1, 1])
        row.reveal_indicators(False)
        self.ui.favorites.add(item['id'])
        self.ui.learned.add(item['id'])
        marked = self.ui.shortcut_row(item)
        self.assertEqual([w.get_opacity() for w, _ in marked.indicators], [1, 1])
        self.assertEqual(marked.get_last_child().get_icon_name(), 'view-conceal-symbolic')
        self.ui.favorites.discard(item['id'])
        self.ui.learned.discard(item['id'])

    def test_visibility_labels_and_filter_results(self):
        model = self.ui.learned_filter.get_model()
        self.assertEqual([model.get_string(i) for i in range(3)], ['Show all', 'Hidden', 'Not hidden'])
        self.ui.learned = {'one'}
        self.ui.learned_filter.set_selected(1)
        self.assertEqual([i['id'] for i in self.ui.filtered_items()], ['one'])
        self.ui.learned_filter.set_selected(2)
        self.assertEqual([i['id'] for i in self.ui.filtered_items()], ['two'])
        self.ui.learned.clear()

    def test_keyboard_columns_reuses_row_component_and_grid_has_indicators(self):
        keyboard = self.ui.keyboard
        keyboard.items = self.ui.items
        with patch.object(keyboard, 'row_factory', wraps=self.ui.shortcut_row) as rows:
            keyboard.extras_layout = 'columns'
            keyboard.update_extras()
            self.assertTrue(rows.called)
            self.assertTrue(all(call.kwargs['columns'] for call in rows.call_args_list))
            rows.reset_mock()
            keyboard.extras_layout = 'list'
            keyboard.update_extras()
            self.assertTrue(rows.called)
            self.assertTrue(all(not call.kwargs['columns'] for call in rows.call_args_list))
        keyboard.extras_layout = 'grid'
        keyboard.update_extras()
        def descendants(widget):
            yield widget
            child = widget.get_first_child()
            while child:
                yield from descendants(child)
                child = child.get_next_sibling()
        cards = [w for w in descendants(keyboard.extras_host) if hasattr(w, 'indicators')]
        self.assertEqual(len(cards), 2)
        self.assertTrue(all(isinstance(w, Gtk.Image) for card in cards for w, _ in card.indicators))

    def test_accelerators_do_not_conflict(self):
        parsed = [Gtk.accelerator_parse(accel)[1:] for accel, _, _ in app.APP_SHORTCUTS]
        self.assertEqual(len(parsed),len(set(parsed)))

    def test_source_cycle_respects_bookmarks(self):
        self.ui.favorite_sources={'Omarchy','Herdr'}
        self.ui.source_picker.set_selected(0)
        self.trigger('<Alt>s')
        self.assertEqual(self.ui.source_name,'Herdr')
        self.trigger('<Alt>s')
        self.assertEqual(self.ui.source_name,'Omarchy')

    def test_empty_bookmarks_does_not_switch_source(self):
        self.ui.favorite_sources=set()
        source=self.ui.source_name
        self.trigger('<Alt>s')
        self.assertEqual(self.ui.source_name,source)

    def test_flat_mode_hides_group_commands(self):
        self.ui.settings_switches['Flat list'].set_active(True)
        self.assertFalse(self.ui.list_controls.get_visible())
        self.ui.settings_switches['Flat list'].set_active(False)
        self.assertTrue(self.ui.list_controls.get_visible())

    def test_columns_render_large_shortcut_font(self):
        self.ui.settings_switches['Columns'].set_active(True)
        pump()
        def descendants(widget):
            yield widget
            child = widget.get_first_child()
            while child:
                yield from descendants(child)
                child = child.get_next_sibling()
        labels = [w for w in descendants(self.ui.list_box)
                  if isinstance(w, Gtk.Label) and w.has_css_class('column-shortcut')]
        self.assertTrue(labels)
        for label in labels:
            self.assertFalse(label.has_css_class('shortcut-key'))
            font = label.get_pango_context().get_font_description()
            self.assertAlmostEqual(font.get_size() / app.Pango.SCALE, self.ui.system_theme.typography(self.ui.preferences)[1], delta=1 / app.Pango.SCALE)

    def test_column_width_survives_search_and_size_change(self):
        self.ui.settings_switches['Columns'].set_active(True)
        width=self.ui.shortcut_column_width
        self.ui.search.set_text('Alpha')
        self.ui.window.set_default_size(900,600)
        pump()
        self.assertEqual(width,self.ui.shortcut_column_width)

    def test_repeated_menus_do_not_hide_or_change_view(self):
        self.ui.view_toggle.set_active(True)
        for _ in range(3):
            for shortcut in ('F10', '<Shift>F10', '<Alt>l', '<Alt>t', '<Alt><Shift>s'):
                self.trigger(shortcut)
                self.trigger('Escape')
                self.assertTrue(self.ui.window.get_mapped())
                self.assertEqual(self.ui.view_stack.get_visible_child_name(), 'keyboard')

    def test_dropdown_keyboard_activation_focuses_current_item(self):
        dropdown = self.ui.source_picker
        controllers = dropdown.observe_controllers()
        handled = False
        for i in range(controllers.get_n_items()):
            controller = controllers.get_item(i)
            if isinstance(controller, Gtk.EventControllerKey) and controller.get_propagation_phase() == Gtk.PropagationPhase.CAPTURE:
                handled = controller.emit('key-pressed', Gdk.KEY_space, 0, Gdk.ModifierType(0)) or handled
        pump()
        self.assertTrue(handled)
        self.assert_choice(dropdown)

    def test_large_list_creates_only_visible_rows(self):
        self.ui.settings_switches['Flat list'].set_active(True)
        self.ui.items = [dict(id=str(i), key='SUPER + A', name=f'Action {i}',
                              group='Action', kind='action', dispatcher='', arg='') for i in range(5000)]
        with patch.object(self.ui, 'shortcut_row', wraps=self.ui.shortcut_row) as rows:
            self.ui.render()
            pump(.15)
            self.assertEqual(self.ui.list_model.get_n_items(), 5000)
            self.assertLess(rows.call_count, 500)

    def test_count_badges_survive_gc(self):
        gc.collect()
        self.ui.update_source_count('Omarchy',321)
        badges=[box for box in self.ui.source_badges if box.source_name=='Omarchy']
        self.assertTrue(badges)
        self.assertTrue(all(box.badge.get_text()=='321' for box in badges))

    def test_shortcut_reference_hides_empty_groups_and_editor_navigation(self):
        self.ui.features = dict(app.DEFAULT_FEATURES)
        self.ui.apply_features()
        self.ui.show_shortcuts()
        def labels(widget):
            values = [widget.get_text()] if isinstance(widget, Gtk.Label) else []
            child = widget.get_first_child()
            while child:
                values.extend(labels(child))
                child = child.get_next_sibling()
            return values
        text = labels(self.ui.shortcuts_window)
        self.assertNotIn('List', text)
        self.assertNotIn('Keyboard', text)
        self.assertNotIn('Back from shortcut management', text)
        self.assertIn('Choose shortcut source', text)
        self.assertIn('Open GTK Inspector', text)
        self.assertLess(text.index('Focus search'), text.index('Choose shortcut source'))
        self.assertFalse(self.ui.action_enabled('back'))
        self.ui.set_feature('manage', True)
        self.assertTrue(self.ui.action_enabled('back'))

    def test_source_menu_skips_zero_and_preserves_selection_and_navigation(self):
        self.ui.source_counts = {'Omarchy': 0, 'Tmux': 42, 'Herdr': 0, 'Shefrd': None}
        self.ui.source_picker.set_selected(1)
        self.ui.open_choice(self.ui.source_picker)
        pump()
        self.assertEqual(self.ui.choice_list.get_row_at_index(0).choice_index, 1)
        self.assertIsNone(self.ui.choice_list.get_row_at_index(1))
        self.assertEqual(self.ui.choice_list.get_selected_row().choice_index, 1)
        self.ui.choice_key_handler(None, Gdk.KEY_Down)
        self.assertIsNone(self.ui.choice_list.get_selected_row())
        self.assertEqual(self.ui.window.get_focus().get_label(),'Choose shortcut sets…')
        self.ui.choice_key_handler(None, Gdk.KEY_Up)
        self.assertEqual(self.ui.choice_list.get_selected_row().choice_index, 1)
        self.ui.choice_key_handler(None, Gdk.KEY_Return)
        self.assertEqual(self.ui.source_picker.get_selected(), 1)

    def test_feature_gallery_grid_list_switch(self):
        self.ui.show_features()
        gallery = self.ui.features_window
        gallery.description_switch.set_active(False)
        self.assertTrue(all(not label.get_visible() for label in gallery.feature_descriptions))
        gallery.preview_switch.set_active(False)
        self.assertTrue(all(not preview.get_visible() for preview in gallery.feature_previews))
        self.assertIs(gallery.preview_switch.get_parent().get_parent(), gallery.layout_switch.get_parent().get_parent())
        gallery.layout_switch.set_active(False)
        self.assertEqual(gallery.feature_cards.get_max_children_per_line(), 1)
        gallery.layout_switch.set_active(True)
        self.assertEqual(gallery.feature_cards.get_max_children_per_line(), 2)
        self.assertTrue(all(not preview.get_visible() for preview in gallery.feature_previews))
        gallery.preview_switch.set_active(True)
        self.assertTrue(all(preview.get_visible() for preview in gallery.feature_previews))
        self.assertTrue(all(not label.get_visible() for label in gallery.feature_descriptions))
        gallery.description_switch.set_active(True)
        self.assertTrue(all(label.get_visible() for label in gallery.feature_descriptions))

    def test_search_reuses_rows_and_retains_correct_actions(self):
        self.ui.flat_list = True
        self.ui.render()
        pump()
        with patch.object(self.ui, 'shortcut_row', wraps=self.ui.shortcut_row) as build:
            for _ in range(3):
                self.ui.search.set_text('Alpha')
                pump(.04)
                self.assertEqual(self.ui.list_model.get_item(0).data['item']['id'], 'one')
                self.ui.search.set_text('')
                pump(.04)
                self.assertEqual(self.ui.list_model.get_n_items(), 2)
            self.assertEqual(build.call_count, 0)
        self.assertLessEqual(len(self.ui.row_cache), 256)
        with patch.object(self.ui, 'run_action') as run:
            self.ui.items[1]['dispatcher'] = 'exec'
            self.ui.render()
            self.ui.activate_list_item(self.ui.list_box, 1)
            run.assert_called_once_with(self.ui.items[1])

    def test_animations_are_an_app_setting_not_a_feature(self):
        import preferences
        self.assertNotIn('animations', app.FEATURES)
        self.assertNotIn('Animate window', self.ui.settings_rows)
        preferences.show(self.ui)
        self.assertIsNotNone(self.ui.preferences_window)
        self.assertEqual(self.ui.preferences['window_animations'], 'off')
        self.ui.preferences_window.controls['window_animations'].set_selected(2)
        self.assertEqual(app.Shortcuts().preferences['window_animations'], 'off')

    def test_missing_and_disabled_sources_are_hidden_and_marks_survive(self):
        self.ui.favorite_sources = {'Omarchy', 'Herdr'}
        self.ui.set_source_enabled('Herdr', False)
        self.assertIn('Herdr', self.ui.favorite_sources)
        with patch.object(app.shortcut_sets, 'installed', side_effect=lambda name: name == 'Tmux'):
            self.ui.open_choice(self.ui.source_picker)
            self.assertEqual(self.ui.choice_list.get_row_at_index(0).choice_index, app.SOURCES.index('Tmux'))
            self.assertIsNone(self.ui.choice_list.get_row_at_index(1))
        restored = app.Shortcuts()
        self.assertIn('Herdr', restored.disabled_sources)
        self.assertIn('Herdr', restored.favorite_sources)

    def test_empty_source_menu_can_open_library_with_keyboard(self):
        self.ui.source_counts = {name:0 for name in app.SOURCES}
        self.ui.open_choice(self.ui.source_picker)
        pump()
        self.assertIsNone(self.ui.choice_list.get_row_at_index(0))
        self.ui.choice_key_handler(None, Gdk.KEY_Return)
        self.assertIsNotNone(self.ui.source_library_window)
        self.assertTrue(all(not switch.get_sensitive() for switch in self.ui.source_library_window.source_switches.values()))

    def test_disabling_current_source_selects_available_fallback(self):
        self.ui.source_counts = {'Omarchy':2, 'Tmux':42}
        self.ui.set_source_enabled('Omarchy',False)
        self.assertEqual(self.ui.source_name, 'Tmux')
        self.ui.set_source_enabled('Tmux',False)
        self.assertFalse(self.ui.items)
        self.assertIn('No available',self.ui.source_note)

    def test_source_library_escape_closes_with_search_focused(self):
        app.source_library.show(self.ui)
        window = self.ui.source_library_window
        child = window.get_child().get_first_child()
        while not isinstance(child, Gtk.SearchEntry):
            child = child.get_next_sibling()
        pump()
        self.assertTrue(window.get_focus().is_ancestor(child))
        child.set_text('chrome')
        pump()
        controllers = window.observe_controllers()
        keys = next(controllers.get_item(i) for i in range(controllers.get_n_items())
                    if isinstance(controllers.get_item(i), Gtk.EventControllerKey)
                    and controllers.get_item(i).get_propagation_phase() == Gtk.PropagationPhase.CAPTURE)
        self.assertTrue(keys.emit('key-pressed', Gdk.KEY_Escape, 0, Gdk.ModifierType(0)))
        pump()
        self.assertIsNone(self.ui.source_library_window)
        self.assertFalse(window.get_visible())
        self.assertTrue(self.ui.window.get_visible())

    def test_features_search_filters_names_and_descriptions_without_changing_settings(self):
        self.ui.show_features()
        gallery = self.ui.features_window
        before = dict(self.ui.features)
        gallery.preview_switch.set_active(False)
        gallery.feature_search.set_text('BOOKMARKS')
        pump()
        self.assertIs(gallery.feature_search.get_parent(), gallery.layout_switch.get_parent().get_parent())
        self.assertIs(gallery.feature_search.get_parent().get_first_child(), gallery.feature_search)
        self.assertTrue(gallery.feature_labels[0].get_attributes().to_string())
        def shown():
            child = gallery.feature_cards.get_first_child()
            result = []
            while child:
                if child.get_child_visible(): result.append(child.search_text)
                child = child.get_next_sibling()
            return result
        self.assertEqual(len(shown()), 1)
        gallery.feature_search.set_text('modifier layers')
        pump()
        self.assertEqual(len(shown()), 1)
        gallery.feature_search.set_text('zzzz-no-feature')
        self.assertTrue(gallery.search_empty.get_visible())
        gallery.feature_search.set_text('')
        pump()
        self.assertEqual(len(shown()), len(app.FEATURES))
        self.assertFalse(gallery.search_empty.get_visible())
        self.assertFalse(gallery.feature_labels[0].get_attributes().to_string())
        self.assertEqual(self.ui.features, before)
        self.assertTrue(all(not preview.get_visible() for preview in gallery.feature_previews))

    def test_feature_card_is_one_click_and_keyboard_toggle_target(self):
        self.ui.show_features()
        gallery = self.ui.features_window
        pump(.2)
        switch = gallery.feature_switches['bookmarks']
        card = switch.get_parent().get_parent()
        self.assertTrue(card.get_focusable())
        controllers = card.observe_controllers()
        click = next(controllers.get_item(i) for i in range(controllers.get_n_items())
                     if isinstance(controllers.get_item(i), Gtk.GestureClick))
        keys = next(controllers.get_item(i) for i in range(controllers.get_n_items())
                    if isinstance(controllers.get_item(i), Gtk.EventControllerKey))
        before = switch.get_active()
        click.emit('released', 1, float(card.get_width()/2), float(card.get_height()-5))
        self.assertEqual(switch.get_active(), not before)
        self.assertEqual(self.ui.feature_enabled('bookmarks'), not before)
        keys.emit('key-pressed', Gdk.KEY_space, 0, Gdk.ModifierType(0))
        self.assertEqual(switch.get_active(), before)

    def test_repeated_dropdown_activation_never_falls_through_to_native_popup(self):
        for button, dropdown, accelerator in ((self.ui.menu_button, self.ui.learned_filter, 'F10'),
                                             (self.ui.app_menu_button, self.ui.target, '<Shift>F10')):
            self.trigger(accelerator)
            controllers = dropdown.observe_controllers()
            keys = next(controllers.get_item(i) for i in range(controllers.get_n_items())
                        if isinstance(controllers.get_item(i), Gtk.EventControllerKey)
                        and controllers.get_item(i).get_propagation_phase() == Gtk.PropagationPhase.CAPTURE)
            for _ in range(3):
                self.assertTrue(keys.emit('key-pressed', Gdk.KEY_space, 0, Gdk.ModifierType(0)))
                pump()
                self.assertTrue(self.ui.choice_popover.get_visible())
                self.assertTrue(keys.emit('key-pressed', Gdk.KEY_space, 0, Gdk.ModifierType(0)))
                pump()
                self.assertFalse(self.ui.choice_popover.get_visible())
            click = next(controllers.get_item(i) for i in range(controllers.get_n_items())
                         if isinstance(controllers.get_item(i), Gtk.GestureClick)
                         and controllers.get_item(i).get_propagation_phase() == Gtk.PropagationPhase.CAPTURE)
            for _ in range(3):
                click.emit('pressed', 1, float(dropdown.get_width()/2), float(dropdown.get_height()/2))
                pump()
                self.assertTrue(self.ui.choice_popover.get_visible())
                click.emit('pressed', 1, float(dropdown.get_width()/2), float(dropdown.get_height()/2))
                pump()
                self.assertFalse(self.ui.choice_popover.get_visible())
            self.trigger('Escape')
            self.assertFalse(button.get_popover().get_visible())
            self.assertTrue(self.ui.window.get_visible())
            self.trigger(accelerator)
            self.trigger(accelerator)
            self.assertFalse(button.get_popover().get_visible())

    def test_live_filter_does_not_capture_app_settings_escape(self):
        self.ui.live_switch.set_active(True)
        self.ui.app_menu_button.popup()
        pump()
        self.trigger('Escape')
        self.assertFalse(self.ui.app_menu_button.get_popover().get_visible())
        self.assertTrue(self.ui.live_switch.get_active())

    def test_visibility_selection_then_toolbar_click_closes_view_options(self):
        button = self.ui.menu_button
        controllers = button.observe_controllers()
        click = next(controllers.get_item(i) for i in range(controllers.get_n_items())
                     if isinstance(controllers.get_item(i), Gtk.GestureClick)
                     and controllers.get_item(i).get_propagation_phase() == Gtk.PropagationPhase.CAPTURE)
        for choice in (1, 2, 0):
            self.trigger('F10')
            self.ui.open_choice(self.ui.learned_filter, from_control=True)
            pump()
            popup = self.ui.choice_popover
            self.ui.choice_list.emit('row-activated', self.ui.choice_list.get_row_at_index(choice))
            pump()
            self.assertEqual(self.ui.learned_filter.get_selected(), choice)
            self.assertFalse(popup.get_visible())
            self.assertIsNone(popup.get_parent())
            self.assertTrue(button.get_popover().get_visible())
            click.emit('pressed', 1, float(button.get_width()/2), float(button.get_height()/2))
            pump()
            self.assertFalse(button.get_popover().get_visible())
            self.assertTrue(self.ui.window.get_visible())

    def test_minimal_features_use_compact_window_width(self):
        self.ui.features = dict(app.DEFAULT_FEATURES)
        self.ui.apply_features()
        self.assertEqual(self.ui.window.get_default_size().width, 800)
        pump(.2)
        self.assertLessEqual(self.ui.window.get_width(), 820)
        self.ui.set_feature('keyboard',True)
        self.assertEqual(self.ui.window.get_default_size().width, 800)
        self.ui.set_feature('keyboard',False)
        self.assertEqual(self.ui.window.get_default_size().width, 800)

    def test_feature_switches_are_compact_without_preview_or_description(self):
        self.ui.show_features()
        gallery = self.ui.features_window
        gallery.preview_switch.set_active(False)
        gallery.description_switch.set_active(False)
        pump(.2)
        child = gallery.feature_cards.get_first_child()
        while child:
            card = child.get_child()
            self.assertFalse(card.has_css_class('feature-card'))
            self.assertLess(card.get_height(), 65)
            child = child.get_next_sibling()
        self.assertLess(gallery.feature_cards.get_height(), 350)
        gallery.layout_switch.set_active(False)
        self.assertEqual(gallery.feature_cards.get_max_children_per_line(), 1)
        self.assertEqual(gallery.feature_cards.get_valign(), Gtk.Align.START)
        gallery.description_switch.set_active(True)
        self.assertTrue(gallery.feature_cards.get_first_child().get_child().has_css_class('feature-card'))
        self.assertEqual(gallery.feature_cards.get_valign(), Gtk.Align.START)


if __name__ == '__main__': unittest.main()
