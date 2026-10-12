"""Bounded local operation journal and conflict-checked undo/redo."""
import copy
from datetime import datetime, timedelta
import json
import sqlite3
import os
from contextlib import contextmanager
from pathlib import Path
import uuid
from localization import text as tr

MUTATIONS = {'settings','decision_apply','features','bookmark','hide','sources','view','reset','guide','companion','sessions','inputs'}
AUDITED = MUTATIONS | {'search','open'}


def policy(app):
    return {'max_operations':app.preferences.get('activity_limit',1000), 'max_age_days':app.preferences.get('activity_days',0), 'zero_means_unlimited':True}


def snapshot(app):
    from app import SOURCES, FILTERS
    values={}
    for key,value in app.preferences.items():values['preference/'+key]=copy.deepcopy(value)
    for key,value in app.features.items():values['feature/'+key]=bool(value)
    for name in SOURCES:values['source/'+name]=name not in app.disabled_sources
    for key in app.favorites:values['bookmark/'+key]=True
    for key in app.learned:values['hidden/'+key]=True
    if getattr(app,'search',None):
        view={'source':app.source_name,'search':app.search.get_text(),'favorites_only':app.only_favorites.get_active(),
              'visibility':['all','hidden','visible'][app.learned_filter.get_selected()],
              'columns':app.columns, 'look':app.look, 'modifiers':sorted(app.keyboard.manual),
              'all_layers':app.keyboard.all_layers, 'raised_keys':app.keyboard.raised_keys,
              'live':app.live_switch.get_active(), 'feature_view':copy.deepcopy(app.feature_view),
              'type':FILTERS[app.type_filter.get_selected()][0], 'flat_list':app.flat_list,
              'layout':'keyboard' if app.view_stack.get_visible_child_name()=='keyboard' else 'list',
              'show_filters':app.settings_switches['Show filters'].get_active()}
        values.update({'view/'+k:v for k,v in view.items()})
    return values


class Journal:
    def __init__(self,path):self.path=Path(path)
    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        fd=os.open(self.path,os.O_CREAT|os.O_RDWR,0o600);os.close(fd)
        db=sqlite3.connect(self.path)
        try:
            db.execute('CREATE TABLE IF NOT EXISTS operations (id TEXT PRIMARY KEY, stamp REAL NOT NULL, data TEXT NOT NULL)')
            db.execute('CREATE INDEX IF NOT EXISTS operation_time ON operations(stamp)')
            db.execute('CREATE TABLE IF NOT EXISTS stacks (seq INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, id TEXT NOT NULL)')
            with db:yield db
        finally:db.close()
    def prune(self,db,retention):
        days=retention['max_age_days'];limit=retention['max_operations']
        if days:db.execute('DELETE FROM operations WHERE stamp < ?',((datetime.now().astimezone()-timedelta(days=days)).timestamp(),))
        if limit:db.execute('DELETE FROM operations WHERE id IN (SELECT id FROM operations ORDER BY stamp DESC,rowid DESC LIMIT -1 OFFSET ?)',(limit,))
        db.execute('DELETE FROM stacks WHERE id NOT IN (SELECT id FROM operations)')
    def insert(self,db,entry):
        db.execute('INSERT INTO operations VALUES (?,?,?)',(entry['id'],datetime.fromisoformat(entry['time']).timestamp(),json.dumps(entry,ensure_ascii=False)))
    def read(self):
        with self.connect() as db:
            return {'entries':[json.loads(r[0]) for r in db.execute('SELECT data FROM operations ORDER BY stamp,rowid')],
                    **{kind:[r[0] for r in db.execute('SELECT id FROM stacks WHERE kind=? ORDER BY seq',(kind,))] for kind in ('undo','redo')}}
    def append(self,app,operation,args,before,after,origin='agent',error=None):
        changed={k for k in before.keys()|after.keys() if before.get(k,False)!=after.get(k,False)}
        if not changed and operation in MUTATIONS and operation not in ('guide','inputs','sessions','companion') and not error:return
        reversible=bool(changed) and not error and operation not in ('reset','guide','companion','sessions','inputs') and 'preference/global_hotkey' not in changed
        entry={'id':uuid.uuid4().hex,'time':datetime.now().astimezone().isoformat(),'operation':operation,'arguments':args,
               'origin':origin,'status':'failed' if error else 'completed','reversible':reversible,
               'before':{k:before.get(k,False) for k in changed},'after':{k:after.get(k,False) for k in changed}}
        if error:entry['error']=str(error)
        with self.connect() as db:
            self.insert(db,entry)
            if changed:
                db.execute("DELETE FROM stacks WHERE kind='redo'")
                if reversible:db.execute('INSERT INTO stacks(kind,id) VALUES (?,?)',('undo',entry['id']))
            self.prune(db,policy(app))


def journal():
    from app import UI_STATE
    return Journal(UI_STATE.parent/'activity.sqlite3')


