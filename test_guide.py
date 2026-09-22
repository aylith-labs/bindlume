import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import time
from unittest.mock import patch

import guide
import install


class GuideTests(unittest.TestCase):
    def test_preferences_persist_and_validate_without_desktop(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'XDG_DATA_HOME': tmp, 'XDG_CONFIG_HOME': tmp}):
            controller = guide.GuideController()
            self.assertFalse(controller.read()['enabled'])
            self.assertFalse(controller.read()['showSavedIndicators'])
            self.assertFalse(controller.read()['compactIcons'])
            with patch.object(controller, 'ipc') as ipc:
                controller.patch(showSavedIndicators=True, enabled=True, compactIcons=True, position='left', showDelayMs=500, fadeDurationMs=300, showActionIndicators=False)
                ipc.assert_called_with('keyguide', 'refresh')
            settings = guide.GuideController().read()
            self.assertTrue(settings['enabled'])
            self.assertTrue(settings['showSavedIndicators'])
            self.assertTrue(settings['compactIcons'])
            self.assertEqual(settings['position'], 'left')
            self.assertEqual(settings['showDelayMs'], 500)
            self.assertEqual(settings['fadeDurationMs'], 300)
            self.assertFalse(settings['showActionIndicators'])
            for value in [-1, 5001, True, 1.2]:
                with self.assertRaises(RuntimeError):
                    controller.backend('settings', 'patch', json.dumps({'showDelayMs':value}))
            for value in [-1, 2001, True]:
                with self.assertRaises(RuntimeError):
                    controller.backend('settings', 'patch', json.dumps({'fadeDurationMs':value}))
            with self.assertRaises(RuntimeError):
                controller.backend('settings', 'patch', '{"compactIcons":"yes"}')
            self.assertTrue(controller.read()['compactIcons'])

    def test_standalone_migration_preserves_backup_and_reinstalls(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            plugin = home / '.config/omarchy/plugins/mrai.keyguide'
            plugin.mkdir(parents=True)
            (plugin / 'manifest.json').write_text(json.dumps({'id': 'mrai.keyguide'}))
            (plugin / 'custom.txt').write_text('keep me')
            dest = install.configure(home)
            self.assertTrue(plugin.is_symlink())
            self.assertEqual(plugin.resolve(), dest / 'keyguide')
            backups = list((home / '.local/state/bindlume/keyguide-backups').iterdir())
            self.assertEqual((backups[0] / 'custom.txt').read_text(), 'keep me')
            install.configure(home)
            self.assertEqual(len(list(backups[0].parent.iterdir())), 1)
            install.configure(home, uninstall=True)
            self.assertFalse(plugin.is_symlink())
            self.assertTrue(backups[0].exists())

    def test_open_settings_goes_directly_to_full_guide(self):
        controller = guide.GuideController()
        with patch.object(controller, 'ipc') as ipc:
            controller.open_settings()
            ipc.assert_called_once_with('shell', 'summon', 'mrai.keyguide')
        self.assertFalse(hasattr(guide, 'GuideWindow'))

    def test_ipc_error_is_reported(self):
        result = subprocess.CompletedProcess([], 1, stdout='', stderr='shell unavailable')
        with patch('guide.subprocess.run', return_value=result):
            with self.assertRaisesRegex(RuntimeError, 'shell unavailable'):
                guide.GuideController().open_settings()


if __name__ == '__main__':
    unittest.main()
