"""Layout-aware physical keyboard with live modifier layers and clickable keys."""
import ctypes as C
import ctypes.util
import json
import os
import socket
import subprocess
import threading
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, GLib
from shortcut_data import split_shortcut, canonical, details, tooltip_widget

# Standard XKB physical key names, positioned in quarter-key units.
ROWS = [
 [('ESC',1),('gap',1)]+[(f'FK{i:02}',1) for i in range(1,13)],
 [('TLDE',1)]+[(f'AE{i:02}',1) for i in range(1,13)]+[('BKSP',2)],
 [('TAB',1.5)]+[(f'AD{i:02}',1) for i in range(1,13)]+[('BKSL',1.5)],
 [('CAPS',1.75)]+[(f'AC{i:02}',1) for i in range(1,12)]+[('RTRN',2.25)],
 [('LFSH',2.25)]+[(f'AB{i:02}',1) for i in range(1,11)]+[('RTSH',2.75)],
 [('LCTL',1.25),('LWIN',1.25),('LALT',1.25),('SPCE',6.25),('RALT',1.25),('RWIN',1.25),('MENU',1.25),('RCTL',1.25)],
]
SPECIAL = {'ESC':'Esc','BKSP':'Backspace','TAB':'Tab','CAPS':'Caps','RTRN':'Enter','LFSH':'Shift',
           'RTSH':'Shift','LCTL':'Ctrl','RCTL':'Ctrl','LWIN':'Super','RWIN':'Super','LALT':'Alt','RALT':'Alt',
           'SPCE':'Space','MENU':'Menu','PRSC':'Print','SCLK':'ScrLk','PAUS':'Pause','INS':'Ins','HOME':'Home',
           'PGUP':'PgUp','DELE':'Del','END':'End','PGDN':'PgDn','UP':'↑','LEFT':'←','DOWN':'↓','RGHT':'→',
           'NMLK':'Num','KPDV':'/','KPMU':'*','KPSU':'−','KPAD':'+','KPEN':'Enter','KPDL':'.'}
MOD_KEYS = {'LFSH':'SHIFT','RTSH':'SHIFT','LCTL':'CTRL','RCTL':'CTRL','LWIN':'SUPER','RWIN':'SUPER','LALT':'ALT','RALT':'ALT'}

class XkbLayout:
    def __init__(self, device):
        lib = self.lib = C.CDLL(ctypes.util.find_library('xkbcommon'))
        class Names(C.Structure):
            _fields_ = [(n,C.c_char_p) for n in ('rules','model','layout','variant','options')]
        signatures = {'xkb_context_new':([C.c_int],C.c_void_p),
                      'xkb_keymap_new_from_names':([C.c_void_p,C.POINTER(Names),C.c_int],C.c_void_p),
                      'xkb_keymap_key_by_name':([C.c_void_p,C.c_char_p],C.c_uint),
                      'xkb_keymap_key_get_syms_by_level':([C.c_void_p,C.c_uint,C.c_uint,C.c_uint,C.POINTER(C.POINTER(C.c_uint))],C.c_int),
                      'xkb_keysym_get_name':([C.c_uint,C.c_char_p,C.c_size_t],C.c_int),
                      'xkb_keysym_to_utf32':([C.c_uint],C.c_uint),
                      'xkb_keymap_unref':([C.c_void_p],None), 'xkb_context_unref':([C.c_void_p],None)}
        for name,(args,ret) in signatures.items():
            f=getattr(lib,name); f.argtypes=args; f.restype=ret
        self.context=lib.xkb_context_new(0)
        names=Names(*(device.get(n,'').encode() or None for n in ('rules','model','layout','variant','options')))
        self.keymap=lib.xkb_keymap_new_from_names(self.context,C.byref(names),0)
        if not self.keymap:
            self.close()
            raise RuntimeError('Cannot compile the active XKB keymap')
        self.group=device.get('active_layout_index',0)
        self.name=device.get('active_keymap',device.get('layout','us'))

    def key(self,name):
        code=self.lib.xkb_keymap_key_by_name(self.keymap,name.encode())
        syms=C.POINTER(C.c_uint)()
        count=self.lib.xkb_keymap_key_get_syms_by_level(self.keymap,code,self.group,0,C.byref(syms)) if code else 0
        if not count:
            return code, '', SPECIAL.get(name,name)
        buf=C.create_string_buffer(128)
        self.lib.xkb_keysym_get_name(syms[0],buf,len(buf))
        symbol=canonical(buf.value.decode())
        char=self.lib.xkb_keysym_to_utf32(syms[0])
        label=SPECIAL.get(name, chr(char).upper() if char >= 32 else symbol)
        return code, symbol, label

    def close(self):
        if getattr(self,'keymap',None): self.lib.xkb_keymap_unref(self.keymap); self.keymap=None
        if getattr(self,'context',None): self.lib.xkb_context_unref(self.context); self.context=None

