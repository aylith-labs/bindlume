"""Versioned, data-only shortcut-set plugins. No plugin code is executed."""
import json
import os
from pathlib import Path
import re
import shutil
import sys

BUILTIN = Path(__file__).with_name('bundled-shortcut-sets')
LIVE = {'Omarchy': ('omarchy', 'hyprctl'), 'Tmux': ('tmux',),
        'Herdr': ('herdr',), 'Shefrd': ('shefrd',)}
CATALOG = {}
ERRORS = []
# Stable IDs in plugins; source labels are translated by the UI.
CATEGORIES = {'browsers':'Browsers', 'desktop':'Desktop', 'terminals':'Terminals',
              'development':'Development', 'personal':'Personal'}
LIVE_CATEGORIES = {'Omarchy':'desktop','Tmux':'terminals','Herdr':'development','Shefrd':'development'}

def category(name):
    return LIVE_CATEGORIES.get(name, CATALOG.get(name, {}).get('category', 'personal'))


def user_directory():
    return Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'bindlume/shortcut-sets'


def validate(data):
    if not isinstance(data, dict) or (type(data.get('version')) is not int or data['version'] != 1):
        raise ValueError('Expected shortcut-set version 1')
    if set(data) - {'version','id','name','description','detect','platforms','shortcuts','documentation','category'}:
        raise ValueError('Unknown shortcut-set field')
    if not re.fullmatch(r'[a-z0-9][a-z0-9.-]{0,63}', str(data.get('id', ''))):
        raise ValueError('id must use lowercase letters, digits, dots or hyphens')
    for field in ('name', 'description'):
        if not isinstance(data.get(field), str) or not data[field].strip():
            raise ValueError(f'{field} is required')
    if data['name'] in LIVE: raise ValueError('Name is reserved for a live integration')
    if 'category' in data and data['category'] not in CATEGORIES: raise ValueError('Unknown set category')
    detect = data.get('detect', {})
    if not isinstance(detect, dict) or set(detect) - {'executables', 'desktop_ids'}:
        raise ValueError('detect supports executables and desktop_ids')
    for field, values in detect.items():
        if not isinstance(values, list) or any(not isinstance(v,str) or not v or '/' in v or '\\' in v for v in values):
            raise ValueError(f'detect.{field} must contain names, not paths')
    platforms = data.get('platforms', ['linux'])
    if not isinstance(platforms,list) or not platforms or any(p not in ('linux','win32','darwin') for p in platforms):
        raise ValueError('platforms must contain linux, win32 or darwin')
    rows = data.get('shortcuts')
    if not isinstance(rows, list) or not rows or len(rows) > 10000:
        raise ValueError('shortcuts must contain between 1 and 10000 entries')
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) - {'id','keys','title','category'}:
            raise ValueError('Each shortcut supports id, keys, title and category only')
        for field in ('id','keys','title'):
            if not isinstance(row.get(field),str) or not row[field].strip():
                raise ValueError(f'Shortcut {field} is required')
        if not re.fullmatch(r'(?:(?:SUPER|CTRL|ALT|SHIFT)(?: (?:SUPER|CTRL|ALT|SHIFT))* \+ )?\S+', row['keys']):
            raise ValueError('keys must use canonical notation, e.g. CTRL SHIFT + T')
        if row['id'] in seen: raise ValueError('Duplicate shortcut id: '+row['id'])
        seen.add(row['id'])
        if 'category' in row and not isinstance(row['category'],str): raise ValueError('category must be text')
    return data


def read(path):
    if path.stat().st_size > 2_000_000: raise ValueError('Shortcut set exceeds 2 MB')
    return validate(json.loads(path.read_text()))


def discover():
    catalog, errors, ids = {}, [], set()
    for directory in (BUILTIN, user_directory()):
        for path in sorted(directory.glob('*.json')):
            try:
                data = read(path)
                if data['id'] in ids or data['name'] in catalog:
                    raise ValueError('Duplicate set id or name')
                ids.add(data['id'])
                catalog[data['name']] = data
            except (ValueError, OSError) as error:
                errors.append(f'{path.name}: {error}')
    CATALOG.clear(); CATALOG.update(catalog)
    ERRORS[:] = errors
    return list(LIVE) + list(CATALOG)


def custom_file(name):
    expected=CATALOG.get(name)
    if not expected:return None
    for path in user_directory().glob('*.json'):
        try:
            if not path.is_symlink() and read(path)==expected:return path
        except (OSError,ValueError):continue
    return None


def remove_custom(name, expected_bytes):
    from localization import text as tr
    path=custom_file(name)
    if path is None:raise ValueError(tr('Custom shortcut set is no longer available.'))
    if path.read_bytes()!=expected_bytes:raise ValueError(tr('This set changed. Reopen the removal preview.'))
    from gi.repository import Gio
    Gio.File.new_for_path(str(path)).trash(None)


def installed(name):
    if name in LIVE:
        return all(shutil.which(os.environ.get(command.upper()+'_BIN', command)) for command in LIVE[name])
    data = CATALOG.get(name)
    if not data or sys.platform not in data.get('platforms', ['linux']): return False
    if 'category' in data and data['category'] not in CATEGORIES: raise ValueError('Unknown set category')
    detect = data.get('detect', {})
    commands, desktops = detect.get('executables', []), detect.get('desktop_ids', [])
    if not commands and not desktops: return True  # Personal/reference set.
    if any(shutil.which(command) for command in commands): return True
    roots = [Path(os.environ.get('XDG_DATA_HOME') or Path.home()/'.local/share')]
    roots += [Path(p) for p in os.environ.get('XDG_DATA_DIRS', '/usr/local/share:/usr/share').split(':') if p]
    return any((root/'applications'/desktop).is_file() for root in roots for desktop in desktops)


def install_file(path):
    data = read(Path(path))
    if data['id'] in {p['id'] for p in CATALOG.values()} or data['name'] in CATALOG:
        raise ValueError('This set already exists. Edit its file to update it.')
    directory = user_directory(); directory.mkdir(parents=True, exist_ok=True)
    target = directory/(data['id']+'.json')
    with target.open('x') as file: json.dump(data,file,indent=2); file.write('\n')
    return target


def create_template():
    directory = user_directory(); directory.mkdir(parents=True, exist_ok=True)
    index=1
    while (directory/f'my-shortcuts-{index}.json').exists(): index+=1
    data = dict(version=1, id=f'my-shortcuts-{index}', name=f'My shortcuts {index}', category='personal',
                description='Personal shortcut reference. Edit this JSON file to add your shortcuts.',
                shortcuts=[dict(id='find', keys='CTRL + F', title='Find', category='Navigation')])
    return install_file_data(directory, data)


def install_file_data(directory, data):
    target=directory/(data['id']+'.json')
    with target.open('x') as file: json.dump(data,file,indent=2); file.write('\n')
    return target


if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser(description='Validate or import a shortcut-set JSON plugin')
    parser.add_argument('file', type=Path)
    parser.add_argument('--install', action='store_true')
    args=parser.parse_args()
    discover()
    try:
        data=read(args.file)
        print(install_file(args.file) if args.install else f"Valid: {data['name']} ({len(data['shortcuts'])} shortcuts)")
    except (ValueError,OSError) as error: parser.exit(1,str(error)+'\n')
