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
        self.ui.search = Gtk.SearchEntry()
        self.ui.only_favorites = Gtk.ToggleButton()
        self.ui.learned_filter = Gtk.DropDown.new_from_strings(['All shortcuts', 'Learned', 'To learn'])
        self.ui.list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.ui.items = [dict(id='a', key='SUPER + 1', name='Workspace', group='Workspaces', dispatcher='lua', arg='hl.dsp.window.close()'),
                         dict(id='b', key='SUPER + T', name='Terminal', group='Apps & tools', dispatcher='exec', arg='')]

    def test_group_state_survives_render_filter_and_restart(self):
        self.ui.set_all_expanded(False)
        self.assertFalse(self.ui.list_box.get_first_child().get_expanded())
        self.ui.search.set_text('Workspace')
        self.ui.render()
        self.assertFalse(self.ui.list_box.get_first_child().get_expanded())
        self.ui.list_box.get_first_child().set_expanded(True)
        restored = app.Shortcuts()
        self.assertTrue(restored.expanded_groups['Workspaces'])
        self.assertFalse(restored.expanded_groups['Apps & tools'])
        self.ui.set_all_expanded(True)
        self.assertTrue(all(app.Shortcuts().expanded_groups.values()))

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
            self.assertEqual(self.ui.target.get_selected(), 0)
            self.assertEqual(self.ui.target_model.get_string(0), 'Current')
            self.ui.target.set_selected(1)
            windows[0] = dict(windows[0], title='Renamed')
            self.ui.refresh_targets()
            self.assertEqual(self.ui.target.get_selected(), 1)
        with patch.object(app, 'clients', return_value=[]):
            self.ui.refresh_targets()
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
