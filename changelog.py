"""Source-owned release notes with installed build dates."""
import json
from pathlib import Path
from gi.repository import Gtk, GLib
from localization import text as tr
import settings_ui
from usage_view import relative_time


def releases():
    rows=json.loads(Path(__file__).with_name('changelog.json').read_text())
    try:build=json.loads(Path(__file__).with_name('build-info.json').read_text())
    except (OSError,ValueError):build={}
    for row in rows:
        row['built_at']=build.get('built_at',row['built_at']) if row['version']==build.get('version') else row['built_at']
    return rows


def show(app):
    if getattr(app,'changelog_window',None):app.changelog_window.present();return
    window=Gtk.Window(application=app,transient_for=getattr(app,'about_window',None) or app.window,modal=True,title=tr('Changelog'),default_width=720,default_height=620)
    app.changelog_window=window
    window.connect('close-request',lambda *_:setattr(app,'changelog_window',None) or False)
    body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=14,margin_top=20,margin_bottom=20,margin_start=20,margin_end=20)
    settings_ui.header(body,window,tr('Changelog'))
    scroll=Gtk.ScrolledWindow(vexpand=True,hscrollbar_policy=Gtk.PolicyType.NEVER);body.append(scroll)
    content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=14);scroll.set_child(content)
    window.release_groups=[]
    dates=[]
    for index,entry in enumerate(releases()):
        group=Gtk.Expander(expanded=index==0)
        heading=Gtk.Box(spacing=16)
        version=Gtk.Label(label=entry['version'],xalign=0,hexpand=True);version._translation_skip=True
        stamp=Gtk.Label(label=relative_time(entry['built_at']),xalign=1)
        stamp._translation_skip=True;stamp.set_tooltip_text(entry['built_at'])
        dates.append((stamp,entry['built_at']))
        heading.append(version);heading.append(stamp);group.set_label_widget(heading)
        details=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10,margin_start=20,margin_top=12,margin_bottom=12)
        for note in entry['changes']:
            details.append(Gtk.Label(label='• '+tr(note),xalign=0,wrap=True,max_width_chars=65))
        group.set_child(details);content.append(group);window.release_groups.append(group)
    def refresh():
        if not window.get_visible():return False
        for label,stamp in dates:label.set_text(relative_time(stamp))
        return True
    window.set_child(body);window.present()
    GLib.timeout_add_seconds(60,refresh)
