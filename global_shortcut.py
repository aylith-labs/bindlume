"""Own only the browser's marked Hyprland binding block."""
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess

DEFAULT = 'SUPER + SHIFT + K'

def normalize(text):
    parts = [part.strip().upper() for part in text.split('+')]
    aliases = {'WIN':'SUPER', 'META':'SUPER', 'CONTROL':'CTRL'}
    parts = [aliases.get(part, part) for part in parts]
    if len(parts) < 2 or len(set(parts)) != len(parts) or any(part not in ('SUPER','CTRL','ALT','SHIFT') for part in parts[:-1]):
        raise ValueError('Use modifiers and one key, for example SUPER + SHIFT + K.')
    if not re.fullmatch(r'[A-Z0-9]|F(?:[1-9]|1[0-2])|SPACE|RETURN', parts[-1]):
        raise ValueError('Choose a letter, digit, F1–F12, Space, or Return.')
    if not any(part in ('SUPER','CTRL','ALT') for part in parts[:-1]):
        raise ValueError('Include Win, Ctrl, or Alt.')
    if set(parts) == {'SUPER','CTRL','SHIFT','K'}:
        raise ValueError('Win+Ctrl+Shift+K is reserved for the global keyboard guide.')
    return ' + '.join([part for part in ('SUPER','CTRL','SHIFT','ALT') if part in parts[:-1]] + [parts[-1]])

def lines(home, hotkey=DEFAULT):
    hotkey = normalize(hotkey)
    launcher = home / '.local/bin/bindlume'
    return ['hl.unbind(' + json.dumps(hotkey) + ')',
            'o.bind(' + json.dumps(hotkey) + ', "Bindlume", ' + json.dumps(shlex.quote(str(launcher))) + ')']

def apply(text, home=None):
    hotkey = normalize(text)
    home = home or Path.home()
    path = home / '.config/hypr/bindings.lua'
    if not path.exists() or not shutil.which('hyprctl'):
        raise RuntimeError('Global shortcut configuration is currently available on Hyprland.')
    import install
    original = path.read_text()
    start, end = original.find(install.BEGIN), original.find(install.END)
    if start < 0 or end < start:
        raise RuntimeError('Install the app before changing its global shortcut.')
    block = original[start:end].splitlines()
    kept = [line for line in block if not ('hl.unbind(' in line or '"Omarchy Shortcuts"' in line or '"Bindlume"' in line)]
    # Preserve the separate global guide binding.
    kept.insert(1, 'hl.unbind("SUPER + CTRL + SHIFT + K")')
    updated = original[:start] + '\n'.join([kept[0], *lines(home, hotkey), *kept[1:]]) + '\n' + original[end:]
    backup = path.with_name(path.name + '.shortcuts-backup')
    backup.write_text(original)
    path.write_text(updated)
    try:
        subprocess.run(['hyprctl','reload'], capture_output=True, timeout=3, check=True)
        result = subprocess.run(['hyprctl','configerrors'], capture_output=True, text=True, timeout=3, check=True)
        if result.stdout.strip():
            raise RuntimeError(result.stdout.strip())
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        path.write_text(original)
        try:
            subprocess.run(['hyprctl','reload'], capture_output=True, timeout=3)
        except (OSError, subprocess.SubprocessError):
            pass
        raise RuntimeError('Could not apply the shortcut; restored the previous configuration. ' + str(error)) from error
    return hotkey
