"""Shared native Markdown and declarative keyboard illustrations (no HTML execution)."""
import json
import re
from pathlib import Path
from urllib.parse import urlparse
from gi.repository import Gtk, Gdk, GLib, Pango


def inline(text):
    tokens = re.compile(r'`([^`]+)`|\*\*(.+?)\*\*|__(.+?)__|~~(.+?)~~|\*([^*]+)\*|\[([^\]]+)\]\(([^\s)]+)\)')
    out=[]; end=0
    for match in tokens.finditer(text):
        out.append(GLib.markup_escape_text(text[end:match.start()]))
        code,bold,strong,strike,italic,label,url=match.groups()
        if code is not None: value='<tt>'+GLib.markup_escape_text(code)+'</tt>'
        elif bold or strong: value='<b>'+inline(bold or strong)+'</b>'
        elif strike: value='<s>'+inline(strike)+'</s>'
        elif italic: value='<i>'+inline(italic)+'</i>'
        elif urlparse(url).scheme in ('https','http','file'):
            value='<a href="'+GLib.markup_escape_text(url)+'">'+GLib.markup_escape_text(label)+'</a>'
        else: value=GLib.markup_escape_text(label)
        out.append(value);end=match.end()
    out.append(GLib.markup_escape_text(text[end:]));return ''.join(out)


def blocks(text):
    lines=text.splitlines();i=0
    while i<len(lines):
        line=lines[i]
        if not line.strip():i+=1;continue
        if line.lstrip().startswith('```'):
            language=line.strip()[3:].strip();i+=1;body=[]
            while i<len(lines) and not lines[i].lstrip().startswith('```'):body.append(lines[i]);i+=1
            yield 'code',language,'\n'.join(body);i+=1;continue
        if i+1<len(lines) and '|' in line and re.fullmatch(r'[\s|:\-]+',lines[i+1]) and '-' in lines[i+1]:
            rows=[[c.strip() for c in line.strip().strip('|').split('|')]];i+=2
            while i<len(lines) and '|' in lines[i] and lines[i].strip():
                rows.append([c.strip() for c in lines[i].strip().strip('|').split('|')]);i+=1
            yield 'table','',rows;continue
        heading=re.match(r'^(#{1,6})\s+(.+)',line)
        if heading:yield 'heading',len(heading[1]),heading[2];i+=1;continue
        if re.fullmatch(r'\s*(?:---+|\*\*\*+)\s*',line):yield 'rule','','';i+=1;continue
        if re.match(r'^\s*(?:[-*+] |\d+[.)] |>)',line):
            yield 'line','',re.sub(r'^(\s*)[-*+] ',r'\1• ',line);i+=1;continue
        paragraph=[line];i+=1
        while i<len(lines) and lines[i].strip() and not re.match(r'^\s*(?:```|#|[-*+] |\d+[.)] |>)',lines[i]):
            if i+1<len(lines) and '|' in lines[i] and re.fullmatch(r'[\s|:\-]+',lines[i+1]):break
            paragraph.append(lines[i]);i+=1
        yield 'paragraph','','\n'.join(paragraph)


