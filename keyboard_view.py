"""Layout-aware physical keyboard with live modifier layers and clickable keys."""
import cairo
import math
import ctypes as C
import ctypes.util
import json
import os
import socket
import subprocess
import threading
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf
from localization import text as tr
from shortcut_data import action_tooltip, split_shortcut, canonical, details, tooltip_widget, reveal_indicators_on_hover, make_switch_row

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

def draw_modifier(cr, modifier, x, y, size):
    """Font-independent modifier marks in a shared 12-unit icon box."""
    cr.save()
    # Cairo paths survive save/restore; discard the text cursor before arcs.
    cr.new_path()
    cr.translate(x, y)
    cr.scale(size / 12, size / 12)
    cr.set_line_width(1.3)
    cr.set_line_join(1)
    cr.set_line_cap(1)
    if modifier == 'SUPER':
        for left in (1, 7):
            for top in (1, 7):
                cr.rectangle(left, top, 4, 4)
        cr.fill()
    elif modifier == 'CTRL':
        cr.move_to(2, 8); cr.line_to(6, 4); cr.line_to(10, 8); cr.stroke()
    elif modifier == 'SHIFT':
        for index, point in enumerate([(6,1),(11,6),(8,6),(8,11),(4,11),(4,6),(1,6)]):
            (cr.move_to if index == 0 else cr.line_to)(*point)
        cr.close_path(); cr.stroke()
    elif modifier == 'ALT':
        cr.move_to(1,2); cr.line_to(4,2); cr.line_to(8,10); cr.line_to(11,10)
        cr.move_to(7,2); cr.line_to(11,2); cr.stroke()
    else:
        cr.arc(6,6,4,0,6.2831853); cr.stroke()
        cr.move_to(2,10); cr.line_to(10,2); cr.stroke()
    cr.restore()


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
    def __init__(self, select, colors, preferences=None, save_preferences=None, row_factory=None, section_factory=None, item_state=None, preview=False):
        super().__init__(orientation=Gtk.Orientation.VERTICAL,spacing=8)
        self.select=select; self.colors=colors; self.items=[]; self.keys=[]
        self.held=frozenset(); self.manual=set(); self.pressed=set(); self.all_layers=True
        self.device_signature=None; self.layout=None; self.stopped=threading.Event()
        self.sock=None; self.live=False
        self.lease_lock = threading.Lock()
        self.lease_worker_running = False
        self.lease_requested = False
        preferences = preferences or {}
        self.show_numpad = preferences.get('show_numpad') is True
        self.fit_width = preferences.get('fit_width') is True
        self.raised_keys = preferences.get('raised_keys') is True
        self.key_overlay = preferences.get('key_overlay', False) is True
        self.save_preferences = save_preferences
        self.icon_cache = {}
        self.row_factory = row_factory
        self.section_factory = section_factory
        self.item_state = item_state or (lambda item: (False, False))
        self.extras_layout = preferences.get('extras_layout', 'grid' if preferences.get('columns', True) else 'list')
        if self.extras_layout not in ('list', 'columns', 'grid'): self.extras_layout = 'grid'
        self.columns = self.extras_layout == 'grid'
        self.extras_expanded = preferences.get('extras_expanded', False) is True
        self.all_layers = preferences.get('all_layers', True) is True
        self.manual = set(preferences.get('manual', [])) & {'SUPER', 'CTRL', 'SHIFT', 'ALT'}
        # The scrolled viewport clips outlines outside its allocation.
        # Reserve space around controls for GTK's outward focus ring.
        toolbar=Gtk.Box(spacing=10, margin_top=6, margin_bottom=6,
                        margin_start=6, margin_end=6)
        all_control = Gtk.Box(spacing=8, margin_end=10)
        all_control.append(Gtk.Label(label='All layers'))
        self.all_button=Gtk.Switch(active=self.all_layers, valign=Gtk.Align.CENTER)
        action_tooltip(self.all_button, 'Include every modifier combination containing the selected modifiers. Off matches the selected combination exactly (Ctrl+Shift+A)')
        self.all_button.connect('notify::active',self.all_toggled)
        all_control.append(self.all_button)
        make_switch_row(all_control, self.all_button)
        self.layer_control = all_control
        toolbar.append(all_control)
        modifiers = Gtk.Box(spacing=0)
        self.modifier_group = modifiers
        modifiers.add_css_class("linked")
        toolbar.append(modifiers)
        self.buttons={}
        for mod in ('SUPER','CTRL','SHIFT','ALT'):
            button=Gtk.ToggleButton(label=mod.title(), active=mod in self.manual)
            button.connect('toggled',lambda b,m=mod:self.toggle_modifier(m,b.get_active()))
            button.set_tooltip_text(f'Include {mod.title()} in the modifier filter. Combine with other modifier buttons.')
            modifiers.append(button); self.buttons[mod]=button
        self.option_buttons = {}
        for label, field in (('Numpad', 'show_numpad'), ('Fit width', 'fit_width'), ('Key overlay', 'key_overlay'), ('Raised keys', 'raised_keys')):
            button = Gtk.Switch(active=getattr(self, field), valign=Gtk.Align.CENTER)
            if field == 'raised_keys':
                action_tooltip(button, tr('Raised keycaps with illuminated bindings'))
            elif field == 'key_overlay':
                action_tooltip(button, 'Show modifier icons on keys and their legend (Ctrl+Shift+O)')
            else:
                action_tooltip(button, 'Show the numeric keypad to the right of the main keyboard (Ctrl+Shift+N)' if field == 'show_numpad' else 'Scale the keyboard to fit the window width (Ctrl+Shift+W)')
            self.option_buttons[field] = button
            button.connect('notify::active', lambda b, _pspec, name=field: self.option_changed(b, name))
            if field == 'key_overlay':
                control = Gtk.Box(spacing=8)
                control.append(Gtk.Label(label=label))
                control.append(button)
                make_switch_row(control, button)
                toolbar.append(control)
        self.toolbar = toolbar
        self.append(toolbar)
        self.caption=Gtk.Label(label='Loading active keyboard layout…',xalign=0,wrap=True)
        self.caption.add_css_class('dim-label'); self.append(self.caption)
        scroll=Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.AUTOMATIC,vscrollbar_policy=Gtk.PolicyType.NEVER)
        self.scroll = scroll
        self.area=Gtk.DrawingArea(content_width=760,content_height=246,hexpand=True)
        self.area.connect('resize', self.resize_keyboard)
        self.area.add_css_class('keyboard-map'); self.area.set_draw_func(self.draw)
        self.area.set_has_tooltip(True); self.area.connect('query-tooltip',self.tooltip)
        click=Gtk.GestureClick(); click.connect('released',self.clicked); self.area.add_controller(click)
        scroll.set_child(self.area); self.append(scroll)
        self.legend = Gtk.Box(spacing=16, visible=self.all_layers and self.key_overlay, margin_top=0, margin_bottom=2)
        for modifier, title in [('SUPER', 'Super'), ('CTRL', 'Ctrl'), ('SHIFT', 'Shift'), ('ALT', 'Alt'), ('NONE', 'No modifier')]:
            entry = Gtk.Box(spacing=6)
            mark = Gtk.DrawingArea(content_width=14, content_height=14, valign=Gtk.Align.CENTER)
            def draw_mark(area, cr, width, height, mod=modifier):
                value = self.colors()['foreground'].lstrip('#')
                cr.set_source_rgb(*(int(value[i:i+2],16)/255 for i in (0,2,4)))
                draw_modifier(cr, mod, 0, 0, 14)
            mark.set_draw_func(draw_mark)
            entry.append(mark)
            label = Gtk.Label(label=title)
            label.add_css_class('dim-label')
            entry.append(label)
            self.legend.append(entry)
        self.append(self.legend)
        self.extras_host = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.append(self.extras_host)
        if preview:
            self.fit_width = True
            self.layout = XkbLayout({'layout':'us'})
            self.build_keys()
            self.area.set_size_request(330, 118)
            self.area.set_content_height(118)
            return
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
        # Serialize/coalesce IPC in a worker: shell timeouts must never block GTK.
        with self.lease_lock:
            self.lease_requested = True
            if self.lease_worker_running:
                return not self.stopped.is_set()
            self.lease_worker_running = True
        def work():
            while True:
                with self.lease_lock:
                    if not self.lease_requested:
                        self.lease_worker_running = False
                        return
                    self.lease_requested = False
                active = self.live and not self.stopped.is_set()
                suppress = getattr(self, 'suppress_guide', self.live) and not self.stopped.is_set()
                value = 'os.time() + 10' if active else '0'
                for command in (
                    ['hyprctl', 'eval', '_bindlume_lease = ' + value],
                    ['omarchy-shell', 'keyguide', 'keyboardView', 'true' if suppress else 'false'],
                ):
                    try:
                        subprocess.run(command, capture_output=True, timeout=2)
                    except (OSError, subprocess.SubprocessError):
                        pass
        threading.Thread(target=work, daemon=True).start()
        return not self.stopped.is_set()

    def physical_key(self, code, state):
        if not self.live:
            return
        if state:self.pressed.add(code)
        else:self.pressed.discard(code)
        self.area.queue_draw()

    def stop(self):
        self.stopped.set()
        if hasattr(self, 'lease_timer'):
            self.renew_lease()
            GLib.source_remove(self.lease_timer)
        if self.sock:
            try: self.sock.shutdown(socket.SHUT_RDWR)
            except OSError: pass
        if hasattr(self, 'layout_timer'): GLib.source_remove(self.layout_timer)
        if self.layout: self.layout.close()

    def refresh_layout(self):
        if getattr(self, '_layout_busy', False): return not self.stopped.is_set()
        self._layout_busy = True
        def loaded(device, error):
            self._layout_busy = False
            if self.stopped.is_set(): return False
            if device is None:
                self.caption.set_text('Keyboard layout unavailable: '+error)
                return False
            signature=tuple(device.get(k) for k in ('layout','variant','options','model','rules','active_layout_index'))
            if signature != self.device_signature:
                new=XkbLayout(device)
                if self.layout:self.layout.close()
                self.layout=new;self.device_signature=signature;self.build_keys()
            return False
        def worker():
            try:
                keyboards=json.loads(subprocess.check_output(['hyprctl','-j','devices'],text=True,timeout=2))['keyboards']
                device=next((d for d in keyboards if d.get('main')),keyboards[0])
                GLib.idle_add(loaded,device,'')
            except Exception as error:GLib.idle_add(loaded,None,str(error))
        threading.Thread(target=worker,daemon=True).start()
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
        if not self.show_numpad:
            self.keys = [k for k in self.keys if k['x'] < 19]
        self.resize_keyboard()
        self.update_extras(); self.repaint()

    def option_changed(self, button, field):
        setattr(self, field, button.get_active())
        if self.layout:
            self.build_keys()
        self.persist()

    def persist(self):
        if self.save_preferences:
            self.save_preferences(dict(raised_keys=self.raised_keys, show_numpad=self.show_numpad, fit_width=self.fit_width, key_overlay=self.key_overlay,
                                       columns=self.columns, extras_layout=self.extras_layout, extras_expanded=self.extras_expanded,
                                       all_layers=self.all_layers, manual=sorted(self.manual)))

    def resize_keyboard(self, *_):
        columns = 23.2 if self.show_numpad else 18.7
        self.area.set_content_width(0 if self.fit_width else round(columns * 41))
        self.scroll.set_policy(Gtk.PolicyType.NEVER if self.fit_width else Gtk.PolicyType.AUTOMATIC,
                               Gtk.PolicyType.NEVER)
        width = self.area.get_width()
        unit = width / columns if width else 41
        if not self.fit_width: unit = min(41, unit)
        self.area.set_content_height(max(1, round(unit * 6)))
        self.area.queue_draw()

    def set_items(self,items):
        self.items=items; self.update_extras(); self.repaint()

    def layer(self):
        selected = frozenset(self.manual) | self.held
        return None if self.all_layers and not selected else selected

    def bindings(self,symbol):
        layer=self.layer()
        return [r for r in self.items if split_shortcut(r['key'])[1]==symbol
                and (layer is None or (layer <= split_shortcut(r['key'])[0] if self.all_layers else split_shortcut(r['key'])[0] == layer))]

    def all_toggled(self,button,*_):
        self.all_layers=button.get_active(); self.update_extras();self.repaint(); self.persist()

    def toggle_modifier(self,mod,active):
        if active:self.manual.add(mod)
        else:self.manual.discard(mod)
        self.update_extras();self.repaint(); self.persist()

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
                    value=subprocess.check_output(['hyprctl','repl','_bindlume_mods or 0'],text=True,timeout=2).strip()
                    GLib.idle_add(self.live_modifiers,int(value))
                    data=b''
                    while not self.stopped.is_set():
                        try:chunk=sock.recv(4096)
                        except socket.timeout:continue
                        if not chunk:break
                        data+=chunk
                        while b'\n' in data:
                            line,data=data.split(b'\n',1)
                            prefix=b'custom>>bindlume-mods,'
                            if line.startswith(prefix):GLib.idle_add(self.live_modifiers,int(line[len(prefix):]))
                            key_prefix=b'custom>>bindlume-key,'
                            if line.startswith(key_prefix):
                                code,state=map(int,line[len(key_prefix):].split(b','))
                                GLib.idle_add(self.physical_key,code,state)
            except (OSError,ValueError,subprocess.SubprocessError):pass
            self.stopped.wait(1)

    def update_extras(self):
        if not hasattr(self, 'extras_host'): return
        while child := self.extras_host.get_first_child(): self.extras_host.remove(child)
        mapped = {k['sym'] for k in self.keys}
        layer = self.layer()
        items = [r for r in self.items if split_shortcut(r['key'])[1] not in mapped
                 and (layer is None or (layer <= split_shortcut(r['key'])[0] if self.all_layers else split_shortcut(r['key'])[0] == layer))]
        self.extra_count = len(items)
        if not self.section_factory: return
        def expanded(section):
            self.extras_expanded = section.get_expanded()
            self.persist()
        section = self.section_factory('Media, mouse & other keys', len(items),
                                       self.extras_expanded, expanded)
        self.extra_expander = section
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                       margin_top=10, margin_bottom=10, margin_start=10, margin_end=10)
        controls = Gtk.Box(spacing=8)
        controls.append(Gtk.Label(label='Layout', xalign=0))
        mode = Gtk.DropDown.new_from_strings(['List', 'Columns', 'Grid'])
        mode.set_selected(['list', 'columns', 'grid'].index(self.extras_layout))
        def layout_changed(button, *_):
            self.extras_layout = ['list', 'columns', 'grid'][button.get_selected()]
            self.columns = self.extras_layout == 'grid'
            self.persist()
            self.update_extras()
        mode.connect('notify::selected', layout_changed)
        controls.append(mode)
        body.append(controls)
        if not items:
            body.append(Gtk.Label(label='No other shortcuts match this layer and filters.', xalign=0))
        elif self.extras_layout != 'grid' and self.row_factory:
            rows = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
            rows.add_css_class('shortcut-list')
            for item in items: rows.append(self.row_factory(item, columns=self.extras_layout == 'columns'))
            body.append(rows)
        else:
            flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
                               row_spacing=10, column_spacing=10,
                               min_children_per_line=1, max_children_per_line=3)
            for item in items:
                button = Gtk.Button()
                content = Gtk.Box(spacing=10)
                text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, hexpand=True)
                text.append(Gtk.Label(label=item['name'], xalign=0, wrap=True, max_width_chars=25))
                key = Gtk.Label(label=item.get('display_key', item['key']), xalign=0, wrap=True, max_width_chars=25)
                key.add_css_class('shortcut-key')
                text.append(key)
                content.append(text)
                favorite, hidden = self.item_state(item)
                indicators = []
                for icon_name, description, active in [
                    ('starred-symbolic' if favorite else 'non-starred-symbolic', 'Bookmarked' if favorite else 'Not bookmarked', favorite),
                    ('view-conceal-symbolic' if hidden else 'view-reveal-symbolic', 'Hidden' if hidden else 'Not hidden', hidden)]:
                    icon = Gtk.Image(icon_name=icon_name, valign=Gtk.Align.CENTER)
                    icon.set_tooltip_text(description)
                    icon.set_visible(getattr(self, 'indicator_features', (True, True))[len(indicators)])
                    content.append(icon)
                    indicators.append((icon, active))
                reveal_indicators_on_hover(button, indicators)
                button.shortcut_id = item['id']
                def update_marks(card=button, record=item):
                    bookmarked, hidden = self.item_state(record)
                    star, eye = [widget for widget, _ in card.indicators]
                    star.set_from_icon_name('starred-symbolic' if bookmarked else 'non-starred-symbolic')
                    eye.set_from_icon_name('view-conceal-symbolic' if hidden else 'view-reveal-symbolic')
                    star.set_tooltip_text('Bookmarked' if bookmarked else 'Not bookmarked')
                    eye.set_tooltip_text('Hidden' if hidden else 'Not hidden')
                    card.indicators[:] = [(star, bookmarked), (eye, hidden)]
                    card.refresh_indicators()
                button.refresh_marks = update_marks
                button.set_child(content)
                def show_tip(_widget, _x, _y, _keyboard, tooltip, row=item):
                    tooltip.set_custom(tooltip_widget([row], technical=False))
                    return True
                button.set_has_tooltip(True)
                button.connect('query-tooltip', show_tip)
                button.connect('clicked', lambda _, row=item: self.select(*reversed(split_shortcut(row['key']))))
                flow.append(button)
            body.append(flow)
        section.set_child(body)
        self.extras_host.append(section)

    def repaint(self):
        layer=self.layer()
        label=' + '.join(sorted(layer)) if layer else ('All modifier combinations' if layer is None else 'No modifiers')
        if self.all_layers and layer: label += ' · including additional modifiers'
        if self.held:label='Live: '+label
        if hasattr(self, 'legend'): self.legend.set_visible(self.all_layers and self.key_overlay)
        self.caption.set_text(f'{self.layout.name if self.layout else "Keyboard"} · {label} · Click a key to list actions')
        self.area.queue_draw()

    def geometry(self,width,height):
        columns = 23.2 if self.show_numpad else 18.7
        return width / columns if self.fit_width else min(41, width / columns, height / 6)

    def surface_transform(self, width, height):
        # The same affine plane is used for painting and pointer hit testing.
        if not self.raised_keys:
            return cairo.Matrix()
        return cairo.Matrix(xx=.94, yy=.88, xy=-.045, x0=width*.035+height*.045, y0=height*.035)

    def hit(self,x,y):
        inverse=self.surface_transform(self.area.get_width(), self.area.get_height())
        inverse.invert()
        x,y=inverse.transform_point(x,y)
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
        else:self.select(key['sym'],self.layer(),self.all_layers)

    def icon_pixbuf(self, source):
        if source not in self.icon_cache:
            try:
                path = source
                if not os.path.isabs(path):
                    theme = Gtk.IconTheme.get_for_display(self.get_display())
                    icon = theme.lookup_icon(source, None, 32, 1, Gtk.TextDirection.NONE, Gtk.IconLookupFlags.PRELOAD)
                    file = icon.get_file()
                    path = file.get_path() if file else None
                self.icon_cache[source] = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 32, 32, True) if path else None
            except (GLib.Error, TypeError):
                self.icon_cache[source] = None
        return self.icon_cache[source]

    def draw(self,area,cr,width,height):
        colors=self.colors();unit=self.geometry(width,height)
        def color(name,alpha=1):
            value=colors[name].lstrip('#');cr.set_source_rgba(*(int(value[i:i+2],16)/255 for i in (0,2,4)),alpha)
        color('background');cr.paint()
        cr.save()
        cr.transform(self.surface_transform(width,height))
        def rounded(x,y,w,h,r):
            cr.new_sub_path()
            for cx,cy,a in ((x+w-r,y+r,-math.pi/2),(x+w-r,y+h-r,0),(x+r,y+h-r,math.pi/2),(x+r,y+r,math.pi)):
                cr.arc(cx,cy,r,a,a+math.pi/2)
            cr.close_path()
        cr.select_font_face('Sans')
        for key in self.keys:
            cr.select_font_face('Sans')
            rows=self.bindings(key['sym'])
            active=key['code'] in self.pressed or MOD_KEYS.get(key['name']) in (self.held | self.manual)
            x,y=key['x']*unit+2,key['y']*unit+2;w,h=key['w']*unit-4,key['h']*unit-4
            if self.raised_keys:
                depth=max(2,unit*.09); radius=min(6,unit*.15)
                if rows or active:
                    color('accent',.12 if rows else .2)
                    rounded(x-2,y-2,w+4,h+depth+4,radius+2);cr.fill()
                color('foreground',.22)
                rounded(x,y+depth,w,h,radius);cr.fill()
                if active:y+=depth*.65
                color('accent' if active else 'lighter_background')
                rounded(x,y,w,h,radius);cr.fill()
                if rows and not active:
                    color('accent',.18);rounded(x,y,w,h,radius);cr.fill()
                color('accent' if rows or active else 'foreground',.85 if rows or active else .2)
                cr.set_line_width(1);rounded(x+.5,y+.5,w-1,h-1,radius);cr.stroke()
                cr.set_source_rgba(1,1,1,.15);cr.move_to(x+radius,y+1);cr.line_to(x+w-radius,y+1);cr.stroke()
            else:
                color('selection' if active else 'lighter_background');cr.rectangle(x,y,w,h);cr.fill()
                color('accent' if rows or active else 'foreground',1 if rows or active else .2)
                cr.set_line_width(2 if active else 1);cr.rectangle(x+.5,y+.5,w-1,h-1);cr.stroke()
            color('foreground')
            if self.raised_keys and active:
                rgb=[int(colors['accent'].lstrip('#')[i:i+2],16)/255 for i in (0,2,4)]
                linear=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in rgb]
                light=sum(v*w for v,w in zip(linear,(.2126,.7152,.0722)))>.179
                cr.set_source_rgb(*((.04,.035,.025) if light else (1,1,1)))
            cr.set_font_size(min(11,unit*.30))
            icons = list(dict.fromkeys(r.get('app_icon') for r in rows if r.get('app_icon')))
            pixbufs = [p for source in icons if (p := self.icon_pixbuf(source)) is not None]
            label=key['label']; ext=cr.text_extents(label)
            if ext.width>w-3:cr.set_font_size(min(11,unit*.30)*(w-3)/ext.width)
            ext=cr.text_extents(label);cr.move_to(x+(w-ext.width)/2-ext.x_bearing,y+h*(.30 if pixbufs or (rows and self.all_layers and self.key_overlay) else .53));cr.show_text(label)
            if pixbufs:
                size = min(20, h * (.32 if self.all_layers and self.key_overlay else .48), w * .55)
                count = min(len(pixbufs), max(1, int((w - 4) / (size + 2))))
                left = x + (w - count * (size + 2) + 2) / 2
                for index, pixbuf in enumerate(pixbufs[:count]):
                    cr.save()
                    cr.translate(left + index * (size + 2), y + h - size - (12 if self.all_layers and self.key_overlay else 3))
                    cr.scale(size / pixbuf.get_width(), size / pixbuf.get_height())
                    Gdk.cairo_set_source_pixbuf(cr, pixbuf, 0, 0)
                    cr.paint()
                    cr.restore()
            if rows and self.key_overlay:
                color('accent')
                cr.set_font_size(8)
                if self.all_layers:
                    color('foreground', .55)
                    layers = [split_shortcut(r['key'])[0] for r in rows]
                    modifiers = [mod for mod in ('SUPER', 'CTRL', 'SHIFT', 'ALT')
                                 if any(mod in layer for layer in layers)]
                    if any(not layer for layer in layers): modifiers.append('NONE')
                    gap = 2
                    size = min(10, (w - 6 - gap * (len(modifiers) - 1)) / max(1, len(modifiers)))
                    left = x + (w - len(modifiers) * (size + gap) + gap) / 2
                    for index, modifier in enumerate(modifiers):
                        draw_modifier(cr, modifier, left + index * (size + gap), y + h - size - 2, size)
                else:
                    cr.move_to(x+3,y+h-4);cr.show_text(str(len(rows)))

        cr.restore()
