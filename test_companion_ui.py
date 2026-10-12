import os
import tempfile
import unittest
from unittest.mock import patch
import test_ui_workflows as workflows
from test_ui_workflows import pump
from gi.repository import Gtk, Gdk
from rich_content import MarkdownView, KeyboardSnippet, blocks, inline
from companion import read_memory, write_memory
from chat import normalize_usage

class ContentTests(unittest.TestCase):
    def test_markdown_blocks_and_safe_inline(self):
        data=list(blocks('# Title\n\n| Key | Action |\n| --- | --- |\n| **Super** | Test |\n\n```python\nx = 2\n\ny = 3\n```'))
        self.assertEqual([x[0] for x in data],['heading','table','code'])
        self.assertIn('\n\n',data[2][2])
        self.assertEqual(inline('<script> **bold** [x](javascript:evil)'), '&lt;script&gt; <b>bold</b> x')
    def test_memory_and_usage(self):
        with tempfile.TemporaryDirectory() as folder:
            write_memory(folder,['Prefer compact diagrams','Prefer compact diagrams','My name is István'])
            self.assertEqual(read_memory(folder),['Prefer compact diagrams','My name is István'])
        self.assertEqual(normalize_usage({'input_tokens':23,'output_tokens':7,'cached_input_tokens':10}),{'input_tokens':23,'output_tokens':7,'cached_input_tokens':10})

@unittest.skipUnless(os.environ.get('GDK_BACKEND')=='broadway','Private display required')
class CompanionUiTests(unittest.TestCase):
    def setUp(self):
        self.fixture=workflows.UiWorkflows();self.fixture.setUp();self.ui=self.fixture.ui
    def tearDown(self):
        for name in ('about_window','info_window','companion_window','guide_window','activity_window','changelog_window'):
            window=getattr(self.ui,name,None)
            if window:window.destroy()
        self.fixture.tearDown()
    def test_about_companion_and_memory_opt_in(self):
        import companion,agent_control
        self.ui.show_info();pump();self.assertIsNotNone(self.ui.about_window)
        self.ui.show_details();pump();self.assertIs(self.ui.info_window.get_transient_for(),self.ui.about_window)
        companion.show(self.ui);pump();self.assertIsNotNone(self.ui.companion_window)
        with self.assertRaises(ValueError):agent_control.execute(self.ui,{'operation':'companion','arguments':{'action':'remember','text':'Name is István'}})
        self.ui.preferences['chat_memory_enabled']=True
        reply=agent_control.execute(self.ui,{'operation':'companion','arguments':{'action':'remember','text':'Name is István'}})
        self.assertIn('Name is István',reply['memory'])
    def test_guide_side_preview_and_autosave(self):
        import guide_settings
        with patch('guide_settings.GuideController.read',return_value=guide_settings.defaults()),patch('guide_settings.GuideController.backend',return_value=[]),patch('guide_settings.GuideController.patch') as saved:
            self.ui.show_guide();pump(.3);window=self.ui.guide_window
            window.controls['preview_side'].set_active(True);pump()
            self.assertGreater(window.get_default_size()[0],740)
            window.controls['autosave'].set_active(True)
            window.controls['showIcons'].set_active(False);pump(.6)
            self.assertTrue(saved.called);self.assertFalse(window.original['showIcons'])
            window.dialog_keys.emit('key-pressed',Gdk.KEY_Escape,0,Gdk.ModifierType(0));pump()
            self.assertIsNone(self.ui.guide_window)
    def test_rich_chat_widgets(self):
        self.ui.show_chat();panel=self.ui.chat_panel
        self.ui.preferences['chat_snippets']=True
        widget=panel.bubble('assistant','**Hi**\n\n| Key | Action |\n| --- | --- |\n| Super | Open |\n\n```keyboard\n{"keys":["SUPER","Y"]}\n```')
        self.assertIsInstance(widget,MarkdownView)
        self.assertIsInstance(widget.get_last_child(),KeyboardSnippet)
        pump(.2)


class KeyboardGeometryTests(unittest.TestCase):
    def test_physical_row_offsets_and_equal_widths(self):
        rows = KeyboardSnippet.layout()
        positions = {}
        for row in rows:
            x = 0
            for key, width in row:
                positions.setdefault(key, x)
                x += width
            self.assertEqual(x, 15)
        for top, home, bottom in zip('QWE', 'ASD', 'ZXC'):
            self.assertEqual(positions[home] - positions[top], .25)
            self.assertEqual(positions[bottom] - positions[home], .5)


