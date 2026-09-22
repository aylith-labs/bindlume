"""Fresh-install native styling and reproducible interaction regression checks."""
import ctypes
import json
import os
from pathlib import Path
import random
import shlex
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import native_style

class MenuTokenTests(unittest.TestCase):
    def test_legacy_style_maps_to_square(self):
        import theme
        self.assertNotIn('omarchy', theme.LOOKS)
        self.assertEqual(theme.resolve_look('omarchy'), 'square')

    def test_folded_scroll_height_matches_shell(self):
        tokens = dict(row=50,row_gap=3)
        self.assertEqual(native_style.folded_height(0,500,tokens),50)
        self.assertEqual(native_style.folded_height(3,500,tokens),156)
        self.assertEqual(native_style.folded_height(20,500,tokens),452)

    def test_shell_font_and_spacing_overrides(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)/'shell.toml'
            source.write_text('[font]\nbase-size=18\nheading=25\n[spacing]\nscale=2\nrow-padding-x=9\n')
            with patch.object(native_style, 'SHELL_THEME', source), patch.dict(os.environ, {'OMARCHY_MENU_FONT':'Test Font'}):
                tokens = native_style.menu_tokens()
            self.assertEqual(tokens['family'], 'Test Font')
            self.assertEqual(tokens['size'], 25)
            self.assertEqual(tokens['padding'],54)
            self.assertEqual(tokens['row'],150)

