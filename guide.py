"""Backend and shell IPC for the bundled Keyboard Guide."""
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent / 'keyguide'


class GuideController:
    def backend(self, *args):
        env = dict(os.environ, PYTHONPATH=str(ROOT / 'src/backend'), PYTHONDONTWRITEBYTECODE='1')
        result = subprocess.run([sys.executable, '-m', 'keyguide_backend', *args],
                                env=env, capture_output=True, text=True, timeout=15)
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or 'Guide command failed')
        return json.loads(result.stdout)

    def read(self):
        return self.backend('settings', 'get')

    def patch(self, **values):
        settings = self.backend('settings', 'patch', json.dumps(values))
        # The FileView also reloads preferences; explicit refresh avoids watcher latency.
        self.ipc('keyguide', 'refresh')
        return settings

    def ipc(self, *args):
        result = subprocess.run(['omarchy-shell', *args], capture_output=True, text=True, timeout=8)
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or 'Guide service unavailable. Run make install and restart the Omarchy shell.')
        return result.stdout

    def status(self):
        settings = self.read()
        live = json.loads(self.ipc('keyguide', 'settings'))
        return settings, live

    def open_settings(self):
        self.ipc('shell', 'summon', 'mrai.keyguide')