def tracked(app,payload,run,origin='agent'):
    operation=payload.get('operation')
    if getattr(app,'_activity_depth',0) or operation not in AUDITED:return run()
    before=snapshot(app)
    app._activity_depth=1
    try:
        result=run()
    except Exception as error:
        journal().append(app,operation,payload.get('arguments',{}),before,snapshot(app),origin,error)
        raise
    else:
        journal().append(app,operation,payload.get('arguments',{}),before,snapshot(app),origin)
        return result
    finally:app._activity_depth=0


def ui_operation(operation, arguments):
    def decorate(method):
        def wrapped(app,*args,**kwargs):
            if not getattr(app,'window',None) or not hasattr(app,'settings_switches'):
                return method(app,*args,**kwargs)
            payload={'operation':operation,'arguments':arguments(*args,**kwargs)}
            return tracked(app,payload,lambda:method(app,*args,**kwargs),'ui')
        return wrapped
    return decorate


def query(app,args):
    limit=args.get('limit',10);offset=args.get('offset',0)
    if type(limit) is not int or not 1<=limit<=1000 or type(offset) is not int or offset<0:
        raise ValueError(tr('Invalid activity request.'))
    date=args.get('date')
    today=datetime.now().astimezone().date()
    if date in ('today','yesterday'):date=(today-timedelta(days=date=='yesterday')).isoformat()
    if date is not None:
        try:datetime.strptime(date,'%Y-%m-%d')
        except (ValueError,TypeError):raise ValueError(tr('Invalid activity request.')) from None
    store=journal()
    with store.connect() as db:
        store.prune(db,policy(app))
        where='';params=[]
        if date:
            start=datetime.strptime(date,'%Y-%m-%d')
            where=' WHERE stamp>=? AND stamp<?'
            params=[start.astimezone().timestamp(),(start+timedelta(days=1)).astimezone().timestamp()]
        matching=db.execute('SELECT COUNT(*) FROM operations'+where,params).fetchone()[0]
        entries=[json.loads(r[0]) for r in db.execute('SELECT data FROM operations'+where+' ORDER BY stamp DESC,rowid DESC LIMIT ? OFFSET ?',params+[limit,offset])]
        retained=db.execute('SELECT COUNT(*) FROM operations').fetchone()[0]
        available={kind:bool(db.execute('SELECT 1 FROM stacks WHERE kind=? LIMIT 1',(kind,)).fetchone()) for kind in ('undo','redo')}
    return {'operations':[{k:v for k,v in e.items() if k not in ('before','after')} for e in entries],
            'matching':matching,'retained':retained,'offset':offset,'retention':policy(app),
            'can_undo':available['undo'],'can_redo':available['redo']}


def change_retention(app,args):
    allowed={'max_operations','max_age_days'}
    if set(args)-allowed or not args or any(type(v) is not int or v<0 for v in args.values()):
        raise ValueError(tr('Invalid activity request.'))
    before=snapshot(app);app._activity_depth=1
    try:
        for key,value in args.items():app.set_preference('activity_limit' if key=='max_operations' else 'activity_days',value)
    finally:app._activity_depth=0
    journal().append(app,'settings',{'retention':args},before,snapshot(app))
    return dict(policy(app),retained=query(app,{})['retained'])


def restore(app,action):
    from agent_control import _execute
    store=journal()
    with store.connect() as db:
        store.prune(db,policy(app))
        row=db.execute('SELECT operations.data,stacks.seq FROM stacks JOIN operations USING(id) WHERE stacks.kind=? ORDER BY stacks.seq DESC LIMIT 1',(action,)).fetchone()
        if not row:raise ValueError(tr('Nothing to undo.' if action=='undo' else 'Nothing to redo.'))
        entry=json.loads(row[0]);sequence=row[1]
    expected,target=(entry['after'],entry['before']) if action=='undo' else (entry['before'],entry['after'])
    current=snapshot(app)
    if any(current.get(k,False)!=v for k,v in expected.items()):
        raise ValueError(tr('The app changed since this operation. Undo or redo was not applied.'))
    # Validate all stored domains before applying anything. Changes contain only
    # values previously accepted by the app, and external binding edits are excluded.
    from preferences import DEFAULTS
    from features import FEATURES
    from app import SOURCES
    for key,value in target.items():
        kind,name=key.split('/',1)
        valid=(kind=='preference' and name in DEFAULTS and type(value) is type(DEFAULTS[name]) or
               kind=='feature' and name in FEATURES and type(value) is bool or
               kind=='source' and name in SOURCES and type(value) is bool or
               kind in ('bookmark','hidden') and type(value) is bool and any(item['id']==name for item in app.items) or
               kind=='view' and name in ('source','search','favorites_only','visibility','type','flat_list','layout','show_filters','columns','look','modifiers','all_layers','raised_keys','live','feature_view'))
        if not valid:raise ValueError(tr('Invalid activity log.'))
    app._activity_depth=1
    try:
        view={k.split('/',1)[1]:v for k,v in target.items() if k.startswith('view/')}
        if view:_execute(app,{'operation':'view','arguments':view})
        # Restore automatic feature prerequisites last, after restoring the view.
        for kind in ('preference','source','bookmark','hidden','feature'):
            for key,value in target.items():
                prefix,name=key.split('/',1)
                if prefix!=kind:continue
                if kind=='preference':payload={'operation':'settings','arguments':{'key':name,'value':value}}
                elif kind in ('source','feature'):payload={'operation':'sources' if kind=='source' else 'features','arguments':{'name':name,'enabled':value}}
                else:payload={'operation':'bookmark' if kind=='bookmark' else 'hide','arguments':{'id':name,'enabled':value}}
                _execute(app,payload)
    finally:app._activity_depth=0
    actual=snapshot(app)
    if any(actual.get(k,False)!=v for k,v in target.items()):raise ValueError(tr('The operation could not be fully restored.'))
    record={'id':uuid.uuid4().hex,'time':datetime.now().astimezone().isoformat(),'operation':action,'arguments':{'operation_id':entry['id']},'origin':'agent','status':'completed','reversible':False}
    with store.connect() as db:
        db.execute('DELETE FROM stacks WHERE seq=?',(sequence,))
        db.execute('INSERT INTO stacks(kind,id) VALUES (?,?)',('redo' if action=='undo' else 'undo',entry['id']))
        store.insert(db,record);store.prune(db,policy(app))
    return {'operation':action,'operation_id':entry['id'],'restored':target,'retention':policy(app)}


