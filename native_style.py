"""Read the installed shell's menu tokens and reproduce its scroll scrims."""
import math
import os
from pathlib import Path
import tomllib
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk

SHELL_THEME = Path.home()/'.local/state/omarchy/current/theme/shell.toml'

def menu_tokens():
    try: data = tomllib.loads(SHELL_THEME.read_text())
    except (OSError, ValueError): data = {}
    font, spacing = data.get('font', {}), data.get('spacing', {})
    base = float(font.get('base-size', 12))
    scale = float(spacing.get('scale', 1)) * (base/12 if spacing.get('scale-with-font', True) else 1)
    px = lambda n: max(1, math.floor(n + .5))
    space = lambda key, n: px(float(spacing.get(key, n*scale)))
    return dict(family=os.environ.get('OMARCHY_MENU_FONT') or 'monospace',
                size=px(float(font.get('heading', base*1.333))),
                title=px(float(font.get('title', base*1.167))),
                padding=space('panel-padding',18), gap=space('md',6),
                row=max(px(50*scale), px(float(font.get('body',base)))+space('row-padding-x',12)*2),
                row_gap=space('xs',3), inset=px(18*scale), fade=px(28*scale),
                header=max(px(34*scale),px(float(font.get('title',base*1.167)))+space('control-padding-y',6)*2),
                menu=data.get('menu', {}))

def folded_height(count, available, tokens):
    row, gap = tokens['row'], tokens['row_gap']
    total = count*(row+gap)-gap
    if count == 0: return row
    if total <= available: return total
    peek = math.floor(row*.55+.5)
    full = max(0, int((available+gap)//(row+gap)))
    while full > 1 and full*(row+gap)+peek > available: full -= 1
    return full*(row+gap)+peek if full else max(available,row)

class ScrollScrim(Gtk.Overlay):
    """Input-transparent, distance-based gradients matching Omarchy Menu.qml."""
    def __init__(self, scroll, enabled, background):
        super().__init__(vexpand=True)
        self.set_child(scroll)
        self.scroll, self.enabled, self.background = scroll, enabled, background
        scroll.add_css_class('scrim-scroll')
        self.scrim = Gtk.DrawingArea(can_target=False)
        self.scrim.set_draw_func(self.draw)
        self.add_overlay(self.scrim)
        adjustment = scroll.get_vadjustment()
        for signal in ('changed', 'value-changed'):
            adjustment.connect(signal, lambda *_: self.scrim.queue_draw())

    def draw(self, _area, cr, width, height):
        if not self.enabled() or not height: return
        import cairo
        color = Gdk.RGBA()
        if not color.parse(self.background()): return
        adjustment = self.scroll.get_vadjustment()
        depth = min(menu_tokens()['fade'], height/2)
        if depth <= 0: return
        for y, distance, top in ((0, adjustment.get_value()-adjustment.get_lower(), True),
                (height-depth, adjustment.get_upper()-adjustment.get_page_size()-adjustment.get_value(), False)):
            strength = max(0, min(1, distance/depth))
            gradient = cairo.LinearGradient(0,y,0,y+depth)
            gradient.add_color_stop_rgba(0,color.red,color.green,color.blue,strength if top else 0)
            gradient.add_color_stop_rgba(1,color.red,color.green,color.blue,0 if top else strength)
            cr.rectangle(0,y,width,depth); cr.set_source(gradient); cr.fill()


def border_css(data=None):
    """Resolve the same named border tokens used by Omarchy's Border.surfaceSpec."""
    import re
    if data is None:
        try: data = tomllib.loads(SHELL_THEME.read_text())
        except (OSError, ValueError): data = {}
    menu = data.get('menu', {})
    value = menu.get('border', data.get('hyprland', {}).get('active-border', '#3584e4'))
    for _ in range(4):
        if not isinstance(value, str) or '.' not in value: break
        section, key = value.split('.', 1)
        resolved = data.get(section, {}).get(key)
        if resolved is None: break
        value = resolved
    alpha = max(0, min(1, float(menu.get('border-alpha', 1))))
    colors = []
    for token in str(value).split():
        match = re.fullmatch(r'rgba?\(([0-9a-fA-F]{6,8})\)|#([0-9a-fA-F]{6,8})', token)
        if not match: continue
        hexcolor = match.group(1) or match.group(2)
        if len(hexcolor) not in (6,8): continue
        rgb = [int(hexcolor[i:i+2],16) for i in (0,2,4)]
        opacity = (int(hexcolor[6:8],16)/255 if len(hexcolor)==8 else 1)*alpha
        colors.append(f'rgba({rgb[0]},{rgb[1]},{rgb[2]},{opacity:.5f})')
    if not colors: colors = ['@accent_bg_color']
    angle = re.search(r'(-?\d+(?:\.\d+)?)deg', str(value))
    widths = str(menu.get('border-width', 2)).split()
    try: widths = [max(0,min(20,float(v))) for v in widths]
    except ValueError: widths = [2]
    if len(widths) not in (1,2,3,4): widths = [2]
    widths = (widths*4 if len(widths)==1 else widths*2 if len(widths)==2 else [*widths,widths[1]] if len(widths)==3 else widths)
    for i,side in enumerate(('top','right','bottom','left')):
        widths[i] = max(0,min(20,float(menu.get('border-width-'+side,widths[i]))))
    css = 'border-style: solid; border-width: '+' '.join(f'{v:g}px' for v in widths)+'; border-color: '+colors[0]+';'
    if len(colors)>1:
        css += ' border-image-source: linear-gradient('+ (angle.group(1) if angle else '0')+'deg, '+', '.join(colors)+'); border-image-slice: 1;'
    else: css += ' border-image-source: none;'
    return 'window.shortcuts-app { '+css+' }'
