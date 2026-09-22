import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import install


class InstallTests(unittest.TestCase):
    def test_install_update_uninstall_preserve_user_config_and_state(self):
        with tempfile.TemporaryDirectory(prefix='shortcuts test ') as tmp:
            home = Path(tmp)
            bindings = home / '.config/hypr/bindings.lua'
            bindings.parent.mkdir(parents=True)
            unrelated = 'o.bind("SUPER + B", "Browser", "browser")\n'
            bindings.write_text(unrelated +
                'o.bind("SUPER + SHIFT + K", "Omarchy Shortcuts", "python /old/bindlume/app.py")\n'
                'dofile("/old/bindlume/input_bridge.lua")\n')
            state = home / '.config/bindlume/favorites.json'
            state.parent.mkdir(parents=True)
            state.write_text('["keep"]')
            dest = install.configure(home)
            text = bindings.read_text()
            self.assertIn(unrelated, text)
            self.assertNotIn('/old/', text)
            self.assertEqual(text.count(install.BEGIN), 1)
            self.assertIn('hl.unbind("SUPER + SHIFT + K")', text)
            self.assertTrue(list(bindings.parent.glob('bindings.lua.bak.*')))
            launcher = home / '.local/bin/bindlume'
            self.assertTrue(launcher.stat().st_mode & 0o111)
            self.assertNotIn(str(install.SOURCE), launcher.read_text())
            self.assertNotIn(str(install.SOURCE), text)
            for name in install.FILES:
                self.assertFalse((dest / name).is_symlink())
            # A separate process successfully imports installed modules from an unrelated cwd.
            subprocess.run(['/usr/bin/python', '-c',
                'import sys; sys.path.insert(0, sys.argv[1]); import app; print(app.PROJECT)', str(dest)],
                cwd='/', check=True, capture_output=True)
            (dest / 'README.md').write_text('outdated')
            install.configure(home)
            self.assertEqual(bindings.read_text(), text)
            self.assertEqual((dest / 'README.md').read_text(), (install.SOURCE / 'README.md').read_text())
            # Uninstallation still works using the installed helper with the checkout absent from its imports.
            subprocess.run(['/usr/bin/python', str(dest / 'install.py'), 'uninstall',
                            '--home', str(home), '--no-reload'], cwd='/', check=True, capture_output=True)
            self.assertFalse(dest.exists())
            self.assertFalse(launcher.exists())
            self.assertFalse((home / '.local/share/applications/bindlume.desktop').exists())
            self.assertIn(unrelated, bindings.read_text())
            self.assertNotIn(install.BEGIN, bindings.read_text())
            self.assertEqual(state.read_text(), '["keep"]')
            install.configure(home, uninstall=True)

    def test_legacy_migration_preserves_data_and_replaces_integration(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            old = home/'.config'/install.LEGACY
            old.mkdir(parents=True)
            (old/'favorites.json').write_text('["saved"]')
            (old/'conversations').mkdir()
            (old/'conversations/chat.json').write_text('{"messages": ["hello"]}')
            bindings = home/'.config/hypr/bindings.lua'
            bindings.parent.mkdir(parents=True)
            bindings.write_text('-- BEGIN '+install.LEGACY+' (managed by installer)\nold command\n-- END '+install.LEGACY+'\n')
            install.configure(home)
            new = home/'.config/bindlume'
            self.assertFalse(old.exists())
            self.assertEqual((new/'favorites.json').read_text(), '["saved"]')
            self.assertEqual((new/'conversations/chat.json').read_text(), '{"messages": ["hello"]}')
            self.assertNotIn('old command', bindings.read_text())
            self.assertNotIn(install.LEGACY, bindings.read_text())
            install.configure(home)
            self.assertEqual((new/'favorites.json').read_text(), '["saved"]')

    def test_migration_refuses_conflicting_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            for name in (install.LEGACY, 'bindlume'):
                folder = home/'.config'/name
                folder.mkdir(parents=True)
                (folder/'favorites.json').write_text(name)
            with self.assertRaisesRegex(RuntimeError, 'neither was changed'):
                install.configure(home)
            for name in (install.LEGACY, 'bindlume'):
                self.assertEqual((home/'.config'/name/'favorites.json').read_text(), name)

    def test_reload_reports_config_errors(self):
        with patch('install.subprocess.run', side_effect=[
            subprocess.CompletedProcess([], 0),
            subprocess.CompletedProcess([], 0, stdout='broken config')]):
            with self.assertRaisesRegex(RuntimeError, 'broken config'):
                install.reload_hyprland()

    def test_desktop_path_escaping(self):
        self.assertEqual(install.desktop_quote('/home/a b/100%'), '"/home/a b/100%%"')


if __name__ == '__main__':
    unittest.main()