class KeyboardSnippet(Gtk.DrawingArea):
    """A compact keyboard diagram; only data keys influence rendering."""
    def __init__(self, data, vignette=True):
        super().__init__(content_width=280, content_height=155, hexpand=True)
        self.keys={str(k).upper() for k in data.get('keys',[])[:20]}
        self.keys={'SUPER' if k in ('WIN','META') else 'CTRL' if k=='CONTROL' else 'ENTER' if k=='RETURN' else k for k in self.keys}
        self.vignette=vignette
        self.set_tooltip_text(str(data.get('label',''))[:300] or ' + '.join(sorted(self.keys)))
        self.update_property([Gtk.AccessibleProperty.LABEL],['Keyboard: '+' + '.join(sorted(self.keys))])
        self.set_draw_func(self.draw)

    @staticmethod
    def layout():
        """ANSI key widths keep every row on the same physical coordinate grid."""
        regular = lambda keys: [(key, 1) for key in keys]
        return [
            regular(['ESC', *list('1234567890'), '-', '=']) + [('BACKSPACE', 2)],
            [('TAB', 1.5)] + regular('QWERTYUIOP[]') + [('\\', 1.5)],
            [('CAPS', 1.75)] + regular("ASDFGHJKL;'") + [('ENTER', 2.25)],
            [('SHIFT', 2.25)] + regular('ZXCVBNM,./') + [('SHIFT', 2.75)],
            [('CTRL', 1.25), ('SUPER', 1.25), ('ALT', 1.25), ('SPACE', 6.25),
             ('ALT', 1.25), ('SUPER', 1.25), ('MENU', 1.25), ('CTRL', 1.25)],
        ]

    def draw(self, widget, cr, width, height):
        import cairo
        rows = self.layout()
        known = {key for row in rows for key, _ in row}
        extra = sorted(self.keys - known)
        if extra:
            rows = [*rows, [(key, 1.5) for key in extra[:10]]]
        cr.push_group()
        unit = min(width / 15, 28)
        h = min(24, (height - 12) / len(rows))
        left = (width - 15 * unit) / 2
        fg=self.get_style_context().get_color();cr.select_font_face('monospace');cr.set_font_size(min(9, unit * .34))
        for row, values in enumerate(rows):
            x = left
            for key, units in values:
                kw = unit * units - 3
                active = key in self.keys
                cr.new_path()
                if active: cr.set_source_rgba(.22,.49,.86,1)
                else: cr.set_source_rgba(fg.red,fg.green,fg.blue,.10)
                cr.rectangle(x,row*h+12,kw,h-3);cr.fill()
                cr.set_source_rgba(1,1,1,1) if active else cr.set_source_rgba(fg.red,fg.green,fg.blue,.8)
                label = {'BACKSPACE':'⌫', 'CAPS':'CAPS', 'ENTER':'↵', 'MENU':'≡'}.get(key, key)
                cr.move_to(x+2,row*h+12+(h-3)*.68);cr.show_text(label)
                x += unit * units
        surface=cr.pop_group();cr.set_source(surface)
        if self.vignette:
            mask=cairo.RadialGradient(width/2,height/2,30,width/2,height/2,max(width*.58,height))
            mask.add_color_stop_rgba(0,1,1,1,1);mask.add_color_stop_rgba(.65,1,1,1,.95);mask.add_color_stop_rgba(1,1,1,1,0)
            cr.mask(mask)
        else:cr.paint()


class MarkdownView(Gtk.Box):
    def __init__(self,text='',link=None,snippets=False,vignette=True,formatter=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL,spacing=10,hexpand=True)
        self._translation_skip=True
        self.link=link;self.snippets=snippets;self.vignette=vignette
        self.formatter=formatter or inline
        self.set_text(text)

    def label(self,text,markup=True):
        label=Gtk.Label(xalign=0,wrap=True,wrap_mode=Pango.WrapMode.WORD_CHAR,selectable=True,max_width_chars=60,hexpand=True)
        label._translation_skip=True
        if markup:label.set_markup(self.formatter(text))
        else:label.set_text(text)
        if self.link:label.connect('activate-link',self.link)
        return label

    def set_text(self,text):
        while child:=self.get_first_child():self.remove(child)
        for kind,meta,value in blocks(text):
            if kind=='rule':self.append(Gtk.Separator());continue
            if kind=='table':
                grid=Gtk.Grid(column_spacing=12,row_spacing=6)
                grid.add_css_class('markdown-table')
                for r,row in enumerate(value[:100]):
                    for c,cell in enumerate(row[:12]):
                        label=self.label(cell)
                        if r==0:label.add_css_class('heading')
                        grid.attach(label,c,r,1,1)
                height=min(240, max(60, len(value)*32))
                scroll=Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.AUTOMATIC,vscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
                    min_content_height=height,max_content_height=height,propagate_natural_height=True,vexpand=False,valign=Gtk.Align.START)
                scroll.set_child(grid);self.append(scroll);continue
            if kind=='code':
                if meta=='keyboard' and self.snippets:
                    try:
                        data=json.loads(value)
                        if not isinstance(data,dict) or not isinstance(data.get('keys'),list):raise ValueError()
                        self.append(KeyboardSnippet(data,self.vignette));continue
                    except (ValueError,TypeError):pass
                box=Gtk.Overlay();box.add_css_class('markdown-code')
                copy=Gtk.Button(icon_name='edit-copy-symbolic',halign=Gtk.Align.END,valign=Gtk.Align.START,tooltip_text=__import__('localization').text('Copy code'))
                copy.connect('clicked',lambda _,content=value:Gdk.Display.get_default().get_clipboard().set(content))
                label=self.label(value,False);label.add_css_class('monospace')
                label.set_margin_end(52);label.set_yalign(0)
                box.set_child(label);box.add_overlay(copy);box.set_measure_overlay(copy,True)
                self.append(box);continue
            label=self.label(value)
            if kind=='heading':label.add_css_class('title-3' if meta>1 else 'title-2')
            self.append(label)
