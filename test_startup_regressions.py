import os, tempfile, threading, time, unittest
from unittest.mock import patch
import app
import test_ui_workflows as workflows

@unittest.skipUnless(os.environ.get('GDK_BACKEND')=='broadway','Private GTK display required')
class StartupTests(unittest.TestCase):
    def test_uncached_source_shows_loading_not_empty_results(self):
        refresh=app.Shortcuts.refresh
        fixture=workflows.UiWorkflows();fixture.setUp()
        release=threading.Event()
        try:
            ui=fixture.ui;ui.items=[];ui.source_name='Omarchy'
            def slow():
                release.wait(3)
                return []
            with patch('app.source_cache.read',return_value=None),patch('app.source_cache.write'),patch('app.records',side_effect=slow):
                refresh(ui);workflows.pump(.1)
                self.assertEqual(ui.list_model.get_item(0).data,{'loading':True})
                from dialogs import walk
                self.assertTrue(any(isinstance(w,app.Gtk.Label) and w.get_text()=='Loading shortcuts…' for w in walk(ui.list_box)))
                release.set()
                deadline=time.monotonic()+2
                while ui.refresh_busy and time.monotonic()<deadline:workflows.pump(.01)
                self.assertNotIn('loading',ui.list_model.get_item(0).data)
        finally:
            release.set();fixture.tearDown()

    def test_cache_is_shown_before_slow_discovery_finishes(self):
        refresh=app.Shortcuts.refresh
        fixture=workflows.UiWorkflows();fixture.setUp()
        release=threading.Event()
        row=dict(id='cached',name='Full screen',key='SUPER + F',group='Windows',dispatcher='',arg='')
        def slow():
            release.wait(3)
            return [dict(row,name='Updated title')]
        try:
            ui=fixture.ui;ui.items=[];ui.source_name='Omarchy'
            with tempfile.TemporaryDirectory() as root,patch.dict('os.environ',{'XDG_CACHE_HOME':root}),patch('app.records',side_effect=slow):
                app.source_cache.write('Omarchy',[row],'Live Hyprland bindings')
                refresh(ui)
                workflows.pump(.05)
                self.assertTrue(ui.refresh_busy)
                self.assertEqual(ui.items[0]['name'],'Full screen')
                release.set()
                deadline=time.monotonic()+2
                while ui.refresh_busy and time.monotonic()<deadline:workflows.pump(.01)
                self.assertFalse(ui.refresh_busy)
                self.assertEqual(ui.items[0]['name'],'Updated title')
        finally:
            release.set();fixture.tearDown()

    def test_capture_requests_and_releases_system_keys(self):
        fixture=workflows.UiWorkflows();fixture.setUp()
        try:
            import preferences
            from gi.repository import Gdk
            preferences.show(fixture.ui);workflows.pump()
            picker=fixture.ui.preferences_window.controls['global_hotkey']
            with patch.object(Gdk.Toplevel,'inhibit_system_shortcuts') as inhibit,patch.object(Gdk.Toplevel,'restore_system_shortcuts') as restore:
                picker.capture.set_active(True)
                inhibit.assert_called_once()
                picker.capture_controller.emit('key-pressed',Gdk.KEY_k,0,Gdk.ModifierType.CONTROL_MASK)
                restore.assert_called_once()
                self.assertFalse(picker.capture.get_active())
                self.assertIsNone(picker.capture_root_handler)
        finally:fixture.tearDown()
