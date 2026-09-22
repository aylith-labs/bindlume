"""Opt-in screenshots on a private GTK display; no desktop or real agent turns.
VISUAL_REVIEW_DIR=/tmp/review VISUAL_STYLES=square,rounded python tests/run.py tests.visual_review
"""
import ctypes
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import test_ui_workflows as workflows
from test_ui_workflows import pump
from gi.repository import Gtk
import app, preferences, source_library, localization, guide_settings


@unittest.skipUnless(os.environ.get('VISUAL_REVIEW_DIR'), 'Opt-in photo review')
class Capture(unittest.TestCase):
    def test_capture(self):
        output = Path(os.environ['VISUAL_REVIEW_DIR']); output.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as folder:
            library = Path(folder)/'capture.so'
            flags = shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','gtk4'], text=True))
            subprocess.run(['cc','-shared','-fPIC','-Wno-deprecated-declarations',str(Path(__file__).with_name('visual_capture.c')),'-o',str(library),*flags],check=True)
            native = ctypes.CDLL(str(library)); native.capture.argtypes = [ctypes.c_void_p,ctypes.c_char_p]
            pointer = ctypes.pythonapi.PyCapsule_GetPointer
            pointer.argtypes = [ctypes.py_object,ctypes.c_char_p]; pointer.restype = ctypes.c_void_p
            fixture = workflows.UiWorkflows(); fixture.setUp(); ui=fixture.ui
            records=[]
            def capture(name, widget):
                if isinstance(widget,Gtk.Window):
                    widget.set_decorated(False)
                    widget.present()
                pump(.3)
                path=output/(prefix+'-'+name+'.png')
                result=native.capture(pointer(widget.__gpointer__,None),str(path).encode())
                self.assertEqual(result,0,name)
                records.append(dict(name=name,file=path.name,width=widget.get_width(),height=widget.get_height()))
            def descendants(widget):
                yield widget
                child=widget.get_first_child()
                while child:
                    yield from descendants(child); child=child.get_next_sibling()
            def scroll_bottom(window):
                for widget in descendants(window):
                    if isinstance(widget,Gtk.ScrolledWindow):
                        adjustment=widget.get_vadjustment()
                        adjustment.set_value(adjustment.get_upper()-adjustment.get_page_size());return
            try:
                for language in os.environ.get('VISUAL_LANGUAGES','hu').split(','):
                    ui.preferences['language']=language;localization.set_language(ui,language)
                    for style in os.environ.get('VISUAL_STYLES','rounded').split(','):
                        for theme in os.environ.get('VISUAL_THEMES','dark,light').split(','):
                            prefix=language+'-'+style+'-'+theme
                            ui.features={key:True for key in app.FEATURES}
                            ui.look=style;ui.preferences.update(theme=theme,app_icons=True,action_icons=True)
                            ui.system_theme.set_look(style);ui.system_theme.set_preferences(ui.preferences)
                            ui.source_name='Omarchy'; ui.columns=True;ui.flat_list=True
                            ui.items=[dict(id=str(i),key=key,name=name,group=group,kind=kind,dispatcher='exec',arg='',app_icon=icon,type_icon=symbol)
                                      for i,(key,name,group,kind,icon,symbol) in enumerate([
                                       ('SUPER + RETURN','Terminal','Command','command','utilities-terminal','⌘'),
                                       ('SUPER SHIFT + RETURN','Browser','Desktop App','desktopApp','web-browser',''),
                                       ('SUPER SHIFT + F','File manager','Desktop App','desktopApp','system-file-manager',''),
                                       ('SUPER + ESCAPE','System menu','System UI','systemUI','','⚙'),
                                       ('SUPER + F','Full screen','Action','action','',''),
                                       ('SUPER + W','Close window','Action','action','',''),
                                       ('PRINT','Screenshot','Command','command','','⌘')])]
                            ui.favorites={'0'};ui.learned={'5'};ui.render();ui.apply_feature_visibility()
                            ui.window.set_default_size(1000,720);capture('main',ui.window)
                            ui.app_menu_button.popup();capture('cog-menu',ui.app_menu_button.get_popover());ui.app_menu_button.popdown()
                            ui.menu_button.popup();capture('view-menu',ui.menu_button.get_popover());ui.menu_button.popdown()
                            ui.open_choice(ui.source_picker,from_control=True);capture('sources',ui.choice_popover);ui.dismiss_choice()
                            ui.view_toggle.set_active(True);capture('keyboard',ui.window);ui.view_toggle.set_active(False)
                            preferences.show(ui);capture('settings',ui.preferences_window)
                            ui.preferences_window.controls['theme'].set_selected({'system':0,'dark':1,'light':2}[theme])
                            capture('settings-selection',ui.preferences_window)
                            for name in ('theme','look','window_animations'):
                                control=ui.preferences_window.controls[name]
                                trigger=next((w for w in descendants(control) if isinstance(w,Gtk.ToggleButton)),None)
                                if trigger: trigger.set_active(True)
                                pump(.05)
                                popup=next((w for w in descendants(control) if isinstance(w,Gtk.Popover) and w.get_visible()),None)
                                if popup: capture('settings-'+name+'-menu',popup);popup.popdown()
                            scroll_bottom(ui.preferences_window);capture('settings-bottom',ui.preferences_window)
                            if os.environ.get('VISUAL_EXTRA'):
                                before=set(Gtk.Window.list_toplevels())
                                font=ui.preferences_window.controls['font']
                                trigger=next((w for w in descendants(font) if isinstance(w,Gtk.Button)),None)
                                if trigger: trigger.emit('clicked')
                                pump(.1)
                                chooser=next((w for w in Gtk.Window.list_toplevels() if w not in before and w.get_visible()),None)
                                if chooser: capture('font-chooser',chooser);chooser.close();pump()
                            ui.preferences_window.close();pump()
                            ui.show_features();capture('features',ui.features_window)
                            ui.features_window.feature_search.set_text('book');pump(.1);capture('features-filtered-card',ui.features_window)
                            ui.features_window.feature_search.set_text('')
                            for child in descendants(ui.features_window):
                                if isinstance(child,Gtk.ScrolledWindow):child.get_vadjustment().set_value(child.get_vadjustment().get_upper()/2);break
                            capture('features-middle',ui.features_window)
                            scroll_bottom(ui.features_window);capture('features-bottom',ui.features_window)
                            ui.features_window.preview_switch.set_active(False);ui.features_window.description_switch.set_active(False)
                            capture('features-flat',ui.features_window)
                            ui.features_window.feature_search.set_text('billentyű' if language=='hu' else 'shortcut');pump(.2);capture('features-filtered',ui.features_window)
                            ui.features_window.close();pump();ui.feature_view={}
                            source_library.show(ui);capture('shortcut-sets',ui.source_library_window)
                            if os.environ.get('VISUAL_EXTRA'):
                                from info_view import MarkdownWindow
                                guide=MarkdownWindow(ui,ui.source_library_window,Path(app.__file__).with_name('SHORTCUT_SETS.md'),'Create shortcut sets')
                                guide.present();capture('shortcut-set-guide',guide);guide.close();pump()
                            ui.source_library_window.close();pump()
                            ui.show_reset();capture('reset',ui.reset_window)
                            for child in descendants(ui.reset_window):
                                if isinstance(child,Gtk.Expander):child.set_expanded(True)
                            capture('reset-files',ui.reset_window);ui.reset_window.close();pump()
                            ui.show_shortcuts();capture('keyboard-shortcuts',ui.shortcuts_window);ui.shortcuts_window.close();pump()
                            ui.show_info();capture('about',ui.about_window)
                            ui.show_details();capture('internals',ui.info_window);ui.info_window.close();ui.about_window.close();pump()
                            with patch('chat_view.available_agents',return_value=['codex','claude']):
                                ui.show_chat();capture('chat-empty',ui.window)
                                panel=ui.chat_panel
                                session=panel.store.create('codex','Képernyőkép készítése' if language=='hu' else 'Taking screenshots')
                                session['messages']=[dict(role='user',content='Hogyan készíthetek képernyőképet?',created_at=session['created_at']),
                                                     dict(role='assistant',content='Nyomd meg a Print billentyűt a képernyőkép készítéséhez. A keresőben a @print kifejezéssel találod meg.',created_at=session['created_at'])]
                                session['messages'][-1]['content']='**Screenshot shortcuts**\n\n| Keys | Action |\n| --- | --- |\n| `Print` | Screenshot |\n| `Super + Y` | Example |\n\n```keyboard\n{"keys":["SUPER","Y"],"label":"Example shortcut"}\n```'
                                ui.preferences['chat_snippets']=True
                                panel.store.save(session);panel.open(session['id']);capture('chat-conversation',ui.window)
                                from rich_content import KeyboardSnippet
                                for w in descendants(panel):
                                    if isinstance(w,KeyboardSnippet):
                                        capture('keyboard-snippet',w)
                                import companion
                                companion.show(ui,panel);capture('companion-settings',ui.companion_window)
                                scroll_bottom(ui.companion_window);capture('companion-settings-bottom',ui.companion_window)
                                ui.companion_window.close();pump()
                                panel.choosing=True;panel.pending=['Jelöld meg kedvencként.'];panel.update_busy();capture('chat-working-queued',ui.window)
                                panel.choosing=False;panel.pending=[];panel.update_busy()
                                panel.history();capture('chat-history',panel.history_window);panel.history_window.close();pump()
                                if os.environ.get('VISUAL_EXTRA'):
                                    before=set(ui.get_windows());panel.rename(session)
                                    rename=next(w for w in ui.get_windows() if w not in before)
                                    capture('chat-rename',rename);rename.close();pump()
                                    panel.copy_button.popup();capture('chat-copy',panel.copy_button.get_popover());panel.copy_button.popdown()
                                panel.quota_ready({'codex':dict(status='available',windows=[dict(name='weekly',remaining_percent=97)])})
                                popover=panel.usage_body.get_ancestor(Gtk.Popover);popover.popup();capture('chat-usage',popover);popover.popdown()
                                panel.new();ui.show_chat(False)
                            bindings=[dict(id=item['id'],app_id=item['id'],key=item['key'].split(' + ')[-1],modifiers=['SUPER'],description=item['name']) for item in ui.items]
                            with patch('guide_settings.GuideController.read',return_value=guide_settings.defaults()),patch('guide_settings.GuideController.backend',return_value=bindings):
                                ui.show_guide();pump(.2);capture('guide-settings',ui.guide_window)
                                for child in descendants(ui.guide_window):
                                    if isinstance(child,Gtk.ScrolledWindow):child.get_vadjustment().set_value(child.get_vadjustment().get_upper()/2);break
                                capture('guide-preview',ui.guide_window)
                                scroll_bottom(ui.guide_window);capture('guide-settings-bottom',ui.guide_window)
                                ui.guide_window.controls['preview_side'].set_active(True);pump(.5)
                                capture('guide-side-preview',ui.guide_window)
                                ui.guide_window.controls['preview_side'].set_active(False)
                                ui.guide_window.close();pump()
                            print(prefix, len(records), 'photos',flush=True)
                (output/'manifest.json').write_text(json.dumps(records,indent=2))
            finally:
                fixture.tearDown()
                localization.language='en'
