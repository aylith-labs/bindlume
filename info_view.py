"""Rich, linked documentation with asynchronous native resource previews."""
from pathlib import Path
from urllib.parse import urlparse, unquote, urljoin
from urllib.request import Request, urlopen
from html.parser import HTMLParser
import mimetypes
import re
import threading
import json
import subprocess
import os
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gio, GLib, Gdk, Pango

LIMIT = 512 * 1024
TOKEN = re.compile(r'https?://[^\s<>]+|(?<![\w:])(?:~/|/)[^\s<>]+|\b[\w.-]+\.(?:py|lua|md|json|toml|desktop)\b')


def target_uri(token, project):
    token = token.rstrip('.,;:)')
    if token.startswith(('https://', 'http://')):
        return token
    if token.startswith(('~/', '/')):
        return Path(token).expanduser().as_uri()
    candidate = project / token
    if not candidate.exists():
        candidate = Path.home() / '.codex/skills/omarchy' / token
    return candidate.as_uri() if candidate.exists() else None


def linked_markup(text, project, base=None):
    """Escape prose, link Markdown links and known local resources safely."""
    pieces = []
    pattern = re.compile(r'\[([^\]]+)\]\(([^)]+)\)|`([^`]+)`|\*\*([^*]+)\*\*|' + TOKEN.pattern)
    offset = 0
    for match in pattern.finditer(text):
        pieces.append(GLib.markup_escape_text(text[offset:match.start()]))
        raw = match.group(0)
        if match.group(1):
            label, target = match.group(1), match.group(2)
            uri = urljoin(base, target) if base else target_uri(target, project)
            if uri is None:
                uri = (project / target).resolve().as_uri()
        elif match.group(3):
            value = match.group(3)
            uri = target_uri(value, project)
            label = value
            if not uri:
                pieces.append('<tt>' + GLib.markup_escape_text(value) + '</tt>')
                offset = match.end(); continue
        elif match.group(4):
            pieces.append('<b>' + GLib.markup_escape_text(match.group(4)) + '</b>')
            offset = match.end(); continue
        else:
            label = raw.rstrip('.,;:)')
            uri = target_uri(label, project)
        if uri and urlparse(uri).scheme in ('http', 'https', 'file'):
            pieces.append(f'<a href="{GLib.markup_escape_text(uri)}">{GLib.markup_escape_text(label)}</a>')
            if raw.startswith(label):
                pieces.append(GLib.markup_escape_text(raw[len(label):]))
        else:
            pieces.append(GLib.markup_escape_text(raw))
        offset = match.end()
    pieces.append(GLib.markup_escape_text(text[offset:]))
    return ''.join(pieces)


class ReadableHTML(HTMLParser):
    """Extract a bounded readable page with headings, paragraphs and links."""
    def __init__(self, base):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.parts = []
        self.title = ''
        self.in_title = False
        self.skip = 0
        self.link_stack = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag in ('script', 'style', 'svg', 'noscript', 'nav', 'footer'):
            self.skip += 1
        if self.skip: return
        if tag == 'title': self.in_title = True
        if tag in ('p', 'div', 'article', 'section', 'br', 'li', 'h1', 'h2', 'h3'):
            self.parts.append('\n')
        if tag in ('h1', 'h2', 'h3'): self.parts.append('## ')
        if tag == 'li': self.parts.append('• ')
        if tag == 'a':
            self.link_stack.append(urljoin(self.base, values.get('href', '')))
            self.parts.append('[')

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'svg', 'noscript', 'nav', 'footer') and self.skip:
            self.skip -= 1
            return
        if self.skip: return
        if tag == 'title': self.in_title = False
        if tag == 'a' and self.link_stack:
            self.parts.append('](' + self.link_stack.pop() + ')')
        if tag in ('p', 'div', 'article', 'section', 'li', 'h1', 'h2', 'h3'):
            self.parts.append('\n\n')

    def handle_data(self, data):
        if self.skip: return
        value = re.sub(r'\s+', ' ', data)
        if self.in_title:
            self.title += value
        else:
            self.parts.append(value)

    def text(self):
        return re.sub(r'\n[ \t]*\n(?:[ \t]*\n)+', '\n\n', ''.join(self.parts)).strip()


