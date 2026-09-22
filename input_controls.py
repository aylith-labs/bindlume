"""Opt-in device exploration and gestures/controllers scoped to Bindlume."""
import json
import os
from pathlib import Path
import re
import struct
from gi.repository import Gtk, Gdk, GLib
import settings_ui
from localization import text as tr

ACTIONS = [('none','No action'),('search','Focus search'),('chat','Toggle chat'),('clear','Clear search'),('shortcuts','Keyboard shortcuts')]
DEFAULT = dict(gestures={}, buttons={}, controller=False, device='', device_id='')


def devices(source=Path('/proc/bus/input/devices')):
    try: text=source.read_text()
    except OSError: return []
    grouped={}
    for block in text.split('\n\n'):
        name=re.search(r'^N: Name="(.*)"',block,re.M)
        if not name: continue
        identity=re.search(r'Vendor=(\w+) Product=(\w+)',block)
        identity=':'.join(identity.groups()) if identity else ''
        key=(name.group(1),identity)
        item=grouped.setdefault(key,dict(name=key[0],id=identity,kinds=set(),joysticks=[]))
        handlers=re.search(r'^H: Handlers=(.*)',block,re.M)
        handlers=handlers.group(1).split() if handlers else []
        if 'kbd' in handlers: item['kinds'].add('Keyboard')
        if any(h.startswith('mouse') for h in handlers): item['kinds'].add('Mouse')
        for h in handlers:
            if re.fullmatch(r'js\d+',h): item['kinds'].add('Controller');item['joysticks'].append('/dev/input/'+h)
    result=[dict(item,kinds=sorted(item['kinds'])) for item in grouped.values() if item['kinds'] and not re.search(r'Power Button|Sleep Button|Video Bus|PC Speaker|WMI hotkeys|Wireless Radio', item['name'], re.I)]
    return sorted(result,key=lambda item:('Controller' not in item['kinds'],item['name'].lower()))


def direction(x,y,threshold=40):
    if max(abs(x),abs(y))<threshold: return None
    return ('right' if x>0 else 'left') if abs(x)>abs(y) else ('down' if y>0 else 'up')


