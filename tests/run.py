#!/usr/bin/env python3
"""Run GTK tests on a private Broadway display, never on the user's desktop."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

root = Path(__file__).resolve().parents[1]
daemon = shutil.which('gtk4-broadwayd')
if not daemon:
    sys.exit('GTK tests require gtk4-broadwayd (provided by GTK4). No desktop windows were opened.')
with tempfile.TemporaryDirectory(prefix='shortcuts-tests-') as temporary:
    display = 100 + os.getpid() % 30000
    env = dict(os.environ, GDK_BACKEND='broadway', BROADWAY_DISPLAY=f':{display}',
               GSK_RENDERER='cairo', PYTHONWARNINGS='ignore::DeprecationWarning')
    socket = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')) / f'broadway{display+1}.socket'
    visual = bool(os.environ.get('VISUAL_REVIEW_DIR') or os.environ.get('NATIVE_PHOTOS') or os.environ.get('BINDLUME_CHAOS_STEPS'))
    server = subprocess.Popen([daemon, '--unixsocket', temporary+'/http.socket', f':{display}'],
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + 5
        while not socket.exists():
            if server.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError('Private GTK display failed to start')
            time.sleep(.02)
        result = subprocess.run([sys.executable, str(root/'tests/strict_runner.py'), '-v', *sys.argv[1:]],
                                cwd=root, env=env, timeout=300 if visual else 180)
        sys.exit(result.returncode)
    finally:
        server.terminate()
        server.wait(timeout=5)