def load_preview(uri):
    """Read previews without executing files or page scripts."""
    parsed = urlparse(uri)
    if parsed.scheme == 'file':
        if parsed.netloc not in ('', 'localhost'):
            raise ValueError('Remote file hosts are not supported.')
        path = Path(unquote(parsed.path))
        if not path.exists():
            return dict(kind='message', title=path.name, meta=str(path), text='This file does not exist yet. Settings files are created when their preferences are first saved.')
        if path.is_dir():
            entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.casefold()))
            return dict(kind='directory', title=path.name or str(path), meta=f'{path}\n{len(entries)} entries',
                        entries=[(p.name + ('/' if p.is_dir() else ''), p.as_uri()) for p in entries[:250]])
        size = path.stat().st_size
        mime = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
        meta = f'{path}\n{mime} · {size:,} bytes'
        if mime.startswith('image/'):
            return dict(kind='image', title=path.name, meta=meta, path=str(path))
        with path.open('rb') as stream: data = stream.read(LIMIT + 1)
        if b'\0' in data[:8192]:
            return dict(kind='message', title=path.name, meta=meta, text='Binary file. Use Open Externally to view it in its associated application.')
        text = data[:LIMIT].decode('utf-8', errors='replace')
        if len(data) > LIMIT: text += '\n\n[Preview limited to 512 KiB]'
        return dict(kind='markdown' if path.suffix.lower() == '.md' else 'text', title=path.name, meta=meta, text=text, base=uri)
    if parsed.scheme not in ('http', 'https'):
        raise ValueError('Only file, HTTP and HTTPS links can be previewed.')
    request = Request(uri, headers={'User-Agent': 'OmarchyShortcuts/1.0 (readable preview)', 'Accept': 'text/html,text/plain,image/*'})
    with urlopen(request, timeout=15) as response:
        final = response.url
        mime = response.headers.get_content_type()
        charset = response.headers.get_content_charset() or 'utf-8'
        data = response.read(LIMIT + 1)
    if mime.startswith('image/'):
        return dict(kind='image-bytes', title=Path(urlparse(final).path).name or 'Image', meta=final, data=data[:LIMIT])
    if mime not in ('text/html','application/xhtml+xml') and not mime.startswith('text/'):
        return dict(kind='message', title=Path(urlparse(final).path).name or 'Resource', meta=f'{final}\n{mime}', text='This resource needs its associated application. Use Open Externally to view it.')
    text = data[:LIMIT].decode(charset, errors='replace')
    if mime in ('text/html','application/xhtml+xml'):
        parser = ReadableHTML(final); parser.feed(text)
        text = parser.text()
        title = parser.title.strip() or urlparse(final).netloc
        kind = 'markdown'
    else:
        title = Path(urlparse(final).path).name or urlparse(final).netloc
        kind = 'text'
    if len(data) > LIMIT: text += '\n\n[Preview limited to 512 KiB]'
    return dict(kind=kind, title=title, meta=final + '\nReadable web preview · scripts and interactive content are omitted', text=text or 'No readable page content found.', base=final)


def local_preview_path(uri):
    parsed = urlparse(uri)
    if parsed.scheme == 'file' and parsed.netloc in ('', 'localhost'):
        return Path(unquote(parsed.path))
    return None