class Controls:
    def __init__(self,app):
        from app import UI_STATE
        self.app=app;self.path=UI_STATE.parent/'input-controls.json';self.fd=None;self.open_device=None
        try: self.config=json.loads(self.path.read_text())
        except (OSError,ValueError): self.config={}
        if not isinstance(self.config,dict):self.config={}
        self.config={**DEFAULT,**self.config}
        for key in ('gestures','buttons'):
            if not isinstance(self.config[key],dict):self.config[key]={}
        self.drag=Gtk.GestureDrag(button=3)
        self.drag.connect('drag-end',self.gesture)
        app.window.add_controller(self.drag)
        self.timer=GLib.timeout_add(50,self.poll)
        app.window.connect('unrealize',lambda *_:self.stop())
        app.window.connect('map',lambda *_:setattr(self,'timer',GLib.timeout_add(50,self.poll)) if self.timer is None else None)
        app.connect('shutdown',lambda *_:self.stop())
        self.window=None;self.test_enabled=False;self.test_status=None

    def save(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temporary=self.path.with_suffix('.tmp');temporary.write_text(json.dumps(self.config)+'\n');temporary.chmod(0o600);temporary.replace(self.path)

    def active(self):
        return self.app.feature_enabled('inputs') and self.app.window.get_visible() and self.app.window.is_active() and not any(w is not self.app.window and w.get_visible() and w.get_modal() for w in self.app.get_windows())

    def execute(self,action):
        if not self.active():return
        if action=='search':self.app.search.grab_focus()
        elif action=='clear':self.app.search.set_text('')
        elif action=='chat':self.app.show_chat(self.app.main_pane.get_end_child() is None)
        elif action=='shortcuts':self.app.show_shortcuts()

    def gesture(self,_drag,x,y):
        name=direction(x,y)
        if name:self.execute(self.config['gestures'].get(name,'none'))

    def close_device(self):
        if self.fd is not None:
            os.close(self.fd);self.fd=None
        self.open_device=None

    def stop(self):
        self.close_device()
        if self.timer:GLib.source_remove(self.timer);self.timer=None

    def poll(self):
        testing=bool(self.window and self.window.get_visible() and self.window.is_active() and self.test_enabled)
        enabled=self.app.feature_enabled('inputs') and (testing or (self.config['controller'] and self.active()))
        path=self.config.get('device','')
        if not enabled or not isinstance(path,str) or not re.fullmatch(r'/dev/input/js\d+',path):self.close_device();return True
        if self.open_device!=path:
            self.close_device()
            identity=self.config.get('device_id')
            if identity and not any(path in d['joysticks'] and d['id']+' '+d['name']==identity for d in devices()):
                if testing:self.test_status.set_text(tr('Controller unavailable. Reconnect it or check device access.'))
                return True
            try:self.fd=os.open(path,os.O_RDONLY|os.O_NONBLOCK);self.open_device=path
            except OSError:
                if testing:self.test_status.set_text(tr('Controller unavailable. Reconnect it or check device access.'))
                return True
        try:
            for _ in range(64):
                event=os.read(self.fd,8)
                if len(event)!=8:self.close_device();break
                _time,value,kind,number=struct.unpack('IhBB',event)
                if kind&0x80:continue # Initial state is never an action.
                if testing:
                    self.test_status.set_text(tr('Button {number}: {value}').format(number=number+1,value=value) if kind==1 else tr('Axis {number}: {value}').format(number=number+1,value=value))
                elif kind==1 and value==1:self.execute(self.config['buttons'].get(str(number),'none'))
        except BlockingIOError:pass
        except OSError:self.close_device()
        return True

    def show(self):
        if self.window:self.window.present();return
        window=Gtk.Window(application=self.app,transient_for=self.app.window,modal=True,title=tr('Mouse gestures & controllers'),default_width=780,default_height=660)
        self.window=window;window.add_css_class('shortcuts-app')
        root=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=16,margin_top=20,margin_bottom=20,margin_start=20,margin_end=20)
        settings_ui.header(root,window,'Mouse gestures & controllers')
        body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=14)
        scroll=Gtk.ScrolledWindow(vexpand=True,hscrollbar_policy=Gtk.PolicyType.NEVER);scroll.set_child(body);root.append(scroll);window.set_child(root)
        settings_ui.section(body,'Connected devices')
        device_box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8)
        devices_scroll=Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, min_content_height=130,max_content_height=190,propagate_natural_height=True)
        devices_scroll.set_child(device_box);body.append(devices_scroll)
        picker=Gtk.DropDown.new_from_strings([tr('No controller selected')]);paths=['']
        def refresh(*_):
            while child:=device_box.get_first_child():device_box.remove(child)
            found=devices();names=[tr('No controller selected')];paths[:]=['']
            for item in found:
                text=item['name']+' · '+item['id']+'\n'+' · '.join(tr(v) for v in item['kinds'])
                label=Gtk.Label(label=text,xalign=0,wrap=True);label._translation_skip=True;device_box.append(label)
                for node in item['joysticks']:paths.append(node);names.append(item['name']+' · '+node)
            if not found:device_box.append(Gtk.Label(label=tr('No input devices detected.'),xalign=0))
            previous=self.config['device'];self.refreshing=True
            picker.set_model(Gtk.StringList.new(names));picker.set_selected(paths.index(previous) if previous in paths else 0)
            self.refreshing=False
        refresh_button=Gtk.Button(label=tr('Refresh devices'));refresh_button.connect('clicked',refresh);body.append(refresh_button)
        settings_ui.section(body,'Mouse gestures')
        body.append(Gtk.Label(label=tr('Hold the right mouse button and drag inside Bindlume. Assign actions below.'),xalign=0,wrap=True))
        def mapping(title,group,key):
            pick=Gtk.DropDown.new_from_strings([tr(v) for _,v in ACTIONS]);keys=[k for k,_ in ACTIONS]
            pick.set_selected(keys.index(self.config[group].get(key)) if self.config[group].get(key) in keys else 0)
            def changed(w,*_):self.config[group][key]=keys[w.get_selected()];self.save()
            pick.connect('notify::selected',changed);settings_ui.row(body,title,pick)
        for key,title in [('left','Drag left'),('right','Drag right'),('up','Drag up'),('down','Drag down')]:mapping(title,'gestures',key)
        pad=Gtk.Frame();pad.set_size_request(-1,90)
        status=Gtk.Label(label=tr('Try a right-button gesture here'));pad.set_child(status);body.append(pad)
        drag=Gtk.GestureDrag(button=3);pad.add_controller(drag)
        drag.connect('drag-end',lambda _,x,y:status.set_text(tr({'left':'Drag left','right':'Drag right','up':'Drag up','down':'Drag down'}.get(direction(x,y),'Move farther to recognize a gesture'))))
        settings_ui.section(body,'Controller')
        settings_ui.row(body,'Device',picker)
        refresh()
        def selected(w,*_):
            if getattr(self,'refreshing',False):return
            i=w.get_selected()
            if i<len(paths):
                self.config['device']=paths[i]
                self.config['device_id']=next((d['id']+' '+d['name'] for d in devices() if paths[i] in d['joysticks']),'')
                self.close_device();self.save()
        picker.connect('notify::selected',selected)
        enable=Gtk.Switch(active=bool(self.config['controller']))
        settings_ui.row(body,'Enable controller actions',enable,'Only while the Bindlume main window has focus. No desktop-wide remapping.')
        enable.connect('notify::active',lambda w,*_:(self.config.update(controller=w.get_active()),self.save()))
        for number in range(8):mapping(tr('Button {number}').format(number=number+1),'buttons',str(number))
        test=Gtk.Switch(active=False);settings_ui.row(body,'Test controller input',test)
        self.test_status=Gtk.Label(label=tr('Input is read only while this test is enabled and focused.'),xalign=0,wrap=True);body.append(self.test_status)
        test.connect('notify::active',lambda w,*_:setattr(self,'test_enabled',w.get_active()))
        body.append(Gtk.Label(label=tr('Azeron keyboard and mouse modes use their existing key mappings. Controller button numbers depend on the device; test before assigning.'),xalign=0,wrap=True))
        def closed(*_):self.test_enabled=False;self.close_device();self.window=None
        window.connect('unmap',closed)
        import localization
        localization.translate_tree(root);window.present()


def show(app):
    if app.feature_enabled('inputs'):app.input_controls.show()
