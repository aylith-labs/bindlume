import unittest
from shortcut_types import annotate, matches_type

class ShortcutTypesTests(unittest.TestCase):
    def test_metadata_keeps_identity_and_uses_app_icon(self):
        rows = [dict(id='keep', key='SUPER SHIFT + A', name='ChatGPT', group='Apps & tools')]
        meta = [dict(modifiers=['SHIFT', 'SUPER'], key='A', displayKind='webapp', icon='/tmp/favicon.png')]
        result = annotate(rows, meta)[0]
        self.assertEqual(result['id'], 'keep')
        self.assertEqual(result['group'], 'Web App')
        self.assertEqual(result['topic'], 'Apps & tools')
        self.assertEqual(result['app_icon'], '/tmp/favicon.png')
        self.assertTrue(matches_type(result, 'apps'))
        self.assertTrue(matches_type(result, 'webapp'))
        self.assertFalse(matches_type(result, 'cmd'))

    def test_missing_metadata_is_not_misclassified(self):
        row = dict(key='F12', name='Custom', group='Apps & tools')
        self.assertEqual(annotate([row], [])[0]['kind'], 'unknown')

    def test_action_icon_follows_setting(self):
        row = dict(key='SUPER + W', name='Close', group='Windows')
        meta = [dict(modifiers=['SUPER'], key='W', displayKind='action')]
        self.assertEqual(annotate([row], meta, False)[0]['type_icon'], '')
