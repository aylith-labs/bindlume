#!/usr/bin/python
"""Install a self-contained user copy and its Hyprland integration."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

SOURCE = Path(__file__).resolve().parent
FILES = ('docs/USER_GUIDE.md', 'LICENSE', 'CONTRIBUTING.md', 'branding/mark.svg', 'branding/README.md', 'FAST_CHAT.md', 'chat_api.py', 'source_cache.py', 'brand.py', 'input_controls.py', 'usage_view.py', 'overlay_surface.py', 'native_style.py', 'rich_content.py', 'companion.py', 'about.py', 'settings_ui.py', 'guide_settings.py', 'dialogs.py', 'agent_quota.py', 'agent_control.py', 'chat.py', 'chat_view.py', 'looks.json', 'localization.py', 'translations.json', 'preferences.py', 'global_shortcut.py', 'shortcut_sets.py', 'source_library.py', 'SHORTCUT_SETS.md', 'features.py', 'app.py', 'shortcut_data.py', 'keyboard_view.py', 'info_view.py',
         'binding_sources.py', 'shortcut_manager.py', 'theme.py', 'guide.py', 'shortcut_types.py', 'input_bridge.lua', 'windows.lua', 'README.md', 'RELEASE_READINESS.md', 'RESEARCH.md', 'install.py')
BEGIN = '-- BEGIN bindlume (managed by installer)'
END = '-- END bindlume'


# Legacy identifiers exist only here to migrate previous installations.
LEGACY = 'omarchy-shortcuts'
LEGACY_ID = 'local.omarchy.Shortcuts'


def migrate_legacy(home):
    """Move user data without overwriting anything; retire app-owned integration files."""
    pairs = [(home/base/LEGACY, home/base/'bindlume') for base in
             ('.config', '.local/state')]
    # Preflight every destination before moving any data.
    for old, new in pairs:
        if old.exists() and new.exists():
            raise RuntimeError(f'Migration needs review: both {old} and {new} exist; neither was changed.')
    for old, new in pairs:
        if old.exists():
            new.parent.mkdir(parents=True, exist_ok=True)
            old.rename(new)
    old_dest = home/'.local/share'/LEGACY
    for base in (home/'.agents/skills', home/'.codex/skills', home/'.claude/skills',
                 home/'.gemini/skills', home/'.config/opencode/skills'):
        for name in (LEGACY, 'shortcut-set-creator'):
            entry = base/name
            if entry.is_symlink() and entry.resolve().is_relative_to(old_dest):
                entry.unlink()
    plugin = home/'.config/omarchy/plugins/mrai.keyguide'
    if plugin.is_symlink() and plugin.resolve() == old_dest/'keyguide':
        plugin.unlink()
    # Keep the previous installation and launchers together as a rollback backup.
    old_cache, new_cache = home/'.cache'/LEGACY, home/'.cache/bindlume'
    if old_cache.exists() and not new_cache.exists():
        old_cache.rename(new_cache)
    artifacts = [old_cache, old_dest, home/'.local/bin'/LEGACY,
                 home/'.local/share/applications'/f'{LEGACY}.desktop',
                 home/'.config/autostart'/f'{LEGACY}.desktop',
                 home/'.local/share/icons/hicolor/scalable/apps'/f'{LEGACY_ID}.svg']
    backup = home/'.local/state/bindlume/migration-backups'/datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    for index, artifact in enumerate(artifacts):
        if artifact.exists() or artifact.is_symlink():
            backup.mkdir(parents=True, exist_ok=True)
            shutil.move(str(artifact), str(backup/f'{index}-{artifact.name}'))


def clean_bindings(text):
    text = re.sub(r'-- BEGIN ' + re.escape(LEGACY) + r' \(managed by installer\).*?-- END ' + re.escape(LEGACY) + r'\n?', '', text, flags=re.S)
    text = re.sub(re.escape(BEGIN) + r'.*?' + re.escape(END) + r'\n?', '', text, flags=re.S)
    lines = []
    for line in text.splitlines(keepends=True):
        # Migrate only this application's old one-line integrations.
        if (re.match(r'\s*o\.bind\(', line) and any(name in line for name in ('Omarchy Shortcuts', 'Bindlume'))
                and any(name in line for name in ('bindlume', LEGACY))):
            continue
        if (re.match(r'\s*dofile\(', line) and any(name + '/' in line for name in ('bindlume', LEGACY))
                and 'input_bridge.lua' in line):
            continue
        lines.append(line)
    return ''.join(lines)


def desktop_quote(value):
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%') + '"'


def install_guide(home, dest, uninstall=False):
    """Own only our symlink; preserve an existing standalone plugin in a backup."""
    plugin = home / '.config/omarchy/plugins/mrai.keyguide'
    target = dest / 'keyguide'
    managed = plugin.is_symlink() and plugin.resolve() == target.resolve()
    if uninstall:
        if managed:
            plugin.unlink()
        return
    source = SOURCE / 'keyguide'
    if source.resolve() != target.resolve():
        shutil.copytree(source, target, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'build'))
    if managed:
        return
    if plugin.exists() or plugin.is_symlink():
        manifest = json.loads((plugin / 'manifest.json').read_text())
        if manifest.get('id') != 'mrai.keyguide':
            raise RuntimeError(f'Refusing to replace unrelated plugin: {plugin}')
        backup = home / '.local/state/bindlume/keyguide-backups' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(plugin), str(backup))
        print(f'Backed up standalone Keyguide: {backup}')
    plugin.parent.mkdir(parents=True, exist_ok=True)
    plugin.symlink_to(target, target_is_directory=True)


def install_agent_skills(home, dest):
    """Install app-owned skills for agents without replacing unrelated user skills."""
    for name in ('bindlume', 'shortcut-set-creator'):
        source = SOURCE / 'skills' / name
        target = dest / 'skills' / name
        shutil.copytree(source, target, dirs_exist_ok=True)
        for base in (home/'.agents/skills', home/'.codex/skills', home/'.claude/skills',
                     home/'.gemini/skills', home/'.config/opencode/skills'):
            entry = base/name
            if entry.exists() or entry.is_symlink():
                # Existing independent skills belong to the user.
                continue
            base.mkdir(parents=True, exist_ok=True)
            entry.symlink_to(target, target_is_directory=True)


def configure(home, uninstall=False):
    if not uninstall:
        migrate_legacy(home)
    dest = home / '.local/share/bindlume'
    launcher = home / '.local/bin/bindlume'
    desktop = home / '.local/share/applications/bindlume.desktop'
    bindings = home / '.config/hypr/bindings.lua'
    original = bindings.read_text() if bindings.exists() else ''
    updated = clean_bindings(original)
    if not uninstall:
        for name in FILES:
            if not (SOURCE / name).is_file():
                raise FileNotFoundError(SOURCE / name)
        dest.mkdir(parents=True, exist_ok=True)
        for name in FILES:
            source, target = SOURCE / name, dest / name
            if source.resolve() != target.resolve():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        if (SOURCE / 'bundled-shortcut-sets').resolve() != (dest / 'bundled-shortcut-sets').resolve():
            shutil.copytree(SOURCE / 'bundled-shortcut-sets', dest / 'bundled-shortcut-sets', dirs_exist_ok=True)
        try:
            revision = subprocess.check_output(['git','rev-parse','--short','HEAD'],cwd=SOURCE,text=True).strip()
            if subprocess.check_output(['git','status','--porcelain'],cwd=SOURCE,text=True).strip(): revision += ' + local changes'
        except (OSError, subprocess.CalledProcessError): revision = 'Local build'
        (dest/'build-info.json').write_text(json.dumps(dict(version='Development', revision=revision,
            built_at=datetime.now().astimezone().isoformat(timespec='seconds'), homepage=__import__('brand').HOMEPAGE),indent=2)+'\n')
        install_guide(home, dest)
        install_agent_skills(home, dest)
        launcher.parent.mkdir(parents=True, exist_ok=True)
        launcher.write_text('#!/bin/sh\nif [ "$1" = "ctl" ]; then\n  shift\n  exec /usr/bin/python ' + shlex.quote(str(dest / 'agent_control.py')) + ' "$@"\nfi\nif [ "$#" -eq 0 ]; then\n  if gdbus call --session --timeout 1 --dest com.aylith.Bindlume --object-path /com/aylith/Bindlume --method org.freedesktop.Application.Activate \'{}\' >/dev/null 2>&1; then\n    exit 0\n  fi\nfi\n' + 'exec /usr/bin/python ' + shlex.quote(str(dest / 'app.py')) + ' "$@"\n')
        launcher.chmod(0o755)
        autostart = home / '.config/autostart/bindlume.desktop'
        autostart.parent.mkdir(parents=True, exist_ok=True)
        autostart.write_text('[Desktop Entry]\nType=Application\nName=Bindlume background\nExec=' + desktop_quote(launcher) + ' --background\nNoDisplay=true\n')

        icon = home / '.local/share/icons/hicolor/scalable/apps/com.aylith.Bindlume.svg'
        icon.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dest / 'branding/mark.svg', icon)
        desktop.parent.mkdir(parents=True, exist_ok=True)
        desktop.write_text('[Desktop Entry]\nType=Application\nName=Bindlume\n'
                           'Comment=Bindlume — illuminating your bindings\n'
                           f'Exec={desktop_quote(launcher)}\n'
                           'Icon=com.aylith.Bindlume\nTerminal=false\n'
                           'Categories=Utility;\nStartupWMClass=com.aylith.Bindlume\n')
        from global_shortcut import lines, DEFAULT
        try:
            hotkey = json.loads((home / '.config/bindlume/ui-state.json').read_text()).get('preferences', {}).get('global_hotkey', DEFAULT)
        except (OSError, ValueError): hotkey = DEFAULT
        updated = updated.rstrip() + '\n\n' + '\n'.join((
            BEGIN,
            *lines(home, hotkey),
            'dofile(' + json.dumps(str(dest / 'input_bridge.lua')) + ')',
            'dofile(' + json.dumps(str(dest / 'windows.lua')) + ')',
            'hl.unbind("SUPER + CTRL + SHIFT + K")',
            'o.bind("SUPER + CTRL + SHIFT + K", "Toggle Global Shortcut Guide", "omarchy-shell keyguide toggleGlobal")',
            END, ''))
    if updated != original:
        bindings.parent.mkdir(parents=True, exist_ok=True)
        if bindings.exists():
            backup = bindings.with_name(bindings.name + '.bak.' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
            shutil.copy2(bindings, backup)
            print(f'Backed up bindings: {backup}')
        bindings.write_text(updated)
    if uninstall:
        for name in ('bindlume', 'shortcut-set-creator'):
            for base in (home/'.agents/skills', home/'.codex/skills', home/'.claude/skills', home/'.gemini/skills', home/'.config/opencode/skills'):
                entry = base/name
                if entry.is_symlink() and entry.resolve() == (dest/'skills'/name).resolve(): entry.unlink()
        install_guide(home, dest, uninstall=True)
        (home / '.config/autostart/bindlume.desktop').unlink(missing_ok=True)
        launcher.unlink(missing_ok=True)
        desktop.unlink(missing_ok=True)
        (home / '.local/share/icons/hicolor/scalable/apps/com.aylith.Bindlume.svg').unlink(missing_ok=True)
        if dest.exists():
            shutil.rmtree(dest)
    return dest


def reload_hyprland():
    subprocess.run(['hyprctl', 'reload'], check=True)
    result = subprocess.run(['hyprctl', 'configerrors'], check=True, capture_output=True, text=True)
    if result.stdout.strip():
        raise RuntimeError('Hyprland configuration errors:\n' + result.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['install', 'uninstall'])
    parser.add_argument('--home', type=Path, default=Path.home(), help='Target home (also useful for isolated tests)')
    parser.add_argument('--no-reload', action='store_true', help='Skip live Hyprland reload')
    args = parser.parse_args()
    home = args.home.expanduser().resolve()
    if home != Path.home().resolve() and not args.no_reload:
        parser.error('An alternate --home requires --no-reload')
    if args.action == 'uninstall' and not args.no_reload:
        plugin = home / '.config/omarchy/plugins/mrai.keyguide'
        if plugin.is_symlink() and plugin.resolve() == home / '.local/share/bindlume/keyguide':
            subprocess.run(['omarchy', 'plugin', 'disable', 'mrai.keyguide'], check=True)
    dest = configure(home, uninstall=args.action == 'uninstall')
    if not args.no_reload:
        reload_hyprland()
        if args.action == 'install':
            subprocess.run(['omarchy', 'plugin', 'enable', 'mrai.keyguide'], check=True)
        subprocess.run(['omarchy', 'restart', 'shell'], check=True)
    print(f'{args.action.capitalize()} complete: {dest}; user preferences preserved.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f'Installation operation failed: {error}', file=sys.stderr)
        sys.exit(1)
