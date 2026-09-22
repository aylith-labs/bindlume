import unittest
from binding_sources import chord, printed, tmux_records, resolved

class SourceTests(unittest.TestCase):
    def test_missing_optional_executables_do_not_crash_discovery(self):
        from unittest.mock import patch
        from binding_sources import load
        with patch('binding_sources.shortcut_sets.installed', return_value=True), patch('binding_sources.run', side_effect=FileNotFoundError), patch('binding_sources.shutil.which', return_value='/missing/harness'):
            for source in ('Tmux', 'Herdr'):
                rows, status = load(source)
                self.assertEqual(rows, [])
                self.assertIn('not installed', status)

    def test_tmux_modifiers_and_prefix(self):
        rows = tmux_records('bind-key -T prefix C-M-x split-window -h\nbind-key -T root S-Left resize-pane -L', 'C-Space')
        self.assertEqual(rows[0]['key'], 'CTRL ALT + X')
        self.assertEqual(rows[0]['display_key'], 'C-Space → CTRL ALT + X')
        self.assertEqual(rows[1]['key'], 'SHIFT + LEFT')
        self.assertFalse(rows[0]['dispatcher'])

    def test_config_prefix_is_context_not_modifier(self):
        rows = printed('Herdr', 'PREFIX → CTRL + SPACE\nPREFIX + SHIFT + N → New workspace\nCTRL + V → Paste')
        self.assertEqual(rows[0]['key'], 'SHIFT + N')
        self.assertIn('CTRL + SPACE', rows[0]['group'])
        self.assertEqual(rows[1]['group'], 'Direct')

    def test_resolved_overrides_and_unbound_actions(self):
        rows = resolved('Shefrd', {'result': {'entries': [
            dict(id='new_tab',label='New tab',context='prefix',keys=['prefix+ctrl+t']),
            dict(id='disabled',label='Disabled',context='direct',keys=[])]}})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['key'], 'CTRL + T')
        self.assertEqual(rows[0]['display_key'], 'prefix+ctrl+t')
        with self.assertRaises(ValueError):
            resolved('Shefrd', {'error': 'server unavailable'})

    def test_case_sensitive_tmux_keys(self):
        self.assertEqual(chord('X'), 'SHIFT + X')
        self.assertEqual(chord('x'), 'X')
