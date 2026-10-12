"""Bounded, opt-in request diagnostics. Never stores HTTP headers or credentials."""
import json
import math
import os
from pathlib import Path
import sqlite3
from datetime import datetime
import uuid

LIMIT = 50
MAX_BYTES = 524288
DESCRIPTION = 'Records the latest 50 requests locally, up to 512 KiB each. Content may include your prompts, instructions and tool results. Headers and API credentials are excluded. Turn recording off or clear the history at any time.'
TOKEN_HELP = 'Estimates use one token per four characters, not the model tokenizer. Reported input tokens appear when a provider supplies them. For installed agents, only the input handed to the agent is visible; its internal context and extra requests are not captured.'


def database():
    from app import UI_STATE
    path=UI_STATE.parent/'model-insights.sqlite3'
    path.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(path,os.O_CREAT|os.O_RDWR,0o600);os.close(fd)
    db=sqlite3.connect(path,timeout=5)
    db.execute('CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, created TEXT NOT NULL, data TEXT NOT NULL)')
    return db


def record(prefs,provider,kind,content):
    if not prefs.get('model_insights_enabled'):return None
    raw=content if isinstance(content,str) else json.dumps(content,ensure_ascii=False,indent=2)
    encoded=raw.encode('utf-8')
    entry=dict(id=uuid.uuid4().hex,created=datetime.now().astimezone().isoformat(),provider=provider,kind=kind,
               content=encoded[:MAX_BYTES].decode('utf-8',errors='ignore'),bytes=len(encoded),
               estimated_tokens=0 if kind=='Local command' else math.ceil(len(raw)/4),
               truncated=len(encoded)>MAX_BYTES,reported_input_tokens=0 if kind=='Local command' else None)
    if isinstance(content,str):
        try:content=json.loads(content)
        except ValueError:pass
    if isinstance(content,dict) and kind!='Local command':
        entry['components']={key:dict(bytes=len(json.dumps(value,ensure_ascii=False).encode()),estimated_tokens=math.ceil(len(json.dumps(value,ensure_ascii=False))/4)) for key,value in content.items()}
    try:
        db=database()
        with db:
            db.execute('INSERT INTO requests VALUES (?,?,?)',(entry['id'],entry['created'],json.dumps(entry,ensure_ascii=False)))
            db.execute('DELETE FROM requests WHERE id IN (SELECT id FROM requests ORDER BY created DESC,rowid DESC LIMIT -1 OFFSET ?)',(LIMIT,))
        db.close()
        return entry['id']
    except (OSError,sqlite3.Error):return None  # Diagnostics must not interrupt a request.


def usage(identity,value):
    if not identity:return
    count=value.get('input_tokens',value.get('prompt_tokens')) if isinstance(value,dict) else None
    if type(count) is not int or count<0:return
    try:
        db=database()
        with db:
            row=db.execute('SELECT data FROM requests WHERE id=?',(identity,)).fetchone()
            if row:
                entry=json.loads(row[0]);entry['reported_input_tokens']=count
                db.execute('UPDATE requests SET data=? WHERE id=?',(json.dumps(entry,ensure_ascii=False),identity))
        db.close()
    except (OSError,sqlite3.Error):pass


def entries():
    db=database()
    try:return [json.loads(row[0]) for row in db.execute('SELECT data FROM requests ORDER BY created DESC,rowid DESC')]
    finally:db.close()


def clear():
    db=database()
    try:
        with db:db.execute('DELETE FROM requests')
    finally:db.close()


def populate(app,content):
    from gi.repository import Gtk
    from localization import text as tr
    import settings_ui
    from usage_view import relative_time
    toggle=Gtk.Switch(active=app.preferences.get('model_insights_enabled',False))
    settings_ui.row(content,tr('Record model requests'),toggle,tr(DESCRIPTION))
    toggle.connect('notify::active',lambda w,*_:app.set_preference('model_insights_enabled',w.get_active()))
    help_label=Gtk.Label(label=tr(TOKEN_HELP),xalign=0,wrap=True,max_width_chars=64)
    help_label.add_css_class('dim-label');content.append(help_label)
    bar=Gtk.Box(spacing=8);content.append(bar)
    refresh=Gtk.Button(label=tr('Refresh'));erase=Gtk.Button(label=tr('Clear history'))
    bar.append(refresh);bar.append(erase)
    summary=Gtk.Label(xalign=0,wrap=True);content.append(summary)
    rows=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10);content.append(rows)
    def reload(*_):
        while child:=rows.get_first_child():rows.remove(child)
        history=entries()
        summary.set_text(tr('Requests: {count} · Estimated input tokens: {tokens}').format(count=len(history),tokens=sum(e['estimated_tokens'] for e in history))+'\n'+tr('Reported input tokens: {tokens} · Requests without usage: {count}').format(tokens=sum(e['reported_input_tokens'] or 0 for e in history),count=sum(e['reported_input_tokens'] is None for e in history)))
        if not history:rows.append(Gtk.Label(label=tr('No recorded requests yet.'),xalign=0))
        for entry in history:
            group=Gtk.Expander(label=entry['provider']+' · '+tr(entry['kind'])+' · '+relative_time(entry['created']))
            group._translation_skip=True
            details=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8,margin_start=12,margin_top=8)
            report=entry['reported_input_tokens']
            metrics=tr('Input: {bytes} bytes · Estimated tokens: {estimated} · Reported tokens: {reported}').format(bytes=entry['bytes'],estimated=entry['estimated_tokens'],reported=report if report is not None else tr('Not reported'))
            details.append(Gtk.Label(label=metrics,xalign=0,wrap=True))
            for name,component in entry.get('components',{}).items():
                label=Gtk.Label(label=name+' · '+tr('Input: {bytes} bytes · Estimated tokens: {estimated} · Reported tokens: {reported}').format(bytes=component['bytes'],estimated=component['estimated_tokens'],reported=tr('Not reported')),xalign=0,wrap=True)
                label._translation_skip=True;details.append(label)
            if entry['truncated']:details.append(Gtk.Label(label=tr('Content truncated at 512 KiB; sizes describe the complete request.'),xalign=0,wrap=True))
            editor=Gtk.TextView(editable=False,cursor_visible=False,monospace=True,wrap_mode=Gtk.WrapMode.WORD_CHAR)
            editor.get_buffer().set_text(entry['content'])
            editor._translation_skip=True
            scroll=Gtk.ScrolledWindow(min_content_height=160,max_content_height=320,propagate_natural_height=True)
            scroll.set_child(editor);details.append(scroll)
            group.set_child(details);rows.append(group)
    refresh.connect('clicked',reload)
    erase.connect('clicked',lambda *_:(clear(),reload()))
    content.reload_insights=reload
    reload()
