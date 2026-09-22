"""Read application keymaps without dispatching their actions."""
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess

import shortcut_sets

SOURCES = shortcut_sets.discover()

def refresh_registry():
    SOURCES[:] = shortcut_sets.discover()
    return SOURCES


def run(args):
    return subprocess.run(args, text=True, capture_output=True, check=True, timeout=8).stdout


def chord(value):
    value = value.strip()
    mods = []
    aliases = {'C': 'CTRL', 'M': 'ALT', 'S': 'SHIFT', 'ctrl': 'CTRL',
               'control': 'CTRL', 'alt': 'ALT', 'shift': 'SHIFT',
               'super': 'SUPER', 'cmd': 'SUPER', 'meta': 'SUPER'}
    # Both tmux C-M-x and explicit ctrl+alt+x syntax.
    while True:
        match = re.match(r'^(C|M|S)-(.+)$', value)
        if not match:
            match = re.match(r'^(ctrl|control|alt|shift|super|cmd|meta)\s*\+\s*(.+)$', value, re.I)
        if not match: break
        mods.append(aliases.get(match[1], aliases.get(match[1].lower(), match[1].upper())))
        value = match[2]
    if len(value) == 1 and value.isupper() and 'SHIFT' not in mods:
        mods.append('SHIFT')
    value = {'Space': 'SPACE', 'BSpace': 'BACKSPACE', 'BTab': 'TAB',
             'PPage': 'PRIOR', 'NPage': 'NEXT', 'DC': 'DELETE', 'IC': 'INSERT'}.get(value, value)
    return (' '.join(mods) + ' + ' if mods else '') + value.upper()


def record(source, context, key, label, identity=None, display=None):
    identity = identity or context + '\0' + key + '\0' + label
    return dict(id=hashlib.sha256((source+'\0'+identity).encode()).hexdigest()[:20],
                key=key, display_key=display or key, name=label, group=context,
                topic=source, source=source, kind='action', dispatcher='', arg='',
                app_icon='', type_icon='')


def printed(source, output):
    records = []
    prefix = ''
    for line in output.splitlines():
        if ' → ' not in line: continue
        key, label = (part.strip() for part in line.split(' → ', 1))
        if key == 'PREFIX':
            prefix = label
            continue
        context = 'Direct'
        stroke = key
        for marker in ('PREFIX', 'COPY MODE'):
            if key.startswith(marker + ' + '):
                context = marker.title() + (f' ({prefix})' if marker == 'PREFIX' else '')
                stroke = key[len(marker)+3:]
                break
        # Printed helpers uppercase plain letters, so preserve their explicit modifier notation.
        parts = stroke.split(' + ')
        normalized = (' '.join(parts[:-1]) + ' + ' if len(parts) > 1 else '') + parts[-1]
        records.append(record(source, context, normalized, label, display=key))
    return records


def tmux_records(output, prefix):
    records = []
    for line in output.splitlines():
        parts = shlex.split(line)
        if not parts or parts[0] != 'bind-key' or '-T' not in parts: continue
        index = parts.index('-T')
        table, key = parts[index+1:index+3]
        command = ' '.join(parts[index+3:])
        label = parts[parts.index('-N')+1] if '-N' in parts[:index] else command
        context = f'Prefix ({prefix})' if table == 'prefix' else table
        normalized = chord(key)
        display = f'{prefix} → {normalized}' if table == 'prefix' else normalized
        records.append(record('Tmux', context, normalized, label, display=display))
    return records


def resolved(source, payload):
    if 'error' in payload: raise ValueError(str(payload['error']))
    entries = payload.get('result', payload).get('entries')
    if not isinstance(entries, list): raise ValueError('No resolved keymap returned')
    rows = []
    for entry in entries:
        context = str(entry.get('context', 'direct'))
        for key in entry.get('keys', []):
            stroke = re.sub(r'^prefix\s*\+\s*', '', key, flags=re.I)
            rows.append(record(source, context, chord(stroke), entry.get('label', entry['id']),
                               identity=entry['id']+'\0'+context+'\0'+key, display=key))
    return rows


def load(source):
    if not shortcut_sets.installed(source):
        return [], f'{source} is not installed'
    if source in shortcut_sets.CATALOG:
        data = shortcut_sets.CATALOG[source]
        rows = [record(source, row.get('category', 'General'), row['keys'], row['title'],
                       identity=data['id']+'\0'+row['id']) for row in data['shortcuts']]
        return rows, 'Reference shortcuts · ' + data['description']
    if source == 'Tmux':
        try:
            prefix = run(['tmux', 'show-options', '-gv', 'prefix']).strip()
            return tmux_records(run(['tmux', 'list-keys']), prefix), 'Live tmux server · current socket'
        except subprocess.CalledProcessError:
            return printed(source, run(['omarchy', 'menu', 'tmux-keybindings', '--print'])), 'Tmux configuration · no live server'
    executable = os.environ.get(source.upper()+'_BIN') or shutil.which(source.lower())
    if not executable:
        return [], f'{source} is not installed or not on PATH'
    try:
        return resolved(source, json.loads(run([executable, 'keys', 'list', '--json']))), f'{source} live resolved keymap'
    except (subprocess.SubprocessError, ValueError):
        if source == 'Herdr':
            return printed(source, run(['omarchy', 'menu', 'herdr-keybindings', '--print'])), 'Herdr defaults + current config · live keymap unavailable in this version'
        return [], 'Shefrd live keymap unavailable · start its server, then Refresh'