def show(app):
    from gi.repository import Gtk
    import settings_ui
    from agent_control import execute
    if getattr(app,'activity_window',None):app.activity_window.present();return
    window=Gtk.Window(application=app,transient_for=app.window,title=tr('Activity log'),default_width=840,default_height=700)
    app.activity_window=window
    window.connect('close-request',lambda *_:setattr(app,'activity_window',None) or False)
    body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12,margin_top=20,margin_bottom=20,margin_start=20,margin_end=20)
    settings_ui.header(body,window,'Activity log')
    controls=Gtk.Box(spacing=8)
    cap=Gtk.SpinButton.new_with_range(0,1000000000,1);cap.set_value(app.preferences.get('activity_limit',1000))
    days=Gtk.SpinButton.new_with_range(0,1000000,1);days.set_value(app.preferences.get('activity_days',0))
    settings_ui.row(body,'Maximum operations',cap)
    settings_ui.row(body,'Retention days',days)
    body.append(Gtk.Label(label=tr('Zero means unlimited. Pruned operations cannot be recovered.'),xalign=0,wrap=True))
    body.append(controls)
    status=Gtk.Label(xalign=0,wrap=True);body.append(status)
    scroll=Gtk.ScrolledWindow(vexpand=True);body.append(scroll)
    rows=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10);scroll.set_child(rows)
    date=Gtk.DropDown.new_from_strings([tr('All'),tr('Today'),tr('Yesterday')]);controls.append(date)
    offset=[0]
    def refresh(*_):
        while child:=rows.get_first_child():rows.remove(child)
        args={'limit':50,'offset':offset[0]}
        if date.get_selected():args['date']=['','today','yesterday'][date.get_selected()]
        result=execute(app,{'operation':'activity','arguments':args})
        for entry in result['operations']:
            text=entry['time']+' · '+entry['operation']+'\n'+json.dumps(entry['arguments'],ensure_ascii=False)
            label=Gtk.Label(label=text,xalign=0,wrap=True,selectable=True);label._translation_skip=True;rows.append(label)
        if not result['operations']:rows.append(Gtk.Label(label=tr('No activity yet.'),xalign=0))
        undo.set_sensitive(result['can_undo']);redo.set_sensitive(result['can_redo'])
        previous.set_sensitive(offset[0]>0);following.set_sensitive(offset[0]+50<result['matching'])
        return result
    def perform(action):
        try:
            args={'action':action}
            if action=='retention':args.update(max_operations=cap.get_value_as_int(),max_age_days=days.get_value_as_int())
            execute(app,{'operation':'activity','arguments':args})
            status.set_text(tr('App tool finished'));refresh()
            cap.set_value(app.preferences['activity_limit']);days.set_value(app.preferences['activity_days'])
        except Exception as error:status.set_text(str(error))
    for label,action in [('Apply','retention'),('Undo','undo'),('Redo','redo')]:
        button=Gtk.Button(label=tr(label));button.connect('clicked',lambda _,a=action:perform(a));controls.append(button)
        if action=='undo':undo=button
        if action=='redo':redo=button
    previous=Gtk.Button(label=tr('Previous'));following=Gtk.Button(label=tr('Next'))
    controls.append(previous);controls.append(following)
    def page(change):offset[0]=max(0,offset[0]+change);refresh()
    previous.connect('clicked',lambda *_:page(-50));following.connect('clicked',lambda *_:page(50))
    date.connect('notify::selected',lambda *_:(offset.__setitem__(0,0),refresh()))
    window.activity_controls={'limit':cap,'days':days,'undo':undo,'redo':redo,'rows':rows}
    refresh();window.set_child(body);window.present()
