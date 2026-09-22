"""Reproducible real GTK screenshots with public shortcut fixtures, never user data."""
import ctypes, json, os, shlex, subprocess, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import test_ui_workflows as workflows
from test_ui_workflows import pump
import app

@unittest.skipUnless(os.environ.get('LANDING_SHOTS'), 'Opt-in screenshot export')
class LandingCapture(unittest.TestCase):
    def test_export(self):
        output=Path(os.environ['LANDING_SHOTS']);output.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory() as root:
            library=Path(root)/'capture.so'
            flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','gtk4'],text=True))
            subprocess.run(['cc','-shared','-fPIC',str(Path(__file__).with_name('visual_capture.c')),'-o',str(library),*flags],check=True,capture_output=True)
            native=ctypes.CDLL(str(library));native.capture.argtypes=[ctypes.c_void_p,ctypes.c_char_p]
            pointer=ctypes.pythonapi.PyCapsule_GetPointer;pointer.argtypes=[ctypes.py_object,ctypes.c_char_p];pointer.restype=ctypes.c_void_p
            fixture=workflows.UiWorkflows();fixture.setUp();ui=fixture.ui
            try:
                ui.features=app.DEFAULT_FEATURES.copy();ui.features['appearance']=True
                ui.preferences['language']='en';ui.preferences['system_typography']=False
                ui.preferences['font_family']='sans-serif';ui.preferences['font_size']=16
                ui.flat_list=True;ui.columns=True;ui.favorites=set();ui.learned=set()
                ui.window.set_decorated(False)
                data=json.loads((Path(__file__).parents[1]/'bundled-shortcut-sets/chromium.json').read_text())
                browser=[dict(id=r['id'],key=r['keys'],name=r['title'],group=r['category'],kind='action',dispatcher='',arg='') for r in data['shortcuts'][:8]]
                desktop=[dict(id=str(i),key=k,name=n,group='Desktop',kind='action',dispatcher='',arg='') for i,(k,n) in enumerate([
                    ('SUPER + F','Full screen'),('SUPER + W','Close window'),('SUPER CTRL SHIFT + SPACE','Theme menu'),
                    ('SUPER + RETURN','Terminal'),('SUPER SHIFT + RETURN','Browser'),('SUPER SHIFT + F','File manager'),('SUPER + 1','Workspace 1')])]
                for style in ('square','rounded','neo-brutalism'):
                    for mode in ('light','dark'):
                        for source,rows in [('Omarchy',desktop),('Chromium',browser)]:
                            with patch.object(ui,'sync_native_presentation'):
                                ui.look=style;ui.preferences['theme']=mode;ui.apply_features()
                                ui.source_name=source
                                ui._updating_source_model=True
                                ui.source_picker.set_selected(app.SOURCES.index(source))
                                ui._updating_source_model=False
                                ui.items=rows;ui.render()
                                ui.window.set_size_request(1000,670);ui.window.set_default_size(1000,670);ui.window.present();pump(.4)
                                path=output/f'{style}-{mode}-{source.lower()}.png'
                                self.assertEqual(native.capture(pointer(ui.window.__gpointer__,None),str(path).encode()),0)
                ui.look='square';ui.preferences['theme']='dark';ui.apply_features()
                ui.items=[dict(row,id=f'{i}-{row["id"]}') for i in range(12) for row in desktop]
                ui.render();ui.window.set_size_request(1000,670);pump(.3)
                ui.list_scroll.get_vadjustment().set_value(100);pump(.2)
                self.assertEqual(native.capture(pointer(ui.window.__gpointer__,None),str(output/'scroll-fades.png').encode()),0)
                import preferences
                preferences.show(ui);pump()
                picker=ui.preferences_window.controls['global_hotkey'];picker.capture.set_active(True);pump()
                self.assertEqual(native.capture(pointer(ui.preferences_window.__gpointer__,None),str(output/'capture-listening.png').encode()),0)
                picker.capture.set_active(False);ui.preferences_window.close()
                ui.features['agent']=True
                with patch('chat_view.available_agents',return_value=['codex']):
                    ui.show_chat(True);pump()
                    self.assertEqual(native.capture(pointer(ui.window.__gpointer__,None),str(output/'chat-composer.png').encode()),0)
            finally:fixture.tearDown()
