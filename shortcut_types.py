"""Use the guide's presentation metadata without changing shortcut identities."""
from shortcut_data import canonical, split_shortcut

TYPES = {
    'action': ('Action', '󱐋'),
    'systemUi': ('System UI', '󰒓'),
    'desktopApp': ('Desktop App', '󰀻'),
    'webapp': ('Web App', '󰖟'),
    'cmd': ('Command', '󰆍'),
    'unknown': ('Other', '󰘥'),
}
FILTERS = [('all', 'All types')]
for kind, (name, glyph) in TYPES.items():
    if kind == 'desktopApp':
        FILTERS.append(('apps', '󰀻  Apps (desktop + web)'))
    FILTERS.append((kind, f'{glyph}  {name}'))



def annotate(records, presentations, show_actions=True):
    by_chord = {}
    for binding in presentations:
        chord = (frozenset(canonical(m) for m in binding.get('modifiers', [])), canonical(binding.get('key', '')))
        by_chord.setdefault(chord, []).append(binding)
    for record in records:
        candidates = by_chord.get(split_shortcut(record['key']), [])
        binding = next((b for b in candidates if str(b.get('description', b.get('title', ''))).casefold() == record['name'].casefold()), candidates[0] if candidates else {})
        kind = binding.get('displayKind', 'unknown')
        if kind == 'command':
            kind = 'cmd'
        if kind not in TYPES:
            kind = 'unknown'
        record['topic'] = record['group']
        record['kind'] = kind
        record['group'], glyph = TYPES[kind]
        record['app_icon'] = binding.get('icon', '') if kind in ('desktopApp', 'webapp') else ''
        record['type_icon'] = '' if kind == 'action' and not show_actions else glyph
    return records


def matches_type(record, selected):
    kind = record.get('kind', 'unknown')
    return selected == 'all' or (selected == 'apps' and kind in ('desktopApp', 'webapp')) or selected == kind


def load_presentations():
    import json
    from guide import GuideController
    controller = GuideController()
    try:
        return json.loads(controller.ipc('keyguide', 'presentations'))
    except (RuntimeError, ValueError, OSError):
        # The bundle can classify known actions even when its shell plugin is off.
        try:
            actions = controller.backend('shortcuts', 'status')['actions']
            icons = controller.backend('icons')
            for action in actions:
                action['icon'] = icons.get(action.get('targetId', ''), '')
            return {'bindings': actions, 'showActions': controller.read().get('showActionIndicators', True)}
        except (RuntimeError, ValueError, OSError, KeyError):
            return {'bindings': [], 'showActions': True}
