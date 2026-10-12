import io
import json
import os
import threading
import unittest
from unittest.mock import patch, MagicMock
import test_companion_ui as fixture
import test_activity_log as capture
from test_ui_workflows import pump
from gi.repository import Gtk
import companion
import model_insights

@unittest.skipUnless(os.environ.get('GDK_BACKEND')=='broadway','Private display required')
class ReleaseTests(unittest.TestCase):
    setUp=fixture.CompanionUiTests.setUp
    tearDown=fixture.CompanionUiTests.tearDown
    capture=capture.ActivityTests.capture

    def test_keyboard_request_is_exact_and_renders_without_global_opt_in(self):
        from decision_commands import execute
        from rich_content import KeyboardSnippet
        rows=[dict(id='theme',title='Theme menu',keys='SUPER SHIFT CTRL + SPACE',source='Omarchy'),dict(id='focus',title='Focus on next window',keys='ALT + TAB',source='Omarchy')]
        request=MagicMock(return_value=rows)
        result=execute('show theme shortcut on the keyboard',request,threading.Event())[0]['delta']
        self.assertNotIn('Focus',result)
        self.assertIn('```keyboard',result)
        self.assertEqual(request.call_count,1)
        self.ui.set_preference('decision_connections',{'laya':{'enabled':True}})
        self.ui.window.set_size_request(1400,850);pump(.2)
        with patch.object(self.ui.window,'get_surface',return_value=None):self.ui.show_chat()
        panel=self.ui.chat_panel
        panel.session=panel.store.create('decision_laya','Theme preview')
        panel.session['messages']=[{'role':'user','content':'show theme shortcut on the keyboard','created_at':panel.session['created_at']},{'role':'assistant','content':result,'created_at':panel.session['created_at']}]
        self.assertFalse(self.ui.preferences['chat_snippets'])
        panel.render();pump()
        view=panel.messages.get_last_child().get_last_child()
        self.assertIsInstance(view.get_last_child(),KeyboardSnippet)
        self.assertEqual(view.get_last_child().keys,{'SUPER','SHIFT','CTRL','SPACE'})
        if os.environ.get('RELEASE_REVIEW'):
            self.ui.main_pane.set_position(650);pump(.3)
            panel.scroll.get_vadjustment().set_value(panel.scroll.get_vadjustment().get_upper());pump(.2)
            self.capture(self.ui.window,'020-keyboard-preview')

    def test_tabs_explanations_indicators_and_changelog(self):
        import changelog
        companion.show(self.ui);pump()
        window=self.ui.companion_window
        for page in ('general','models','system-one','personalization','insights'):
            self.assertIsNotNone(window.tabs.get_child_by_name(page))
        self.ui.set_preference('decision_connections',{'laya':{'enabled':True}})
        self.ui.set_preference('decision_ranker','laya')
        self.ui.set_preference('decision_router','laya')
        self.assertTrue(all(label.get_visible() for label in self.ui.workflow_indicators))
        self.assertIn('Laya',self.ui.workflow_indicators[0].get_text())
        self.assertIn('24',self.ui.workflow_indicators[0].get_tooltip_text())
        self.ui.set_preference('decision_ranker','')
        self.assertFalse(self.ui.workflow_indicators[0].get_visible())
        self.ui.show_info();changelog.show(self.ui);pump()
        groups=self.ui.changelog_window.release_groups
        self.assertGreaterEqual(len(groups),3)
        self.assertTrue(groups[0].get_expanded())
        self.assertTrue(all(not group.get_expanded() for group in groups[1:]))
        self.assertTrue(groups[1].get_label_widget().get_last_child().get_tooltip_text())
        if os.environ.get('RELEASE_REVIEW'):
            self.capture(self.ui.changelog_window,'020-changelog')
            self.ui.changelog_window.close();self.ui.about_window.close()
            window.tabs.set_visible_child_name('system-one')
            scroll=window.tabs.get_visible_child();pump(.2)
            scroll.get_vadjustment().set_value(scroll.get_vadjustment().get_upper());pump(.2)
            self.capture(window,'020-system-one')
            window.tabs.set_visible_child_name('insights')
            model_insights.record({'model_insights_enabled':True},'Laya','System One',{'state':{'query':'theme'},'questions':{'relevance':{'type':'score','criteria':['unrelated','related']}}})
            window.insights.reload_insights();pump(.2)
            rows=window.insights.get_last_child();rows.get_first_child().set_expanded(True);pump(.2)
            window.tabs.get_visible_child().get_vadjustment().set_value(220);pump(.2)
            self.capture(window,'020-insights')

    def test_insights_records_wire_body_not_credentials_and_keeps_usage_separate(self):
        import system_one
        from test_system_one import QUESTIONS,RESULT
        prefs={'model_insights_enabled':True,'decision_connections':{'jev':{'enabled':True}}}
        opener=MagicMock();opener.open.return_value=io.BytesIO(json.dumps(RESULT).encode())
        with patch.dict('os.environ',{'TYPESAFE_API_KEY':'never-record-this-key'}),patch('system_one.build_opener',return_value=opener):
            system_one.decide('jev',prefs,{'query':'theme'},QUESTIONS)
        entry=model_insights.entries()[0]
        self.assertEqual(entry['content'],opener.open.call_args.args[0].data.decode())
        self.assertNotIn('never-record-this-key',json.dumps(entry))
        self.assertIsNone(entry['reported_input_tokens'])
        self.assertGreater(entry['estimated_tokens'],0)
        self.assertIn('questions',entry['components'])
        model_insights.usage(entry['id'],{'prompt_tokens':42})
        self.assertEqual(model_insights.entries()[0]['reported_input_tokens'],42)
        model_insights.record({},'off','Agent input','not stored')
        self.assertEqual(len(model_insights.entries()),1)
        model_insights.clear();self.assertEqual(model_insights.entries(),[])

    def test_insights_bounds_and_zero_model_tokens_for_local_commands(self):
        prefs={'model_insights_enabled':True}
        for index in range(52):model_insights.record(prefs,'local','Local command',str(index))
        self.assertEqual(len(model_insights.entries()),50)
        self.assertEqual(model_insights.entries()[0]['estimated_tokens'],0)
        model_insights.record(prefs,'model','Agent input','x'*(model_insights.MAX_BYTES+9))
        entry=model_insights.entries()[0]
        self.assertTrue(entry['truncated'])
        self.assertEqual(len(entry['content']),model_insights.MAX_BYTES)
        self.assertEqual(entry['bytes'],model_insights.MAX_BYTES+9)

    def test_new_release_text_has_every_translation(self):
        import changelog,localization
        keys=[companion.RANKING_HELP,companion.ROUTING_HELP,model_insights.DESCRIPTION,model_insights.TOKEN_HELP]
        keys += [note for release in changelog.releases() for note in release['changes']]
        for key in keys:
            self.assertEqual(set(localization.CATALOG[key]),set(localization.LANGUAGE_NAMES)-{'en'},key)