@unittest.skipUnless(os.environ.get("GDK_BACKEND") == "broadway", "Private display required")
class DecisionUiTests(unittest.TestCase):
    setUp = CompanionUiTests.setUp
    tearDown = CompanionUiTests.tearDown

    def test_decision_controls_batch_validation_and_ranking(self):
        import companion, agent_control, decision_workflows
        companion.show(self.ui);pump()
        controls=self.ui.companion_window.decision_controls['laya']
        controls['enabled'].set_active(True)
        controls['url'].set_text('http://remote.example/v1')
        controls['apply'].emit('clicked')
        self.assertEqual(self.ui.preferences['decision_connections'],{})
        controls['url'].set_text('http://127.0.0.1:8001/v1')
        controls['apply'].emit('clicked')
        self.assertTrue(self.ui.preferences['decision_connections']['laya']['enabled'])
        before=dict(self.ui.preferences)
        with self.assertRaises(ValueError):
            agent_control.execute(self.ui,{'operation':'decision_apply','arguments':{'values':{'theme':'dark','chat_memory_enabled':True}}})
        self.assertEqual(self.ui.preferences,before)
        result=agent_control.execute(self.ui,{'operation':'decision_apply','arguments':{'values':{'theme':'dark','compact':True}}})
        self.assertEqual(result,{'theme':'dark','compact':True})
        self.ui.preferences['decision_ranker']='laya'
        with patch('decision_workflows.rank', side_effect=lambda p,prefs,q,items:list(reversed(items))) as rank:
            self.ui.search.set_text('')
            self.ui.search.set_text('a')
            pump(.8)
            self.assertGreater(rank.call_count,0)
        self.ui.preferences['decision_ranker']=''

    @unittest.skipUnless(os.environ.get('SYSTEM_ONE_REVIEW'), 'Opt-in private visual review')
    def test_decision_settings_capture(self):
        import companion, ctypes, subprocess, shlex
        from pathlib import Path
        companion.show(self.ui);pump()
        window=self.ui.companion_window
        window.tabs.set_visible_child_name('system-one')
        window.set_default_size(800,900)
        group=window.decision_controls['laya']['group'];group.set_expanded(True)
        def descendants(widget):
            yield widget
            child=widget.get_first_child()
            while child:
                yield from descendants(child);child=child.get_next_sibling()
        scroll=window.tabs.get_visible_child()
        pump(.2)
        scroll.get_vadjustment().set_value(300);pump(.2)
        with tempfile.TemporaryDirectory() as directory:
            library=Path(directory)/'capture.so'
            flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','gtk4'],text=True))
            subprocess.run(['cc','-shared','-fPIC','-Wno-deprecated-declarations','tests/visual_capture.c','-o',str(library),*flags],check=True)
            native=ctypes.CDLL(str(library));native.capture.argtypes=[ctypes.c_void_p,ctypes.c_char_p]
            pointer=ctypes.pythonapi.PyCapsule_GetPointer;pointer.argtypes=[ctypes.py_object,ctypes.c_char_p];pointer.restype=ctypes.c_void_p
            self.assertEqual(native.capture(pointer(window.__gpointer__,None),os.environ['SYSTEM_ONE_REVIEW'].encode()),0)
            scroll.get_vadjustment().set_value(650);pump(.2)
            target=str(Path(os.environ['SYSTEM_ONE_REVIEW']).with_name('system-one-workflows.png'))
            self.assertEqual(native.capture(pointer(window.__gpointer__,None),target.encode()),0)
            window.close();pump()
            self.ui.preferences['decision_connections']={'laya':{'enabled':True}}
            with patch('chat_view.available_agents',return_value=['decision_laya']):
                self.ui.show_chat(True);pump()
                panel=self.ui.chat_panel
                panel.session=panel.store.create('decision_laya','Switch to dark theme')
                panel.session['model']='laya-rl-agent'
                panel.session['messages']=[{'role':'user','content':'Switch to dark theme.','created_at':panel.session['created_at']},
                    {'role':'assistant','content':'Applied settings:\n```json\n{"applied": {"theme": "dark"}, "decision": "dark", "probability": 0.93}\n```','created_at':panel.session['created_at']}]
                panel.store.save(panel.session);panel.open(panel.session['id'])
                self.ui.window.set_size_request(1100,700);pump(.3)
                target=str(Path(os.environ['SYSTEM_ONE_REVIEW']).with_name('system-one-chat.png'))
                self.assertEqual(native.capture(pointer(self.ui.window.__gpointer__,None),target.encode()),0)


    def test_search_ranking_discards_stale_results(self):
        import threading
        from decision_workflows import SearchRanking
        from unittest.mock import Mock
        ranking=SearchRanking()
        started=threading.Event();release=threading.Event()
        self.ui.preferences['decision_ranker']='laya'
        self.ui.preferences['decision_connections']={'laya':{'enabled':True}}
        items=[dict(id='one',name='Alpha',key='A'),dict(id='two',name='Beta',key='B')]
        def delayed(*_):
            started.set();release.wait(2)
            return list(reversed(items))
        # Suppress unrelated app rendering; exercise this ranking instance directly.
        with patch.object(self.ui,'render',Mock()),patch('decision_workflows.rank',side_effect=delayed):
            ranking.apply(self.ui,'old',items);pump(.4)
            self.assertTrue(started.is_set())
            ranking.apply(self.ui,'',items)
            release.set();pump(.2)
            self.assertIsNone(ranking.order)
            self.assertEqual(ranking.apply(self.ui,'',items),items)

    def test_decision_enable_filters_changes_private_ui(self):
        import agent_control, decision_workflows, threading
        self.ui.features['layouts']=False;self.ui.apply_features()
        def control(payload, **_):return agent_control.execute(self.ui,payload)
        with patch('agent_control.request',side_effect=control),patch('decision_workflows.decide') as model:
            reply=list(decision_workflows.events('decision_laya',{},'enable filters',threading.Event()))
        self.assertTrue(self.ui.feature_enabled('layouts'))
        self.assertTrue(self.ui.settings_switches['Show filters'].get_active())
        self.assertIn('layouts',reply[0]['delta'])
        model.assert_not_called()

    def test_auto_selects_local_first_without_quota_call(self):
        self.ui.preferences['decision_connections']={'laya':{'enabled':True}}
        with patch('chat_view.available_agents',return_value=['codex','decision_laya']):
            self.ui.show_chat(True);panel=self.ui.chat_panel
            with patch.object(panel,'begin_send') as begin,patch('chat_view.choose_agent') as choose:
                panel.dispatch('Explain the keyboard guide');pump(.3)
                begin.assert_called_once_with('Explain the keyboard guide','decision_laya','auto')
                choose.assert_not_called()
