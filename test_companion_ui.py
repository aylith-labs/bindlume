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
        for name in ('about_window','info_window','companion_window','guide_window'):
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
