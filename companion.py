"""Companion preferences, explicit user memory, and runtime information."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import tomllib
from gi.repository import Gtk, GLib, Pango
import settings_ui
from localization import text as tr


def memory_path(root): return Path(root)/'user-memory.md'

def read_memory(root):
    try:return [line[2:].strip() for line in memory_path(root).read_text().splitlines() if line.startswith('- ') and line[2:].strip()]
    except FileNotFoundError:return []

def write_memory(root, entries):
    if not isinstance(entries,list) or len(entries)>200 or any(not isinstance(v,str) or len(v)>2000 for v in entries):raise ValueError('Use at most 200 memory entries of 2000 characters each.')
    entries=list(dict.fromkeys(' '.join(v.split()) for v in entries if v.strip()))
    path=memory_path(root);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp');temporary.write_text(''.join('- '+value+'\n' for value in entries));temporary.chmod(0o600);temporary.replace(path)
    return entries

def runtime(provider, session=None):
    model=(session or {}).get('model')
    if provider.startswith('api_'):
        from chat_api import DEFAULTS
        return dict(harness=DEFAULTS.get(provider, ('',))[0], model=model or tr('Configured in AI companion settings'), reported=bool(model))
    if not model and provider=='codex':
        try:model=tomllib.loads((Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))/'config.toml').read_text()).get('model')
        except (OSError,ValueError):pass
    return dict(harness=shutil.which(provider) or tr('Not installed'),model=model or tr('Agent default'),reported=bool((session or {}).get('model')))

def harness_version(executable):
    try:
        result=subprocess.run([executable,'--version'],capture_output=True,text=True,timeout=3,check=True)
        return next((line.strip()[:200] for line in result.stdout.splitlines() if line.strip()),tr('Version unavailable'))
    except (OSError,subprocess.SubprocessError):return tr('Version unavailable')


def tokens(session):
    usage=session.get('usage_total',session.get('usage',{}))
    return sum(int(usage.get(k,0) or 0) for k in ('input_tokens','output_tokens'))

def show(app,panel=None):
    if getattr(app,'companion_window',None):app.companion_window.present();return
    from app import UI_STATE
    window=Gtk.Window(application=app,transient_for=app.window,modal=True,title='AI companion settings',default_width=760,default_height=700)
    app.companion_window=window
    window.connect('close-request',lambda *_:setattr(app,'companion_window',None) or False)
    body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=14,margin_top=20,margin_bottom=20,margin_start=20,margin_end=20)
    settings_ui.header(body,window,'AI companion settings')
    content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=14)
    scroll=Gtk.ScrolledWindow(vexpand=True,hscrollbar_policy=Gtk.PolicyType.NEVER);scroll.set_child(content);body.append(scroll)
    def switch(title,key,description=None):
        control=Gtk.Switch(active=app.preferences[key]);settings_ui.row(content,title,control,description)
        def changed(widget,*_):
            app.set_preference(key,widget.get_active())
            if panel and not panel.run:panel.render()
        control.connect('notify::active',changed);return control
    settings_ui.section(content,'Agent')
    provider=(panel.session or {}).get('provider') if panel else None
    provider=provider or app.preferences['agent_provider']
    from chat import available_agents,PROVIDERS
    choices=['auto']+available_agents(app.preferences);picker=Gtk.DropDown.new_from_strings(['Automatic']+[PROVIDERS[p] for p in choices[1:]])
    picker.set_selected(choices.index(app.preferences['agent_provider']) if app.preferences['agent_provider'] in choices else 0)
    picker.connect('notify::selected',lambda w,*_:app.set_preference('agent_provider',choices[w.get_selected()]))
    settings_ui.row(content,'Default agent',picker)
    window.harness_details = {}
    for agent in available_agents(app.preferences):
        if agent.startswith('api_'):continue
        data=runtime(agent,panel.session if panel and panel.session and panel.session['provider']==agent else None)
        group=Gtk.Expander(label=f"{PROVIDERS[agent]} · {data['model']}")
        group._translation_skip=True
        details=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8,margin_top=10,margin_bottom=10,margin_start=18)
        path=Gtk.Label(label=data['harness'],xalign=0,wrap=True,wrap_mode=Pango.WrapMode.WORD_CHAR,max_width_chars=48,selectable=True)
        path._translation_skip=True
        settings_ui.row(details,'Executable',path)
        version=Gtk.Label(label=tr('Loading…'),xalign=0,wrap=True,selectable=True)
        settings_ui.row(details,'Version',version)
        group.set_child(details);content.append(group)
        window.harness_details[agent]=group
        def expanded(widget,*_, executable=data['harness'], label=version):
            if not widget.get_expanded() or getattr(widget,'_version_requested',False):return
            widget._version_requested=True
            def worker():
                value=harness_version(executable)
                def apply():
                    label.set_text(value);label._translation_skip=True
                    return False
                GLib.idle_add(apply)
            threading.Thread(target=worker,daemon=True).start()
        group.connect('notify::expanded',expanded)
    settings_ui.section(content,'Direct model connections')
    guidance = Gtk.Label(label=tr('Use a tool-capable model. API keys stay in environment variables. Start a new chat after changing connections.'), xalign=0, wrap=True)
    content.append(guidance)
    from chat_api import DEFAULTS, PROVIDERS as API_PROVIDERS
    window.connection_controls = {}
    for provider, (base, key_env, model) in DEFAULTS.items():
        group = Gtk.Expander(label=API_PROVIDERS[provider])
        form = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8,margin_top=8,margin_bottom=8)
        group.set_child(form);content.append(group)
        current = app.preferences.get('chat_connections',{}).get(provider,{})
        enabled=Gtk.Switch(active=bool(current.get('enabled')))
        settings_ui.row(form,'Enabled',enabled)
        fields = {}
        for field, title, default in [('url','Base URL',base),('model','Model',model),('key_env','API key environment variable',key_env)]:
            control=Gtk.Entry(text=current.get(field,default),hexpand=True)
            control.set_placeholder_text(default or tr('Optional'))
            settings_ui.row(form,title,control);fields[field]=control
        def save_connection(*_, provider=provider, fields=fields, enabled=enabled):
            values={key:control.get_text().strip() for key,control in fields.items()}
            values['enabled']=enabled.get_active()
            connections=dict(app.preferences.get('chat_connections',{}));connections[provider]=values
            app.set_preference('chat_connections',connections)
            if panel and not panel.session and not panel.run:panel.new()
        enabled.connect('notify::active',save_connection)
        for control in fields.values():control.connect('changed',save_connection)
        window.connection_controls[provider] = dict(fields,enabled=enabled)
    settings_ui.section(content,'Chat presentation')
    switch('Keyboard snippets','chat_snippets','Allow illustrated keyboard shortcuts in replies.')
    switch('Fade keyboard snippet edges','chat_vignette','Use a soft vignette around generated keyboards.')
    switch('Show session token usage','chat_token_usage','Show reported input and output tokens. Providers may not report usage.')
    settings_ui.section(content,'Personalization')
    memory=switch('Remember my preferences','chat_memory_enabled','Only save facts and preferences you explicitly ask the agent to remember.')
    memory_box=Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR,height_request=100)
    memory_box.add_css_class('companion-editor')
    memory_box.get_buffer().set_text('\n'.join('- '+v for v in read_memory(UI_STATE.parent)))
    memory_box.set_sensitive(memory.get_active());memory.connect('notify::active',lambda w,*_:memory_box.set_sensitive(w.get_active()))
    content.append(memory_box)
    save=Gtk.Button(label='Save memory', sensitive=memory.get_active())
    memory.connect('notify::active',lambda w,*_:save.set_sensitive(w.get_active()))
    def save_memory(*_):
        b=memory_box.get_buffer();write_memory(UI_STATE.parent,[line.lstrip('- ').strip() for line in b.get_text(b.get_start_iter(),b.get_end_iter(),False).splitlines()])
        save.set_label(tr('Saved'))
    save.connect('clicked',save_memory);content.append(save)
    path=Gtk.Label(label=str(memory_path(UI_STATE.parent)),xalign=0,selectable=True,wrap=True);path.add_css_class('dim-label');content.append(path)
    instructions=switch('Use custom instructions','chat_instructions_enabled','Applied to subsequent messages in every companion conversation.')
    editor=Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR,height_request=130)
    editor.add_css_class('companion-editor')
    editor.get_buffer().set_text(app.preferences['chat_instructions']);editor.set_sensitive(instructions.get_active())
    instructions.connect('notify::active',lambda w,*_:editor.set_sensitive(w.get_active()))
    def store(buffer):app.preferences['chat_instructions']=buffer.get_text(buffer.get_start_iter(),buffer.get_end_iter(),False)[:16000];app.save_ui_state()
    editor.get_buffer().connect('changed',store);content.append(editor)
    window.set_child(body);window.present()
