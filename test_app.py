"""Run with python -m unittest -v (requires a GTK display)."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import app
from gi.repository import Gtk

class AppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        for name, file in [('STATE', 'favorites.json'), ('UI_STATE', 'ui-state.json'), ('LEARNED_STATE', 'learned.json')]:
            mock = patch.object(app, name, Path(self.temp.name) / file)
            mock.start()
            self.addCleanup(mock.stop)
        self.ui = app.Shortcuts()
        self.ui.features = {key: True for key in app.FEATURES}
        self.ui.flat_list = False
        self.ui.columns = False
        self.ui.search = Gtk.SearchEntry()
        self.ui.only_favorites = Gtk.ToggleButton()
        self.ui.learned_filter = Gtk.DropDown.new_from_strings(['All shortcuts', 'Learned', 'To learn'])
        self.ui.create_shortcut_list()
        self.ui.items = [dict(id='a', key='SUPER + 1', name='Workspace', group='Workspaces', dispatcher='lua', arg='hl.dsp.window.close()'),
                         dict(id='b', key='SUPER + T', name='Terminal', group='Apps & tools', dispatcher='exec', arg='')]

    def test_shortcut_outlier_is_ellipsized_without_losing_full_binding(self):
        long_key=' / '.join('PREFIX + CTRL + '+direction for direction in ('LEFT','DOWN','UP','RIGHT'))
        self.ui.items += [dict(self.ui.items[0],id='long',key=long_key)]
        self.ui.update_column_width()
        self.assertLessEqual(self.ui.shortcut_column_width,320)
        row=self.ui.shortcut_row(self.ui.items[-1],columns=True)
        key=row.get_first_child().get_child().get_first_child()
        self.assertEqual(key.get_ellipsize(),app.Pango.EllipsizeMode.END)
        self.assertEqual(key.get_text(),long_key)
        self.assertEqual(key.get_tooltip_text(),long_key)
        self.assertLessEqual(key.measure(Gtk.Orientation.HORIZONTAL,-1)[1],320)

    def test_new_input_feature_is_opt_in_on_upgrade(self):
        app.UI_STATE.write_text(json.dumps({'features': {'agent': True}, 'preferences': {}}))
        self.assertFalse(app.Shortcuts().features['inputs'])
        app.UI_STATE.write_text(json.dumps({'features': {'inputs': True}}))
        self.assertTrue(app.Shortcuts().features['inputs'])

    def test_animation_preference_migrates_and_removes_marker(self):
        marker = app.STATE.parent / 'animate-window'
        marker.touch()
        self.assertEqual(self.ui.preferences['window_animations'], 'off')
        self.ui.preferences['window_animations'] = 'off'
        with patch.object(app.subprocess, 'run') as command:
            command.return_value.stdout = ''
            self.ui.sync_window_animations()
        self.assertFalse(marker.exists())
        saved = json.loads(app.UI_STATE.read_text())
        self.assertNotIn('animate_windows', saved)
        self.assertEqual(saved['preferences']['window_animations'], 'off')
        self.assertEqual(app.Shortcuts().preferences['window_animations'], 'off')
        app.UI_STATE.write_text(json.dumps({'animate_windows': False}))
        self.assertEqual(app.Shortcuts().preferences['window_animations'], 'off')
        app.UI_STATE.write_text(json.dumps({'animate_windows': True}))
        self.assertEqual(app.Shortcuts().preferences['window_animations'], 'off')

    def test_columns_keep_full_source_width_when_filtering(self):
        self.ui.columns = True
        self.ui.items[0]['key'] = 'SUPER CTRL SHIFT ALT + RETURN'
        self.ui.render()
        full_width = self.ui.shortcut_column_width
        self.ui.search.set_text('Terminal')
        self.ui.render()
        self.assertEqual(self.ui.shortcut_column_width, full_width)

    def test_flat_and_columns_are_independent_and_saved(self):
        self.ui.flat_list = True
        self.ui.columns = False
        self.ui.render()
        self.assertEqual(self.ui.list_model.get_n_items(), 2)
        self.assertTrue(all('item' in self.ui.list_model.get_item(i).data for i in range(2)))
        self.ui.save_ui_state()
        restored = app.Shortcuts()
        self.assertTrue(restored.flat_list)
        self.assertFalse(restored.columns)

    def test_type_filter_combines_with_other_filters_and_persists(self):
        from shortcut_types import FILTERS
        self.ui.type_filter = Gtk.DropDown.new_from_strings([label for _, label in FILTERS])
        self.ui.items[0]['kind'] = 'action'
        self.ui.items[1]['kind'] = 'desktopApp'
        index = [key for key, _ in FILTERS].index('apps')
        self.ui.type_filter.set_selected(index)
        self.ui.filters_changed()
        self.assertEqual([r['id'] for r in self.ui.filtered_items()], ['b'])
        self.assertEqual(app.Shortcuts().saved_filters['type'], 'apps')
        self.ui.only_favorites.set_active(True)
        self.assertEqual(self.ui.filtered_items(), [])
        self.ui.favorites.add('b')
        self.assertEqual([r['id'] for r in self.ui.filtered_items()], ['b'])

    def test_group_state_survives_render_filter_and_restart(self):
        self.ui.set_all_expanded(False)
        self.assertFalse(self.ui.list_model.get_item(0).data['expanded'])
        self.ui.search.set_text('Workspace')
        self.ui.search_changed()
        self.assertTrue(self.ui.list_model.get_item(0).data['expanded'])
        self.ui.set_all_expanded(False)
        self.assertFalse(app.Shortcuts().expanded_groups['Workspaces'])
        self.ui.search.set_text('')
        self.ui.render()
        self.assertFalse(self.ui.list_model.get_item(0).data['expanded'])
        self.ui.search.set_text('Workspace')
        self.ui.search_changed()
        self.assertTrue(self.ui.list_model.get_item(0).data['expanded'])
        self.ui.set_all_expanded(False)
        self.assertFalse(self.ui.list_model.get_item(0).data['expanded'])
        self.ui.set_all_expanded(True)
        self.assertFalse(app.Shortcuts().expanded_groups['Workspaces'])
        self.ui.search.set_text('')
        self.ui.render()
        # The first group is Apps & tools; change Workspaces explicitly below.
        self.ui.group_toggled(Gtk.Expander(expanded=True), None, 'Workspaces')
        restored = app.Shortcuts()
        self.assertTrue(restored.expanded_groups['Workspaces'])
        self.assertFalse(restored.expanded_groups['Apps & tools'])
        self.ui.set_all_expanded(True)
        self.assertTrue(all(app.Shortcuts().expanded_groups.values()))

    def test_filters_round_trip_and_group_changes_preserve_them(self):
        self.ui.preferences['remember_search'] = True
        self.ui.set_all_expanded(False)
        self.ui.search.set_text('@1')
        self.ui.only_favorites.set_active(True)
        self.ui.learned_filter.set_selected(2)
        for layer in (None, frozenset(), frozenset({'SUPER', 'SHIFT'})):
            self.ui.keyboard_filter = ('1', layer)
            self.ui.filters_changed()
            self.ui.set_all_expanded(False)
            restored = app.Shortcuts()
            restored.search = Gtk.SearchEntry()
            restored.only_favorites = Gtk.ToggleButton()
            restored.learned_filter = Gtk.DropDown.new_from_strings(['All', 'Learned', 'To learn'])
            restored.restore_filters()
            self.assertEqual(restored.search.get_text(), '@1')
            self.assertTrue(restored.only_favorites.get_active())
            self.assertEqual(restored.learned_filter.get_selected(), 2)
            self.assertEqual(restored.keyboard_filter, ('1', layer))
            self.assertFalse(restored.expanded_groups['Workspaces'])
        self.ui.search.set_text('terminal')
        self.ui.search_changed()
        self.assertIsNone(app.Shortcuts().saved_filters['keyboard'])
        self.assertEqual(app.Shortcuts().saved_filters['search'], 'terminal')
        self.ui.search.set_text('')
        self.ui.only_favorites.set_active(False)
        self.ui.learned_filter.set_selected(0)
        self.ui.filters_changed()
        self.assertEqual(app.Shortcuts().saved_filters['learned'], 'all')
        self.assertFalse(app.Shortcuts().saved_filters['favorites_only'])

    def test_old_and_invalid_filter_state_defaults_safely(self):
        for data in ([], {'expanded_groups': {'Apps': False}},
                     {'expanded_groups': [], 'filters': []},
                     {'filters': {'search': 42, 'favorites_only': 'yes', 'learned': [],
                                  'keyboard': {'symbol': 'W', 'layer': [42]}}}):
            app.UI_STATE.write_text(json.dumps(data))
            restored = app.Shortcuts()
            restored.search = Gtk.SearchEntry()
            restored.only_favorites = Gtk.ToggleButton()
            restored.learned_filter = Gtk.DropDown.new_from_strings(['All', 'Learned', 'To learn'])
            restored.restore_filters()
            self.assertEqual(restored.search.get_text(), '')
            self.assertFalse(restored.only_favorites.get_active())
            self.assertEqual(restored.learned_filter.get_selected(), 0)
            self.assertIsNone(restored.keyboard_filter)

    def test_favorites_survive_restart(self):
        self.ui.favorite(self.ui.items[0])
        self.assertIn('a', app.Shortcuts().favorites)
        self.ui.favorite(self.ui.items[0])
        self.assertNotIn('a', app.Shortcuts().favorites)

    def test_learned_marks_persist_independently_of_favorites(self):
        self.ui.favorite(self.ui.items[0])
        self.ui.toggle_learned(self.ui.items[0])
        restored = app.Shortcuts()
        self.assertIn('a', restored.learned)
        self.assertIn('a', restored.favorites)
        self.ui.toggle_learned(self.ui.items[0])
        self.assertNotIn('a', app.Shortcuts().learned)
        self.assertIn('a', app.Shortcuts().favorites)

    def test_learned_filter_combines_with_search_and_favorites(self):
        self.ui.toggle_learned(self.ui.items[0])
        self.ui.learned_filter.set_selected(1)
        self.assertEqual([r['id'] for r in self.ui.filtered_items()], ['a'])
        self.ui.learned_filter.set_selected(2)
        self.assertEqual([r['id'] for r in self.ui.filtered_items()], ['b'])
        self.ui.only_favorites.set_active(True)
        self.assertEqual(self.ui.filtered_items(), [])
        self.ui.favorite(self.ui.items[1])
        self.assertEqual([r['id'] for r in self.ui.filtered_items()], ['b'])
        self.ui.search.set_text('@1')
        self.assertEqual(self.ui.filtered_items(), [])
        self.ui.only_favorites.set_active(False)
        self.ui.learned_filter.set_selected(0)
        self.assertEqual([r['id'] for r in self.ui.filtered_items()], ['a'])

    def test_current_default_and_explicit_target_preserved(self):
        self.ui.target_model = Gtk.StringList.new(['Current'])
        self.ui.target = Gtk.DropDown(model=self.ui.target_model)
        windows = [dict(address='0x1', title='One', workspace={'name':'1'}, mapped=True, **{'class':'foot'}, focusHistoryID=1)]
        with patch.object(app, 'clients', return_value=windows):
            self.ui.refresh_targets()
            from test_ui_workflows import pump
            pump()
            self.assertEqual(self.ui.target.get_selected(), 0)
            self.assertEqual(self.ui.target_model.get_string(0), 'Current')
            self.ui.target.set_selected(1)
            windows[0] = dict(windows[0], title='Renamed')
            self.ui.refresh_targets()
            from test_ui_workflows import pump
            pump()
            self.assertEqual(self.ui.target.get_selected(), 1)
        with patch.object(app, 'clients', return_value=[]):
            self.ui.refresh_targets()
            from test_ui_workflows import pump
            pump()
            self.assertEqual(self.ui.target.get_selected(), 0)

    def test_current_resolves_at_click_time(self):
        self.ui.target_model = Gtk.StringList.new(['Current'])
        self.ui.target = Gtk.DropDown(model=self.ui.target_model)
        self.ui.status = Gtk.Label()
        window = dict(address='0x123', mapped=True, workspace={'id':4}, **{'class': 'foot'}, focusHistoryID=1)
        class ImmediateThread:
            def __init__(self, target, **kwargs): self.target = target
            def start(self): self.target()
        with patch.object(app, 'clients', return_value=[window]), \
             patch.object(app.threading, 'Thread', ImmediateThread), \
             patch.object(app.subprocess, 'run') as run, \
             patch.object(app.subprocess, 'check_output', return_value='{"id":4}'), \
             patch.object(app, 'adapter') as adapter:
            self.ui.run_action(self.ui.items[0])
            self.assertIn('address:0x123', run.call_args.args[0][-1])
            adapter.assert_called_once()

    def test_current_launch_does_not_focus_another_workspace(self):
        self.ui.target_model = Gtk.StringList.new(['Current'])
        self.ui.target = Gtk.DropDown(model=self.ui.target_model)
        self.ui.status = Gtk.Label()
        class ImmediateThread:
            def __init__(self, target, **kwargs): self.target = target
            def start(self): self.target()
        item = dict(name='Calculator', dispatcher='exec', arg='omacalc')
        with patch.object(app.threading, 'Thread', ImmediateThread), \
             patch.object(app, 'clients') as clients, \
             patch.object(app.subprocess, 'run') as run, \
             patch.object(app, 'adapter') as adapter:
            self.ui.run_action(item)
            clients.assert_not_called()
            run.assert_not_called()
            adapter.assert_called_once_with('dispatch_binding "$1" "$2"', 'exec', 'omacalc')

    def test_folder_button_opens_project_uri(self):
        with patch.object(app.Gio.AppInfo, 'launch_default_for_uri') as launch:
            self.ui.open_folder(app.PROJECT)
            launch.assert_called_once_with(app.PROJECT.as_uri(), None)

    def test_info_reports_real_paths_and_counts(self):
        text = '\n'.join(body for _, body in app.project_info(227))
        self.assertIn(str(app.PROJECT), text)
        self.assertIn(str(app.STATE), text)
        self.assertIn(str(app.UI_STATE), text)
        self.assertIn('app.py:', text)
        self.assertIn('Current is the default target', text)

if __name__ == '__main__':
    unittest.main()