@unittest.skipUnless(os.environ.get('GDK_BACKEND') == 'broadway', 'Private GTK display required')
class NativeWorkflows(unittest.TestCase):
    def setUp(self):
        from test_ui_workflows import UiWorkflows, pump
        import app
        self.fixture = UiWorkflows(); self.fixture.setUp()
        self.ui = self.fixture.ui
        self.pump = pump
        self.ui.features = app.DEFAULT_FEATURES.copy()
        self.ui.apply_features()
        self.ui.render(); pump(.2)

    def tearDown(self): self.fixture.tearDown()

    def test_fresh_defaults_and_native_empty_search(self):
        from gi.repository import Gtk
        import preferences
        ui = self.ui
        self.assertTrue(ui.feature_enabled('agent'))
        self.assertFalse(ui.preferences['app_icons'])
        self.assertFalse(ui.preferences['action_icons'])
        self.assertTrue(ui.preferences['system_typography'])
        self.assertEqual(ui.preferences['window_animations'], 'off')
        self.assertEqual(ui.preferences['app_animations'], 'system')
        self.assertIsInstance(ui.search, Gtk.Entry)
        self.assertIsNone(ui.search.get_icon_name(Gtk.EntryIconPosition.PRIMARY))
        ui.search.set_text('missing example'); self.pump(.15)
        self.assertEqual(ui.list_model.get_item(0).data['empty_query'], 'missing example')
        ui.search.set_text('another missing example'); self.pump(.15)
        self.assertEqual(ui.list_model.get_item(0).data['empty_query'], 'another missing example')
        self.assertGreater(ui.window.get_default_size().height,100)
        preferences.show(ui)
        ui.preferences_window.controls['app_animations'].set_selected(2)
        self.assertFalse(Gtk.Settings.get_default().get_property('gtk-enable-animations'))
        self.assertEqual(ui.preferences['window_animations'],'off')
        ui.preferences_window.close()

    def test_code_copy_overlay_and_path_first(self):
        from gi.repository import Gtk
        from rich_content import MarkdownView
        from info_view import MarkdownWindow
        block = MarkdownView('```sh\necho hello\n```').get_first_child()
        self.assertIsInstance(block, Gtk.Overlay)
        self.assertEqual(block.get_child().get_text(), 'echo hello')
        self.assertEqual(block.get_child().get_yalign(), 0)
        copy = block.get_child().get_next_sibling()
        self.assertIsInstance(copy, Gtk.Button)
        self.assertEqual(copy.get_valign(), Gtk.Align.START)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'guide.md'; path.write_text('Example')
            dialog = MarkdownWindow(self.ui, self.ui.window, path, 'Guide')
            toolbar = dialog.get_child().get_first_child().get_next_sibling().get_next_sibling()
            self.assertEqual(toolbar.get_first_child().get_label(), 'Copy path')
            dialog.destroy()

    def test_keycaps_preserve_plus_and_alternatives(self):
        from shortcut_data import hotkey_caps
        box = hotkey_caps('Ctrl++ / Ctrl+Shift+=')
        labels = []; child = box.get_first_child()
        while child:
            labels.append(child.get_text()); child = child.get_next_sibling()
        self.assertEqual(labels, ['Ctrl', '+', '/', 'Ctrl', 'Shift', '='])

    def test_hover_details_opt_in_delay_and_cancel(self):
        from gi.repository import Gtk
        from shortcut_data import attach_tooltip
        button = Gtk.Button(label='Hover')
        dialog = Gtk.Window(transient_for=self.ui.window, child=button)
        prefs = {'shortcut_tooltips': False, 'tooltip_delay': 100}
        attach_tooltip(button, dict(key='SUPER + T', name='Terminal', group='Apps', dispatcher='exec', arg='terminal'), preferences=lambda: prefs)
        dialog.present(); self.pump(.1)
        motion = button.shortcut_tooltip_motion
        motion.emit('enter', 1., 1.); self.pump(.15)
        self.assertIsNone(button.shortcut_tooltip['popover'])
        prefs['shortcut_tooltips'] = True
        motion.emit('enter', 1., 1.); self.pump(.03)
        self.assertIsNone(button.shortcut_tooltip['popover'])
        motion.emit('leave'); self.pump(.12)
        self.assertIsNone(button.shortcut_tooltip['popover'])
        focus = dialog.get_focus()
        motion.emit('enter', 1., 1.); self.pump(.15)
        self.assertIsNotNone(button.shortcut_tooltip['popover'])
        self.assertEqual(dialog.get_focus(), focus)
        dialog.destroy(); self.pump(.05)
        self.assertIsNone(button.shortcut_tooltip['popover'])

    def test_input_feature_dialog_and_scoped_gesture(self):
        from gi.repository import Gdk
        ui=self.ui
        self.assertFalse(ui.command_buttons['Mouse gestures & controllers'].get_visible())
        ui.set_feature('inputs',True)
        self.assertTrue(ui.command_buttons['Mouse gestures & controllers'].get_visible())
        ui.input_controls.show();self.pump(.1)
        window=ui.input_controls.window
        self.assertFalse(ui.input_controls.test_enabled)
        self.assertTrue(window.dialog_keys.emit('key-pressed',Gdk.KEY_Escape,0,Gdk.ModifierType(0)))
        self.pump(.1)
        self.assertIsNone(ui.input_controls.window)
        ui.input_controls.config['gestures']['left']='clear'
        ui.search.set_text('example')
        with patch.object(ui.input_controls,'active',return_value=False):ui.input_controls.gesture(None,-60,0)
        self.assertEqual(ui.search.get_text(),'example')
        with patch.object(ui.input_controls,'active',return_value=True):ui.input_controls.gesture(None,-60,0)
        self.assertEqual(ui.search.get_text(),'')

    def test_search_memory_is_opt_in(self):
        self.assertFalse(self.ui.preferences['remember_search'])
        self.assertFalse(self.ui.preferences['shortcut_tooltips'])
        self.ui.search.set_text('private query'); self.pump(.1)
        self.ui.save_ui_state()
        self.assertEqual(self.ui.saved_filters['search'], '')
        self.ui.preferences['remember_search'] = True
        self.ui.save_ui_state()
        self.assertEqual(self.ui.saved_filters['search'], 'private query')

    def test_filtered_feature_cards_keep_natural_height(self):
        from gi.repository import Gtk
        ui = self.ui
        ui.show_features(); self.pump(.1)
        gallery = ui.features_window
        gallery.preview_switch.set_active(True)
        gallery.description_switch.set_active(True)
        gallery.feature_search.set_text('bookmarks'); self.pump(.15)
        self.assertEqual(gallery.feature_cards.get_valign(), Gtk.Align.START)
        child = gallery.feature_cards.get_first_child()
        shown = []
        while child:
            if child.get_child_visible(): shown.append(child)
            child = child.get_next_sibling()
        self.assertEqual(len(shown),1)
        self.assertLess(shown[0].get_height(), gallery.get_child().get_height()*.75)
        gallery.close()

    def test_seeded_interactions(self):
        """Deterministic chaos run: settings, filters, dialogs and chat toggles."""
        import app, preferences
        ui = self.ui
        seed = int(os.environ.get('BINDLUME_CHAOS_SEED', '20260920'))
        rng = random.Random(seed)
        choices = ['search','chat','settings','icons','features','style']
        for step in range(int(os.environ.get('BINDLUME_CHAOS_STEPS', '80'))):
            operation = rng.choice(choices)
            with self.subTest(seed=seed, step=step, operation=operation):
                if operation == 'search': ui.search.set_text(rng.choice(['','terminal','@super','no matches 999']))
                elif operation == 'chat': ui.show_chat(ui.main_pane.get_end_child() is None)
                elif operation == 'settings':
                    preferences.show(ui); ui.preferences_window.close()
                elif operation == 'icons': ui.set_preference(rng.choice(['app_icons','action_icons']),rng.choice([True,False]))
                elif operation == 'features': ui.set_feature(rng.choice(['layouts','bookmarks','hidden']),rng.choice([True,False]))
                elif operation == 'style':
                    ui.look = rng.choice(['system','rounded','square'])
                    ui.set_feature('appearance',True)
                self.pump(.015)
                self.assertTrue(ui.window.get_visible())
                self.assertIn(ui.view_stack.get_visible_child_name(),['list','keyboard'])
                self.assertEqual(ui.preferences['window_animations'],'off')
        ui.show_chat(False)
        ui.features = app.DEFAULT_FEATURES.copy(); ui.apply_features()
        ui.search.set_text(''); self.pump(.1)
        self.assertEqual(ui.list_model.get_n_items(),len(ui.filtered_items()))

    @unittest.skipUnless(os.environ.get('NATIVE_PHOTOS'), 'Opt-in screenshots')
    def test_photos(self):
        output = Path(os.environ['NATIVE_PHOTOS']); output.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory() as folder:
            library = Path(folder)/'capture.so'
            flags = shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','gtk4'],text=True))
            subprocess.run(['cc','-shared','-fPIC','-Wno-deprecated-declarations','tests/visual_capture.c','-o',str(library),*flags],check=True)
            native=ctypes.CDLL(str(library));native.capture.argtypes=[ctypes.c_void_p,ctypes.c_char_p]
            pointer=ctypes.pythonapi.PyCapsule_GetPointer;pointer.argtypes=[ctypes.py_object,ctypes.c_char_p];pointer.restype=ctypes.c_void_p
            ui=self.ui
            ui.items = [dict(id=str(i),key=key,name=label,group='Actions',dispatcher='exec',arg='',type_icon='⚙') for i,(key,label) in enumerate([
                ('SUPER + K','Keybindings'),('SUPER + SPACE','Omarchy menu'),('SUPER + RETURN','Terminal'),
                ('SUPER SHIFT + RETURN','Browser'),('SUPER SHIFT + F','File manager'),('SUPER + ESCAPE','System menu'),
                ('SUPER SHIFT CTRL + SPACE','Theme menu'),('SUPER + F','Full screen'),('SUPER ALT + F','Full width'),
                ('SUPER + W','Close window'),('CTRL ALT + DELETE','Close all windows')])]
            ui.window.set_decorated(False)
            for mode in ['system','light','dark']:
                ui.set_preference('theme',mode)
                for state in ['list','scrolled','empty','chat']:
                    ui.search.set_text('unmatched search' if state=='empty' else '')
                    ui.show_chat(state=='chat'); ui.render(); self.pump(.25)
                    if state=='scrolled': ui.list_scroll.get_vadjustment().set_value(75);self.pump(.1)
                    ui.window.set_size_request(*ui.window.get_default_size())
                    path=output/(mode+'-'+state+'.png')
                    self.assertEqual(native.capture(pointer(ui.window.__gpointer__,None),str(path).encode()),0)
                    ui.window.set_size_request(-1,-1)

            import source_library, preferences
            ui.source_counts.update({'Chromium':30,'Google Chrome':30})
            for language in ['en','hu']:
                ui.set_preference('language',language)
                source_library.show(ui); self.pump(.25)
                self.assertEqual(native.capture(pointer(ui.source_library_window.__gpointer__,None),str(output/('sets-'+language+'.png')).encode()),0)
                ui.source_library_window.close()
            ui.set_preference('language','system')
            preferences.show(ui); self.pump(.2)
            self.assertEqual(native.capture(pointer(ui.preferences_window.__gpointer__,None),str(output/'system-language.png').encode()),0)
            ui.preferences_window.close()
            from info_view import MarkdownWindow
            dialog = MarkdownWindow(ui, ui.window, Path('SHORTCUT_SETS.md').resolve(), 'Create shortcut sets')
            dialog.present(); self.pump(.2)
            self.assertEqual(native.capture(pointer(dialog.__gpointer__,None),str(output/'guide.png').encode()),0)
            scroll = dialog.get_child().get_first_child().get_next_sibling().get_next_sibling().get_next_sibling()
            adjustment = scroll.get_vadjustment(); adjustment.set_value(adjustment.get_upper()); self.pump(.15)
            self.assertEqual(native.capture(pointer(dialog.__gpointer__,None),str(output/'guide-bottom.png').encode()),0)
            dialog.close()
            ui.set_feature('inputs', True)
            ui.input_controls.show(); self.pump(.2)
            self.assertEqual(native.capture(pointer(ui.input_controls.window.__gpointer__,None),str(output/'input-controls.png').encode()),0)
            controls_scroll=ui.input_controls.window.get_child().get_last_child()
            controls_scroll.get_vadjustment().set_value(controls_scroll.get_vadjustment().get_upper());self.pump(.15)
            self.assertEqual(native.capture(pointer(ui.input_controls.window.__gpointer__,None),str(output/'input-controls-bottom.png').encode()),0)
            ui.input_controls.window.close(); self.pump(.1)
            from gi.repository import Gtk
            from usage_view import populate
            usage = Gtk.Window(application=ui, transient_for=ui.window, default_width=440, default_height=760)
            usage.add_css_class('shortcuts-app')
            body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=20, margin_bottom=20, margin_start=20, margin_end=20)
            from datetime import datetime, timezone
            populate(body,['codex'],{'codex':{'tier':'pro','windows':[{'name':'weekly','remaining_percent':92}]}},[{'provider':'codex','turn_usage':[{'input_tokens':32000,'output_tokens':800,'created_at':datetime.now(timezone.utc).isoformat(),'model':'Example model'}]}],True)
            usage.set_child(body);usage.present();self.pump(.2)
            self.assertEqual(native.capture(pointer(usage.__gpointer__,None),str(output/'usage.png').encode()),0)
            usage.destroy()
