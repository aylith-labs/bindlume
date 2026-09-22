"""Agent-facing CLI, local D-Bus API, and stdio MCP adapter.

All mutations go through the running app, so agents never race its state files.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

BUS = 'com.aylith.Bindlume'
OBJECT = '/com/aylith/Bindlume/Control'
INTERFACE = BUS + '.Control'
OPERATIONS = ['schema', 'quota', 'state', 'search', 'bookmark', 'hide', 'features', 'settings',
              'sources', 'view', 'guide', 'reset', 'sessions', 'companion', 'inputs', 'open']
HELP = {
    'open': 'surface: settings/features/shortcuts/sets/about/details/guide/inputs/chat. Opens the named app surface and enables its required feature.',
    'inputs': 'Read detected input devices and bindings. Optional gestures (up/down/left/right -> action), buttons (0..7 -> action), controller boolean, device (exact returned joystick path). Actions: none/search/chat/clear/shortcuts. Enables input features on mutation. Actions are scoped to Bindlume, not desktop-wide.',
    'companion': 'Read companion preferences and explicitly saved memory. action=remember with text saves an explicitly requested memory bullet when enabled; action=forget with text removes one. action=preferences with vignette boolean changes the persistent keyboard vignette. Memory is opt-in; never save inferred facts.',
    'quota': 'Read cached provider quota. refresh=true fetches current subscription usage without starting a model turn.',
    'state': 'Read current features, preferences, filters, marks and paths.',
    'search': 'query (text, optional), source (optional; searches installed sources by default). Returns stable IDs, names, keys, saved marks. Search before changing a shortcut.',
    'bookmark': 'id (exact shortcut ID), enabled (boolean). Idempotent bookmark/unbookmark. Remember a shortcut means bookmark it.',
    'hide': 'id (exact shortcut ID), enabled (boolean). Idempotent hide/unhide. Hiding enables the feature and excludes hidden entries from the current list.',
    'features': 'name (feature key or all), enabled (boolean). Omit both to list feature descriptions and states.',
    'settings': 'key and value to set one validated preference; omit to list current values. Global hotkey changes desktop bindings.',
    'sources': 'name and enabled to include/exclude a shortcut set; omit to list sets.',
    'view': 'Optional source, search, modifiers (array of SUPER/CTRL/ALT/SHIFT), all_layers, live, target (current or exact window address), type (all/action/systemUi/apps/desktopApp/webapp/cmd/unknown), show_filters, favorites_only, visibility (all/hidden/visible), layout (list/keyboard), flat_list, columns, look, feature_view (grid/previews/descriptions booleans). Required features are enabled automatically; type filtering also shows the filters. Changes return enabled_features and matching results.',
    'guide': 'values (object) to update guide settings; omit to read. Uses the guide settings validator.',
    'reset': 'Read a preview with no arguments. apply=true resets categories (array of returned category IDs), or all available categories when omitted. Chats and desktop bindings are retained.',
    'sessions': 'List saved chat metadata; optionally id to read a transcript, or id and title to rename.',
}


def execute(app, request):
    import preferences
    import shortcut_sets
    from features import FEATURES
    from app import STATE, UI_STATE, LEARNED_STATE, SOURCES, load_source, records, save_json
    op = request.get('operation')
    args = request.get('arguments') or {}
    if op not in OPERATIONS or not isinstance(args, dict): raise ValueError('Use a documented operation and an arguments object.')
    def boolean(value):
        if not isinstance(value, bool): raise ValueError('enabled must be a boolean')
        return value
    def source_items(source):
        if source not in SOURCES: raise ValueError('Unknown source')
        if source == app.source_name and app.items: return app.items
        return records() if source == 'Omarchy' else load_source(source)[0]
    def shortcut(identity):
        for source in [app.source_name] + [name for name in SOURCES if name != app.source_name and shortcut_sets.installed(name)]:
            item = next((item for item in source_items(source) if item['id'] == identity), None)
            if item: return item
        raise ValueError('Shortcut not found. Search first and use its exact ID.')
    if op == 'schema': return {'version': 2, 'operations': HELP, 'settings_defaults': preferences.DEFAULTS, 'shortcut_types': dict(__import__('shortcut_types').FILTERS), 'feature_ids': list(FEATURES), 'set_categories': shortcut_sets.CATEGORIES}
    if op == 'quota':
        from agent_quota import read_quotas
        from chat import available_agents
        return read_quotas(available_agents(app.preferences),UI_STATE.parent,force=args.get('refresh') is True)
    if op == 'state':
        return dict(features=app.features, preferences=app.preferences, source=app.source_name,
                    targets=[dict(address=r['address'],title=r.get('title','')) for r in app.targets], look=app.look, resolved_look=__import__('theme').resolve_look(app.look if app.feature_enabled('appearance') else 'system'), feature_view=app.feature_view,
                    bookmarks=sorted(app.favorites), hidden=sorted(app.learned), filters=app.saved_filters,
                    config_directory=str(UI_STATE.parent), loading=bool(getattr(app, 'refresh_busy', False)))
    if op == 'search':
        sources = [args['source']] if args.get('source') else [app.source_name] + [name for name in SOURCES if name != app.source_name and shortcut_sets.installed(name)]
        query = str(args.get('query', '')).casefold()
        return [dict(id=r['id'], title=r['name'], keys=r['key'], source=source,
                     bookmarked=r['id'] in app.favorites, hidden=r['id'] in app.learned)
                for source in sources for r in source_items(source)
                if query in (r['name']+' '+r['key']).casefold()]
    if op in ('bookmark', 'hide'):
        identity, enabled = args.get('id'), boolean(args.get('enabled'))
        item = shortcut(identity)
        marks, path, feature = (app.favorites, STATE, 'bookmarks') if op == 'bookmark' else (app.learned, LEARNED_STATE, 'hidden')
        if enabled: marks.add(identity)
        else: marks.discard(identity)
        save_json(path, sorted(marks))
        if enabled and not app.feature_enabled(feature): app.set_feature(feature, True)
        if op == 'hide' and enabled: app.learned_filter.set_selected(2)
        app.refresh_marks(item)
        app.render()
        return dict(id=identity, enabled=identity in marks)
    if op == 'features':
        if 'name' in args:
            name, enabled = args['name'], boolean(args.get('enabled'))
            names = list(FEATURES) if name == 'all' else [name]
            if any(name not in FEATURES for name in names): raise ValueError('Unknown feature')
            for name in names: app.features[name] = enabled
            if 'guide' in names: app.sync_guide_feature(enabled)
            app.apply_features()
            app.save_ui_state()
            if getattr(app, 'features_window', None): app.features_window.close()
        return {key: dict(title=value[0], description=value[1], enabled=app.feature_enabled(key)) for key,value in FEATURES.items()}
    if op == 'companion':
        from companion import read_memory, write_memory
        action=args.get('action','read')
        if action in ('remember','forget'):
            if not app.preferences['chat_memory_enabled']: raise ValueError('Memory is disabled. Enable Remember my preferences in AI companion settings first.')
            value=args.get('text')
            if not isinstance(value,str) or not value.strip():raise ValueError('Memory text is required')
            memory=read_memory(UI_STATE.parent)
            if action=='remember':memory.append(value)
            else:memory=[v for v in memory if v!=value]
            write_memory(UI_STATE.parent,memory)
        elif action=='preferences':
            if 'vignette' in args:app.set_preference('chat_vignette',boolean(args['vignette']))
        elif action!='read':raise ValueError('Unknown companion action')
        return dict(preferences={k:v for k,v in app.preferences.items() if k.startswith('chat_')},
                    memory=read_memory(UI_STATE.parent) if app.preferences['chat_memory_enabled'] else [])
    if op == 'settings':
        if 'key' in args:
            key, value = args['key'], args.get('value')
            if key not in preferences.DEFAULTS: raise ValueError('Unknown setting')
            default = preferences.DEFAULTS[key]
            if type(value) is not type(default): raise ValueError('Incorrect setting value type')
            choices = {'language': [lang for lang,_ in preferences.LANGUAGES], 'theme':['system','dark','light'],
                       'window_animations':['system','on','off'], 'app_animations':['system','on','off']}
            if key in choices and value not in choices[key]: raise ValueError('Unsupported setting value')
            if key == 'tooltip_delay' and not 0 <= value <= 5000: raise ValueError('Tooltip delay must be between 0 and 5000 milliseconds')
            if key == 'font_size' and not 9 <= value <= 28: raise ValueError('Font size must be between 9 and 28')
            if key == 'chat_instructions' and len(value) > 16000: raise ValueError('Custom instructions must be at most 16000 characters')
            if isinstance(value, str) and key != 'chat_instructions' and (not value.strip() or len(value) > 200): raise ValueError('Invalid setting text')
            if key == 'agent_provider':
                from chat import PROVIDERS
                if value != 'auto' and value not in PROVIDERS: raise ValueError('Unknown agent')
            if key == 'global_hotkey':
                from global_shortcut import apply
                value = apply(value)
            app.set_preference(key, value)
        return app.preferences
    if op == 'sources':
        if 'name' in args:
            if args['name'] not in SOURCES: raise ValueError('Unknown source')
            app.set_source_enabled(args['name'], boolean(args.get('enabled')))
        return [dict(name=name, installed=shortcut_sets.installed(name), enabled=name not in app.disabled_sources,
                     count=app.source_counts.get(name), category=shortcut_sets.category(name)) for name in SOURCES]
    if op == 'open':
        surfaces = {'settings': (None, lambda: preferences.show(app)), 'features':(None, app.show_features),
                    'shortcuts':(None, app.show_shortcuts), 'sets':(None, lambda: __import__('source_library').show(app)),
                    'about':(None, lambda: __import__('about').show(app)), 'details':(None, app.show_details),
                    'guide':('guide',app.show_guide), 'inputs':('inputs',app.input_controls.show), 'chat':('agent',app.show_chat)}
        surface = args.get('surface')
        if surface not in surfaces: raise ValueError('Unknown surface')
        feature, show = surfaces[surface]
        if feature and not app.feature_enabled(feature): app.set_feature(feature, True)
        show()
        return dict(opened=surface)
    if op == 'inputs':
        import input_controls
        if set(args)-{'gestures','buttons','controller','device'}: raise ValueError('Unknown input option')
        available = input_controls.devices()
        paths = {path: device for device in available for path in device['joysticks']}
        for key, keys in [('gestures',('up','down','left','right')),('buttons',tuple(str(i) for i in range(8)))]:
            if key in args and (not isinstance(args[key],dict) or any(k not in keys or v not in dict(input_controls.ACTIONS) for k,v in args[key].items())): raise ValueError('Invalid '+key)
        if 'controller' in args: boolean(args['controller'])
        if 'device' in args and args['device'] not in paths and args['device'] != '': raise ValueError('Select an available joystick path')
        if args:
            config = app.input_controls.config
            for key in ('gestures','buttons'):
                if key in args: config[key] = dict(config[key], **args[key])
            if 'controller' in args: config['controller'] = args['controller']
            if 'device' in args:
                config['device'] = args['device']
                device = paths.get(args['device'])
                config['device_id'] = device['id']+' '+device['name'] if device else ''
            app.input_controls.save()
            if not app.feature_enabled('inputs'): app.set_feature('inputs', True)
            if any(v == 'chat' for k in ('gestures','buttons') for v in args.get(k,{}).values()) and not app.feature_enabled('agent'): app.set_feature('agent',True)
        return dict(devices=available, settings=app.input_controls.config, actions=dict(input_controls.ACTIONS))
    if op == 'view':
        # Validate the entire update before changing any visible state.
        unknown = set(args)-{'source','search','favorites_only','visibility','layout','flat_list','columns','look','feature_view','type','show_filters','modifiers','all_layers','live','target'}
        if unknown: raise ValueError('Unknown view option: '+', '.join(sorted(unknown)))
        if 'source' in args and args['source'] not in SOURCES: raise ValueError('Unknown source')
        if args.get('look') == 'omarchy': args = dict(args, look='square')
        for key, allowed in [('visibility',['all','hidden','visible']), ('layout',['list','keyboard']), ('look',list(__import__('theme').LOOKS))]:
            if key in args and args[key] not in allowed: raise ValueError('Invalid '+key)
        from shortcut_types import FILTERS
        if 'type' in args and args['type'] not in dict(FILTERS): raise ValueError('Invalid type; use a shortcut type from schema')
        for key in ('favorites_only','flat_list','columns','show_filters','all_layers','live'):
            if key in args: boolean(args[key])
        if 'search' in args and not isinstance(args['search'], str): raise ValueError('search must be text')
        if 'feature_view' in args:
            if not isinstance(args['feature_view'], dict) or any(k not in ('grid','previews','descriptions') or not isinstance(v,bool) for k,v in args['feature_view'].items()): raise ValueError('Invalid feature view')
        if 'modifiers' in args and (not isinstance(args['modifiers'],list) or any(v not in ('SUPER','CTRL','ALT','SHIFT') for v in args['modifiers'])): raise ValueError('Invalid modifiers')
        targets = ['current'] + [row['address'] for row in app.targets]
        if 'target' in args and args['target'] not in targets: raise ValueError('Unknown target window')
        required = set()
        if 'target' in args: required.add('target')
        if args.get('live'): required.add('live')
        if any(k in args for k in ('type','show_filters','flat_list','columns','modifiers','all_layers')): required.add('layouts')
        if args.get('favorites_only'): required.add('bookmarks')
        if args.get('visibility') in ('hidden','visible'): required.add('hidden')
        if args.get('layout') == 'keyboard': required.add('keyboard')
        if 'look' in args: required.add('appearance')
        enabled_features = sorted(k for k in required if not app.feature_enabled(k))
        for key in enabled_features: app.features[key] = True
        if enabled_features: app.apply_features()
        if 'source' in args: app.source_picker.set_selected(SOURCES.index(args['source']))
        if 'type' in args:
            app.type_filter.set_selected([k for k,_ in FILTERS].index(args['type']))
            app.settings_switches['Show filters'].set_active(True)
        if 'show_filters' in args: app.settings_switches['Show filters'].set_active(args['show_filters'])
        if 'modifiers' in args:
            app.settings_switches['Show filters'].set_active(True)
            for key,button in app.keyboard.buttons.items(): button.set_active(key in args['modifiers'])
        if 'all_layers' in args: app.keyboard.all_button.set_active(args['all_layers'])
        if 'live' in args: app.live_switch.set_active(args['live'])
        if 'target' in args: app.target.set_selected(targets.index(args['target']))
        if 'search' in args: app.search.set_text(args['search'])
        if 'favorites_only' in args: app.only_favorites.set_active(args['favorites_only'])
        if 'visibility' in args: app.learned_filter.set_selected(['all','hidden','visible'].index(args['visibility']))
        if 'layout' in args: app.view_toggle.set_active(args['layout'] == 'keyboard')
        for key, label in [('flat_list','Flat list'),('columns','Columns')]:
            if key in args: app.settings_switches[label].set_active(args[key])
        if 'look' in args: app.look_picker.set_selected(list(__import__('theme').LOOKS).index(args['look']))
        if 'feature_view' in args: app.feature_view.update(args['feature_view'])
        app.save_ui_state()
        app.render()
        return dict(source=app.source_name, filters=app.saved_filters, feature_view=app.feature_view, enabled_features=enabled_features, matches=len(app.filtered_items()))
    if op == 'guide':
        from guide import GuideController
        controller = GuideController()
        if 'values' in args:
            if not isinstance(args['values'], dict): raise ValueError('values must be an object')
            controller.patch(**args['values'])
        return controller.read()
    if op == 'reset':
        changes = app.reset_changes()
        if args.get('apply') is True:
            selected = args.get('categories', [row[0] for row in changes])
            if not isinstance(selected, list) or any(key not in [row[0] for row in changes] for key in selected): raise ValueError('Use category IDs from the reset preview')
            app.reset_defaults(set(selected))
            return {'reset':selected, 'remaining':app.reset_changes()}
        return [dict(id=key,title=title,count=count,preview=detail) for key,title,count,detail in changes]
    if op == 'sessions':
        from chat import SessionStore
        store = SessionStore(UI_STATE.parent/'chats')
        if 'id' not in args: return store.list()
        session = store.load(args['id'])
        if 'title' in args: store.rename(session, args['title'])
        return session


def register(app):
    from gi.repository import Gio, GLib
    node = Gio.DBusNodeInfo.new_for_xml(f'<node><interface name="{INTERFACE}"><method name="Request"><arg type="s" direction="in"/><arg type="s" direction="out"/></method></interface></node>')
    def call(connection, sender, path, interface, method, parameters, invocation):
        try: payload = json.loads(parameters.unpack()[0])
        except (ValueError, TypeError) as error:
            invocation.return_value(GLib.Variant('(s)', (json.dumps({'ok':False, 'error':str(error)}),)))
            return
        if isinstance(payload, dict) and payload.get('operation') == 'quota':
            import threading
            def fetch():
                try: result = {'ok':True, 'result':execute(app, payload)}
                except Exception as error: result = {'ok':False, 'error':str(error)}
                GLib.idle_add(lambda: invocation.return_value(GLib.Variant('(s)', (json.dumps(result),))))
            threading.Thread(target=fetch, daemon=True).start()
            return
        try:
            result = {'ok':True, 'result':execute(app, payload)}
        except Exception as error:
            result = {'ok':False, 'error':str(error)}
        invocation.return_value(GLib.Variant('(s)', (json.dumps(result, ensure_ascii=False),)))
    app.control_registration = app.get_dbus_connection().register_object(OBJECT, node.interfaces[0], call, None, None)


def request(payload, start=True):
    from gi.repository import Gio, GLib
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    def send():
        value = bus.call_sync(BUS, OBJECT, INTERFACE, 'Request', GLib.Variant('(s)', (json.dumps(payload),)),
                              GLib.VariantType.new('(s)'), Gio.DBusCallFlags.NONE, 15000, None)
        reply = json.loads(value.unpack()[0])
        if not reply['ok']: raise ValueError(reply['error'])
        return reply['result']
    try: return send()
    except GLib.Error:
        if not start: raise
        with open(os.devnull, 'w') as log:
            subprocess.Popen(['/usr/bin/python', str(Path(__file__).with_name('app.py')), '--background'], stdout=log, stderr=log, start_new_session=True)
        for _ in range(60):
            time.sleep(.1)
            try: return send()
            except GLib.Error: pass
        raise RuntimeError('The shortcut app did not become available.')


def mcp():
    """MCP stdio transport, one JSON-RPC message per line; stdout is protocol-only."""
    for line in sys.stdin:
        try:
            message = json.loads(line)
            if 'id' not in message: continue
            method, params = message.get('method'), message.get('params', {})
            if method == 'initialize':
                result = {'protocolVersion':params.get('protocolVersion','2024-11-05'), 'capabilities':{'tools':{}}, 'serverInfo':{'name':'bindlume','version':'1.0'}}
            elif method == 'ping': result = {}
            elif method == 'tools/list':
                result = {'tools':[{'name':'control', 'description':'Read or change the shortcut app. Call schema first for argument documentation. '+json.dumps(HELP),
                  'inputSchema':{'type':'object','properties':{'operation':{'type':'string','enum':OPERATIONS},'arguments':{'type':'object'}},'required':['operation'],'additionalProperties':False}}]}
            elif method == 'tools/call':
                try:
                    if params.get('name') != 'control': raise ValueError('Unknown tool')
                    value = request(params.get('arguments', {}))
                    result = {'content':[{'type':'text','text':json.dumps(value,ensure_ascii=False)}]}
                except Exception as error: result = {'isError':True,'content':[{'type':'text','text':str(error)}]}
            else:
                print(json.dumps({'jsonrpc':'2.0','id':message['id'],'error':{'code':-32601,'message':'Unknown method'}}), flush=True)
                continue
            print(json.dumps({'jsonrpc':'2.0','id':message['id'],'result':result}, ensure_ascii=False), flush=True)
        except (ValueError, TypeError, KeyError) as error:
            print(json.dumps({'jsonrpc':'2.0','id':None,'error':{'code':-32700,'message':str(error)}}), flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Control Bindlume from any agent or terminal. Output is JSON; changes update the running app immediately.')
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('state','schema','quota','sources','sessions','mcp'): commands.add_parser(name)
    p=commands.add_parser('search'); p.add_argument('query', nargs='?', default=''); p.add_argument('--source')
    for name in ('bookmark','hide'):
        p=commands.add_parser(name); p.add_argument('id'); p.add_argument('enabled', choices=['on','off'])
    p=commands.add_parser('features'); p.add_argument('name', nargs='?'); p.add_argument('enabled', choices=['on','off'], nargs='?')
    p=commands.add_parser('settings'); p.add_argument('key', nargs='?'); p.add_argument('value', nargs='?', help='JSON value, e.g. false, 14, or \'"system"\'')
    p=commands.add_parser('reset'); p.add_argument('--apply', action='store_true'); p.add_argument('--categories', nargs='+')
    p=commands.add_parser('request'); p.add_argument('json', help='{"operation":"view","arguments":{"search":"terminal"}}')
    args=vars(parser.parse_args(argv)); command=args.pop('command')
    if command == 'mcp': return mcp()
    try:
        if command == 'request': payload=json.loads(args['json'])
        else:
            args={k:v for k,v in args.items() if v is not None}
            if 'enabled' in args: args['enabled']=args['enabled']=='on'
            if 'value' in args: args['value']=json.loads(args['value'])
            payload={'operation':command,'arguments':args}
        print(json.dumps(request(payload), ensure_ascii=False, indent=2))
        return 0
    except Exception as error:
        print(json.dumps({'error':str(error)}), file=sys.stderr)
        return 1

if __name__ == '__main__': sys.exit(main())