class KeyboardView(Gtk.Box):
    def __init__(self, select, colors):
        super().__init__(orientation=Gtk.Orientation.VERTICAL,spacing=8)
        self.select=select; self.colors=colors; self.items=[]; self.keys=[]
        self.held=frozenset(); self.manual=set(); self.pressed=set(); self.all_layers=True
        self.device_signature=None; self.layout=None; self.stopped=threading.Event()
        self.sock=None; self.live=False
        toolbar=Gtk.Box(spacing=6)
        self.all_button=Gtk.ToggleButton(label='All layers',active=True)
        self.all_button.connect('toggled',self.all_toggled)
        toolbar.append(self.all_button)
        self.buttons={}
        for mod in ('SUPER','CTRL','SHIFT','ALT'):
            button=Gtk.ToggleButton(label=mod.title())
            button.connect('toggled',lambda b,m=mod:self.toggle_modifier(m,b.get_active()))
            toolbar.append(button); self.buttons[mod]=button
        self.append(toolbar)
        self.caption=Gtk.Label(label='Loading active keyboard layout…',xalign=0,wrap=True)
        self.caption.add_css_class('dim-label'); self.append(self.caption)
        scroll=Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.AUTOMATIC,vscrollbar_policy=Gtk.PolicyType.NEVER)
        self.area=Gtk.DrawingArea(content_width=760,content_height=235,hexpand=True)
        self.area.add_css_class('keyboard-map'); self.area.set_draw_func(self.draw)
        self.area.set_has_tooltip(True); self.area.connect('query-tooltip',self.tooltip)
        click=Gtk.GestureClick(); click.connect('released',self.clicked); self.area.add_controller(click)
        scroll.set_child(self.area); self.append(scroll)
        self.extras=Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,max_children_per_line=8)
        self.extra_expander=Gtk.Expander(label='Media, mouse & other keys')
        self.extra_expander.set_child(self.extras); self.append(self.extra_expander)
        self.refresh_layout()
        self.layout_timer=GLib.timeout_add_seconds(3,self.refresh_layout)
        threading.Thread(target=self.listen_modifiers,daemon=True).start()
        self.renew_lease()
        self.lease_timer=GLib.timeout_add_seconds(4,self.renew_lease)

    def set_live(self, enabled):
        self.live = enabled
        self.pressed.clear()
        self.renew_lease()
        self.repaint()

    def renew_lease(self):
        value = 'os.time() + 10' if self.live and not self.stopped.is_set() else '0'
        try:
            subprocess.run(['hyprctl', 'eval', '_omarchy_shortcuts_lease = ' + value],
                           capture_output=True, timeout=2)
        except subprocess.SubprocessError:
            pass
        return not self.stopped.is_set()

    def physical_key(self, code, state):
        if not self.live:
            return
        if state:self.pressed.add(code)
        else:self.pressed.discard(code)
        self.area.queue_draw()

    def stop(self):
        self.stopped.set()
        self.renew_lease()
        GLib.source_remove(self.lease_timer)
        if self.sock:
            try: self.sock.shutdown(socket.SHUT_RDWR)
            except OSError: pass
        GLib.source_remove(self.layout_timer)
        if self.layout: self.layout.close()

    def refresh_layout(self):
        try:
            keyboards=json.loads(subprocess.check_output(['hyprctl','-j','devices'],text=True,timeout=2))['keyboards']
            device=next((d for d in keyboards if d.get('main')),keyboards[0])
            signature=tuple(device.get(k) for k in ('layout','variant','options','model','rules','active_layout_index'))
            if signature!=self.device_signature:
                new=XkbLayout(device)
                if self.layout:self.layout.close()
                self.layout=new; self.device_signature=signature; self.build_keys()
        except Exception as e:
            self.caption.set_text('Keyboard layout unavailable: '+str(e))
        return not self.stopped.is_set()

    def build_keys(self):
        self.keys=[]
        def add(name,x,y,w=1,h=1):
            if name=='gap':return
            code,sym,label=self.layout.key(name)
            self.keys.append(dict(name=name,x=x,y=y,w=w,h=h,code=code,sym=sym,label=label))
        for row,entries in enumerate(ROWS):
            x=0
            for name,w in entries:add(name,x,row,w); x+=w
        for y,names in enumerate([['PRSC','SCLK','PAUS'],['INS','HOME','PGUP'],['DELE','END','PGDN']]):
            for x,name in enumerate(names):add(name,15.5+x,y)
        add('UP',16.5,4)
        for x,name in enumerate(['LEFT','DOWN','RGHT']):add(name,15.5+x,5)
        for y,names in enumerate([['NMLK','KPDV','KPMU','KPSU'],['KP7','KP8','KP9'],['KP4','KP5','KP6'],['KP1','KP2','KP3']]):
            for x,name in enumerate(names):add(name,19+x,y+1)
        add('KPAD',22,2,1,2);add('KPEN',22,4,1,2);add('KP0',19,5,2);add('KPDL',21,5)
        self.update_extras(); self.repaint()

    def set_items(self,items):
        self.items=items; self.update_extras(); self.repaint()

    def layer(self):
        if self.held:return self.held
        return None if self.all_layers else frozenset(self.manual)

    def bindings(self,symbol):
        layer=self.layer()
        return [r for r in self.items if split_shortcut(r['key'])[1]==symbol
                and (layer is None or split_shortcut(r['key'])[0]==layer)]

    def all_toggled(self,button):
        self.all_layers=button.get_active(); self.update_extras();self.repaint()

    def toggle_modifier(self,mod,active):
        if active:self.manual.add(mod)
        else:self.manual.discard(mod)
        self.all_button.set_active(False)
        self.all_layers=False; self.update_extras();self.repaint()

    def live_modifiers(self,mask):
        self.held=frozenset(name for bit,name in ((1,'SHIFT'),(4,'CTRL'),(8,'ALT'),(64,'SUPER')) if mask&bit)
        self.update_extras();self.repaint()

    def listen_modifiers(self):
        path=os.path.join(os.environ.get('XDG_RUNTIME_DIR',''), 'hypr',os.environ.get('HYPRLAND_INSTANCE_SIGNATURE',''),'.socket2.sock')
        while not self.stopped.is_set():
            try:
                with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as sock:
                    self.sock=sock;sock.connect(path);sock.settimeout(2)
                    # Subscribe first so startup cannot miss a modifier release.
                    value=subprocess.check_output(['hyprctl','repl','_omarchy_shortcuts_mods or 0'],text=True,timeout=2).strip()
                    GLib.idle_add(self.live_modifiers,int(value))
                    data=b''
                    while not self.stopped.is_set():
                        try:chunk=sock.recv(4096)
                        except socket.timeout:continue
                        if not chunk:break
                        data+=chunk
                        while b'\n' in data:
                            line,data=data.split(b'\n',1)
                            prefix=b'custom>>omarchy-shortcuts-mods,'
                            if line.startswith(prefix):GLib.idle_add(self.live_modifiers,int(line[len(prefix):]))
                            key_prefix=b'custom>>omarchy-shortcuts-key,'
                            if line.startswith(key_prefix):
                                code,state=map(int,line[len(key_prefix):].split(b','))
                                GLib.idle_add(self.physical_key,code,state)
            except (OSError,ValueError,subprocess.SubprocessError):pass
            self.stopped.wait(1)

    def update_extras(self):
        while child:=self.extras.get_first_child():self.extras.remove(child)
        mapped={k['sym'] for k in self.keys}
        extra=sorted({split_shortcut(r['key'])[1] for r in self.items}-mapped)
        for symbol in extra:
            rows=self.bindings(symbol)
            if not rows:continue
            button=Gtk.Button(label=f'{symbol} · {len(rows)}')
            button.set_has_tooltip(True)
            def show_tooltip(_widget, _x, _y, _keyboard, tooltip, items=rows):
                tooltip.set_custom(tooltip_widget(items, technical=False))
                return True
            button.connect('query-tooltip', show_tooltip)
            button.connect('clicked',lambda _,s=symbol:self.select(s,self.layer()))
            self.extras.append(button)
        self.extra_expander.set_label(f'Media, mouse & other keys · {len(extra)}')

    def repaint(self):
        layer=self.layer()
        label=' + '.join(sorted(layer)) if layer else ('All modifier combinations' if layer is None else 'No modifiers')
        if self.held:label='Live: '+label
        self.caption.set_text(f'{self.layout.name if self.layout else "Keyboard"} · {label} · Click a key to list actions · Keypresses are not saved')
        self.area.queue_draw()

    def geometry(self,width,height):
        return min(width/23.2,height/6.2)

    def hit(self,x,y):
        unit=self.geometry(self.area.get_width(),self.area.get_height())
        return next((k for k in self.keys if k['x']*unit<=x<(k['x']+k['w'])*unit and k['y']*unit<=y<(k['y']+k['h'])*unit),None)

    def tooltip(self,widget,x,y,keyboard,tooltip):
        key=self.hit(x,y)
        if not key:return False
        rows=self.bindings(key['sym'])
        if rows:
            tooltip.set_custom(tooltip_widget(rows, technical=False))
        else:
            tooltip.set_text(f"{key['label']} · No shortcuts in this layer")
        return True

    def clicked(self,gesture,n,x,y):
        key=self.hit(x,y)
        if not key:return
        if key['name'] in MOD_KEYS:
            button=self.buttons[MOD_KEYS[key['name']]];button.set_active(not button.get_active())
        else:self.select(key['sym'],self.layer())

    def draw(self,area,cr,width,height):
        colors=self.colors();unit=self.geometry(width,height)
        def color(name,alpha=1):
            value=colors[name].lstrip('#');cr.set_source_rgba(*(int(value[i:i+2],16)/255 for i in (0,2,4)),alpha)
        color('background');cr.paint()
        cr.select_font_face('Sans')
        for key in self.keys:
            rows=self.bindings(key['sym'])
            active=key['code'] in self.pressed or MOD_KEYS.get(key['name']) in self.held
            x,y=key['x']*unit+2,key['y']*unit+2;w,h=key['w']*unit-4,key['h']*unit-4
            color('selection' if active else 'lighter_background');cr.rectangle(x,y,w,h);cr.fill()
            color('accent' if rows or active else 'foreground',1 if rows or active else .2)
            cr.set_line_width(2 if active else 1);cr.rectangle(x+.5,y+.5,w-1,h-1);cr.stroke()
            color('foreground');cr.set_font_size(min(11,unit*.30))
            label=key['label']; ext=cr.text_extents(label)
            if ext.width>w-3:cr.set_font_size(min(11,unit*.30)*(w-3)/ext.width)
            ext=cr.text_extents(label);cr.move_to(x+(w-ext.width)/2-ext.x_bearing,y+h*.53);cr.show_text(label)
            if rows:
                color('accent');cr.set_font_size(8);cr.move_to(x+3,y+h-4);cr.show_text(str(len(rows)))