def reveal_file(uri):
    path = local_preview_path(uri)
    if path is None:
        raise ValueError('Show in Folder is available for local files only.')
    if path.exists():
        subprocess.Popen(['nautilus', '--select', str(path)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif path.parent.is_dir():
        Gio.AppInfo.launch_default_for_uri(path.parent.as_uri(), None)
    else:
        raise FileNotFoundError('The containing folder does not exist.')


def preview_actions(uri):
    path = local_preview_path(uri)
    actions = [('Open Externally', 'open')]
    if path is not None:
        if not path.is_dir():
            actions.append(('Show in Folder', 'reveal'))
        actions.extend([('Copy Path', 'copy-path'), ('Copy File URI', 'copy-link')])
    else:
        actions.append(('Copy URL', 'copy-link'))
    return actions


def copy_plain_text(value):
    # wl-copy retains ownership in its own process after the Info dialog closes.
    subprocess.run(['wl-copy', '--type', 'text/plain;charset=utf-8'], input=value,
                   text=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   timeout=3, check=True)


def dialog_size(width, height):
    """Logical pixels, with room for panel and compositor borders."""
    return max(1, min(1060, width - 48)), max(1, min(700, height - 48))


def available_area(owner):
    display = owner.window.get_display()
    surface = owner.window.get_surface()
    monitor = display.get_monitor_at_surface(surface) if surface else display.get_monitors().get_item(0)
    geometry = monitor.get_geometry()
    width, height = geometry.width, geometry.height
    try:
        monitors = json.loads(subprocess.check_output(['hyprctl', '-j', 'monitors'], text=True, timeout=2))
        current = next(m for m in monitors if m['name'] == monitor.get_connector())
        left, top, right, bottom = current.get('reserved', [0, 0, 0, 0])
        width -= left + right
        height -= top + bottom
    except (subprocess.SubprocessError, ValueError, StopIteration, KeyError):
        pass
    return width, height


class InfoWindow(Gtk.Window):
    def __init__(self, owner, sections, project, settings):
        width, height = dialog_size(*available_area(owner))
        super().__init__(title='About Omarchy Shortcuts', transient_for=owner.window, application=owner,
                         modal=True, default_width=width, default_height=height)
        self.connect('map', lambda *_: GLib.timeout_add(150, self.center_on_monitor))
        self.owner=owner; self.project=project; self.history=[]; self.index=-1; self.generation=0
        self.connect('close-request', self.closed)
        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect('key-pressed', self.key_pressed)
        self.add_controller(keys)
        root=Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, margin_top=18, margin_bottom=18, margin_start=18, margin_end=18)
        self.set_child(root)
        header=Gtk.Box(spacing=12)
        title=Gtk.Label(label='Inside Omarchy Shortcuts', xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.END, width_chars=1)
        title.add_css_class('title-1'); header.append(title)
        close=Gtk.Button(label='Close');close.connect('clicked',lambda *_:self.close());header.append(close)
        root.append(header)
        subtitle=Gtk.Label(label='How it works, where things live, and the resources behind it. Click any link to preview it.',xalign=0,wrap=True)
        subtitle.add_css_class('dim-label');root.append(subtitle)
        toolbar=Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, column_spacing=8, row_spacing=6, max_children_per_line=3, valign=Gtk.Align.START)
        for name, path in [('Preview Project Folder',project),('Preview Settings',settings)]:
            button=Gtk.Button(label=name);button.connect('clicked',lambda _,p=path:self.preview(p.as_uri()));toolbar.insert(button,-1)
        folder=Gtk.Button(label='Open Project Folder');folder.connect('clicked',lambda *_:owner.open_folder(project));toolbar.insert(folder,-1)
        root.append(toolbar)
        pane=Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL if width >= 850 else Gtk.Orientation.VERTICAL,
                       wide_handle=True,position=int(width * .44) if width >= 850 else int(height * .35),vexpand=True)
        pane.set_shrink_start_child(True);pane.set_shrink_end_child(True);root.append(pane)
        left=Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=18,margin_end=12)
        left.set_child(content);pane.set_start_child(left)
        for heading,body in sections:
            card=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8,margin_bottom=8)
            label=Gtk.Label(label=heading,xalign=0,wrap=True);label.add_css_class('title-3');card.append(label)
            self.prose(card,body)
            content.append(card)
            content.append(Gtk.Separator())
        right=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10,margin_start=12)
        pane.set_end_child(right)
        nav=Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,column_spacing=6,row_spacing=4,max_children_per_line=4,valign=Gtk.Align.START)
        self.back=Gtk.Button(label='←');self.back.set_tooltip_text('Previous preview');self.back.connect('clicked',lambda *_:self.navigate(-1));nav.insert(self.back,-1)
        self.forward=Gtk.Button(label='→');self.forward.set_tooltip_text('Next preview');self.forward.connect('clicked',lambda *_:self.navigate(1));nav.insert(self.forward,-1)
        self.action_group=Gio.SimpleActionGroup()
        for name, callback in [('open', self.open_external), ('reveal', self.show_in_folder),
                               ('copy-path', self.copy_path), ('copy-link', self.copy_link)]:
            action=Gio.SimpleAction.new(name,None)
            action.connect('activate',lambda _,_parameter,fn=callback:fn())
            self.action_group.add_action(action)
        self.insert_action_group('preview',self.action_group)
        self.actions_menu=Gio.Menu()
        self.actions_button=Gtk.MenuButton(label='Actions',menu_model=self.actions_menu)
        self.actions_button.set_tooltip_text('Open, reveal or copy this resource')
        nav.insert(self.actions_button,-1)
        right.append(nav)
        self.action_status=Gtk.Label(xalign=0,wrap=True,visible=False)
        self.action_status.add_css_class('dim-label');right.append(self.action_status)
        self.preview_title=Gtk.Label(label='Resource preview',xalign=0,wrap=True);self.preview_title.add_css_class('title-2');right.append(self.preview_title)
        self.meta=Gtk.Label(xalign=0,wrap=True,selectable=True,wrap_mode=Pango.WrapMode.WORD_CHAR)
        self.meta.add_css_class('dim-label');right.append(self.meta)
        self.preview_scroll=Gtk.ScrolledWindow(vexpand=True,hscrollbar_policy=Gtk.PolicyType.AUTOMATIC)
        right.append(self.preview_scroll)
        self.preview(project.as_uri())

    def key_pressed(self, _controller, keyval, _keycode, _state):
        if keyval == Gdk.KEY_Escape:
            self.close()
            return True
        return False

    def show_in_folder(self, *_):
        if self.index >= 0:
            try:
                reveal_file(self.history[self.index])
            except Exception as e:
                self.meta.set_text('Could not reveal file: ' + str(e))

    def center_on_monitor(self):
        if not self.get_mapped():
            return False
        try:
            windows = json.loads(subprocess.check_output(['hyprctl', '-j', 'clients'], text=True, timeout=2))
            dialog = next(c for c in windows if c['pid'] == os.getpid() and c['title'] == self.get_title())
            selector = json.dumps('address:' + dialog['address'])
            subprocess.run(['hyprctl', 'eval', 'hl.dispatch(hl.dsp.window.center({ window = ' + selector + ', reserved = true }))'],
                           capture_output=True, text=True, timeout=2, check=True)
        except (subprocess.SubprocessError, ValueError, StopIteration):
            pass
        return False

    def closed(self,*_):
        self.generation+=1
        return False

    def link(self,_,uri):
        self.preview(uri)
        return True

    def label(self,text,base=None):
        widget=Gtk.Label(xalign=0,wrap=True,selectable=True,wrap_mode=Pango.WrapMode.WORD_CHAR,max_width_chars=58)
        widget.set_markup(linked_markup(text,self.project,base))
        widget.connect('activate-link',self.link)
        return widget

    def prose(self,box,text,base=None):
        for block in re.split(r'\n\s*\n',text):
            if not block.strip():continue
            if block.lstrip().startswith('```'):
                clean=re.sub(r'^```\w*\n?|\n?```$', '', block.strip())
                label=Gtk.Label(label=clean,xalign=0,selectable=True,wrap=True,wrap_mode=Pango.WrapMode.WORD_CHAR)
                label.add_css_class('monospace');box.append(label);continue
            for line in block.splitlines() if block.startswith(('#','- ','* ','• ')) else [block]:
                if line.startswith('#'):
                    label=Gtk.Label(label=line.lstrip('# ').strip(),xalign=0,wrap=True)
                    label.add_css_class('title-3')
                else:
                    label=self.label(re.sub(r'^[-*] ', '• ', line),base)
                box.append(label)

    def preview(self,uri,remember=True):
        if urlparse(uri).scheme not in ('file','http','https'):
            return
        if remember:
            self.history=self.history[:self.index+1]+[uri];self.index+=1
        self.back.set_sensitive(self.index>0);self.forward.set_sensitive(self.index<len(self.history)-1)
        self.actions_menu.remove_all()
        for label, name in preview_actions(uri):
            self.actions_menu.append(label, 'preview.' + name)
        self.action_status.set_visible(False)
        self.generation+=1;ticket=self.generation
        self.preview_title.set_text('Loading preview…');self.meta.set_text(uri)
        spinner=Gtk.Spinner(spinning=True,halign=Gtk.Align.CENTER,valign=Gtk.Align.CENTER)
        self.preview_scroll.set_child(spinner)
        def worker():
            try:result=load_preview(uri)
            except Exception as e:result=dict(kind='message',title='Preview unavailable',meta=uri,text=str(e)+'\n\nYou can still use Open Externally.')
            GLib.idle_add(self.show_result,ticket,result)
        threading.Thread(target=worker,daemon=True).start()

    def show_result(self,ticket,result):
        if ticket!=self.generation:return False
        self.preview_title.set_text(result['title']);self.meta.set_text(result['meta'])
        content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10)
        kind=result['kind']
        if kind=='directory':
            for name,uri in result['entries']:
                label=Gtk.Label(xalign=0,wrap=True,wrap_mode=Pango.WrapMode.WORD_CHAR)
                label.set_markup(f'<a href="{GLib.markup_escape_text(uri)}">{GLib.markup_escape_text(name)}</a>')
                label.connect('activate-link',self.link);content.append(label)
        elif kind=='text':
            view=Gtk.TextView(editable=False,cursor_visible=False,monospace=True,wrap_mode=Gtk.WrapMode.WORD_CHAR,
                              left_margin=10,right_margin=10,top_margin=10,bottom_margin=10)
            view.get_buffer().set_text(result['text']);content.append(view)
        elif kind in ('image','image-bytes'):
            try:
                texture=(Gdk.Texture.new_from_filename(result['path']) if kind=='image' else
                         Gdk.Texture.new_from_bytes(GLib.Bytes.new(result['data'])))
                picture=Gtk.Picture.new_for_paintable(texture);picture.set_can_shrink(True)
                picture.set_content_fit(Gtk.ContentFit.CONTAIN);content.append(picture)
            except Exception as e:content.append(self.label('Image preview unavailable: '+str(e)))
        else:
            self.prose(content,result['text'],result.get('base'))
        self.preview_scroll.set_child(content)
        self.preview_scroll.get_vadjustment().set_value(0)
        return False

    def navigate(self,step):
        index=self.index+step
        if 0<=index<len(self.history):
            self.index=index;self.preview(self.history[index],False)

    def copy_value(self, value, label):
        try:
            copy_plain_text(value)
            self.action_status.set_text(label + ' copied as plain text')
        except Exception as e:
            self.action_status.set_text('Could not copy: ' + str(e))
        self.action_status.set_visible(True)

    def copy_path(self,*_):
        if self.index>=0:
            path=local_preview_path(self.history[self.index])
            if path is not None:
                self.copy_value(str(path), 'Path')

    def copy_link(self,*_):
        if self.index>=0:
            uri=self.history[self.index]
            self.copy_value(uri, 'File URI' if local_preview_path(uri) is not None else 'URL')

    def open_external(self,*_):
        if self.index>=0:
            try:Gio.AppInfo.launch_default_for_uri(self.history[self.index],None)
            except Exception as e:self.meta.set_text('Could not open externally: '+str(e))
