import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import global_shortcut
import install
from guide import GuideController

class PreferencesTests(unittest.TestCase):
    def test_global_hotkey_default_and_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            install.configure(root)
            text = (root / '.config/hypr/bindings.lua').read_text()
            self.assertNotIn('hl.unbind("SUPER + K")', text)
            self.assertIn('o.bind("SUPER + SHIFT + K"', text)
        self.assertEqual(global_shortcut.normalize('Win+K'), 'SUPER + K')
        for key in ('K', 'SHIFT + K', 'SUPER + $(bad)', 'SUPER + CTRL + SHIFT + K'):
            with self.assertRaises(ValueError): global_shortcut.normalize(key)

    def test_failed_hotkey_reload_restores_config(self):
        import subprocess
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            install.configure(root)
            path = root / '.config/hypr/bindings.lua'
            original = path.read_text()
            success = subprocess.CompletedProcess([], 0, stdout='', stderr='')
            errors = subprocess.CompletedProcess([], 0, stdout='configuration error', stderr='')
            with patch('global_shortcut.shutil.which', return_value='/usr/bin/hyprctl'), patch(
                    'global_shortcut.subprocess.run', side_effect=[success, errors, success]):
                with self.assertRaisesRegex(RuntimeError, 'restored'):
                    global_shortcut.apply('Win+K', root)
            self.assertEqual(path.read_text(), original)

    def test_guide_settings_migrate_once_and_independent_controls(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'XDG_DATA_HOME': folder+'/data', 'XDG_CONFIG_HOME': folder+'/config'}):
            legacy = Path(folder)/'data/omarchy-keyguide/settings.json'
            legacy.parent.mkdir(parents=True)
            controller = GuideController()
            values = controller.read()
            values.update(position='right', compactIcons=True)
            for key in ('compactView','badgeMode'): values.pop(key)
            legacy.write_text(json.dumps(values))
            modern = Path(folder)/'config/bindlume/keyboard-guide.json'
            modern.unlink(missing_ok=True)
            migrated = controller.read()
            self.assertEqual(migrated['position'], 'right')
            self.assertTrue(migrated['compactView'])
            self.assertEqual(migrated['badgeMode'], 'icons')
            self.assertTrue(legacy.exists())
            self.assertTrue(modern.exists())
            with patch.object(controller, 'ipc'):
                controller.patch(compactView=False, badgeMode='none', showIcons=False,
                                 showAppIcons=True, showHiddenItems=True, language='hu')
            restored = controller.read()
            self.assertFalse(restored['compactView'])
            self.assertEqual(restored['badgeMode'], 'none')
            self.assertTrue(restored['showAppIcons'])
            self.assertTrue(restored['showHiddenItems'])
            self.assertEqual(restored['language'], 'hu')

class SystemLanguageTests(unittest.TestCase):
    def test_locale_detection_and_fallback(self):
        import localization, os
        from unittest.mock import patch
        for env,expected in [({'LANG':'hu_HU.UTF-8'},'hu'),({'LANG':'de_DE.UTF-8','LC_MESSAGES':'fr_FR.UTF-8'},'fr'),({'LANG':'hu_HU.UTF-8','LC_ALL':'C'},'en'),({'LANG':'en_US.UTF-8','LANGUAGE':'ja:en'},'ja'),({'LANG':'xx_YY.UTF-8'},'en'),({'LANG':'zh-CN.UTF-8'},'zh_CN')]:
            with patch.dict(os.environ,env,clear=True), patch.object(localization.locale,'getlocale',return_value=(None,None)):
                self.assertEqual(localization.resolve_language('system'), expected)
                self.assertEqual(localization.resolve_language('de'), 'de')
        self.assertEqual(__import__('preferences').DEFAULTS['language'],'system')
