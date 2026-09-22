"""Concise About overlay, separate from architecture and resource browsing."""
import json
from pathlib import Path
import platform
from gi.repository import Gtk
import settings_ui
import brand
from localization import text as tr

def show(app):
    if getattr(app,'about_window',None):app.about_window.present();return
    window=Gtk.Window(application=app,transient_for=app.window,modal=True,title='About',default_width=540,default_height=430)
    app.about_window=window
    window.connect('close-request',lambda *_:setattr(app,'about_window',None) or False)
    body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=16,margin_top=24,margin_bottom=24,margin_start=24,margin_end=24)
    logo=Gtk.Image.new_from_file(str(Path(__file__).parent/'branding/mark.svg'))
    logo.set_pixel_size(64)
    logo.set_halign(Gtk.Align.START)
    body.append(logo)
    settings_ui.header(body,window,brand.NAME)
    tagline=Gtk.Label(label=brand.TAGLINE,xalign=0)
    tagline._translation_skip=True
    body.append(tagline)
    description=Gtk.Label(label=tr('Browse, find and remember shortcuts for your desktop and installed apps.'),wrap=True,xalign=0)
    body.append(description)
    try:build=json.loads(Path(__file__).with_name('build-info.json').read_text())
    except (OSError,ValueError):build={'version':'Development','revision':'Working tree','built_at':'Not installed'}
    for title,value in [('Version',build['version']),('Build',build['revision']),('Built',build['built_at']),('Language',__import__('localization').LANGUAGE_NAMES[__import__('localization').resolve_language(app.preferences['language'])]),('Runtime',f'Python {platform.python_version()} · GTK {Gtk.get_major_version()}.{Gtk.get_minor_version()}')]:
        from usage_view import relative_time
        label=Gtk.Label(label=relative_time(value) if title == 'Built' else str(value),selectable=True,wrap=True,xalign=1)
        if title == 'Built': label.set_tooltip_text(str(value))
        settings_ui.row(body,title,label)
    links=Gtk.Box(spacing=8)
    links.append(Gtk.LinkButton.new_with_label(brand.HOMEPAGE,tr('Project homepage')))
    links.append(Gtk.LinkButton.new_with_label(Path(__file__).with_name('README.md').as_uri(),tr('Documentation')))
    body.append(links)
    details=Gtk.Button(label='Inside the app')
    details.connect('clicked',lambda *_:app.show_details())
    body.append(details)
    window.set_child(body);window.present()
