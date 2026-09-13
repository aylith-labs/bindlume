"""Key search, physical mapping, IPC protocol and transient capture checks."""
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import app
from keyboard_view import XkbLayout, KeyboardView
from shortcut_data import matches_query, details

class KeyboardTests(unittest.TestCase):
    def item(self,key,name='Window action'):
        return dict(key=key,name=name,group='Windows',dispatcher='lua',arg='hl.dsp.window.close()')

    def test_at_search_matches_base_keys_not_description(self):
        for shortcut in ['W','SUPER + W','CTRL + W','SUPER CTRL + W']:
            self.assertTrue(matches_query(self.item(shortcut),'@w'))
        for shortcut in ['SUPER + DOWN','SUPER + XF86WWW','CTRL + Q']:
            self.assertFalse(matches_query(self.item(shortcut),'@w'))
        self.assertTrue(matches_query(self.item('SUPER CTRL + W'),'@ctrl+w window'))
        self.assertFalse(matches_query(self.item('SUPER + W'),'@ctrl+w'))
        self.assertTrue(matches_query(self.item('SUPER + RETURN'),'@enter'))
        self.assertTrue(matches_query(self.item('SUPER + W'),r'\@w'))

    def test_details_include_full_metadata(self):
        text=details(self.item('SUPER + W'))
        for value in ['Description: Window action','Dispatcher: lua','Arguments: hl.dsp.window.close()']:
            self.assertIn(value,text)

    def test_native_layout_resolves_different_layouts(self):
        us=XkbLayout(dict(layout='us'));de=XkbLayout(dict(layout='de'))
        try:
            self.assertEqual(us.key('AD02')[1], 'W')
            self.assertEqual(us.key('AD06')[1], 'Y')
            self.assertEqual(de.key('AD06')[1], 'Z')
        finally:
            us.close();de.close()

    def test_exact_modifier_layer_and_all_layers(self):
        # Exercise matching independently of the GTK view and its live listener.
        class View:
            layer=KeyboardView.layer
        v=View();v.held=frozenset();v.manual={'CTRL'};v.all_layers=False
        v.items=[self.item('CTRL + W'),self.item('SUPER CTRL + W'),self.item('W')]
        self.assertEqual(len(KeyboardView.bindings(v,'W')),1)
        v.all_layers=True
        self.assertEqual(len(KeyboardView.bindings(v,'W')),3)
        v.held=frozenset({'SUPER','CTRL'})
        self.assertEqual(KeyboardView.bindings(v,'W')[0]['key'],'SUPER CTRL + W')

    def test_input_bridge_lease_release_and_no_history(self):
        script='''
local callback, events
local now = 100
os.time = function() return now end
hl = { on = function(_, cb) callback = cb end,
       dsp = { event = function(value) return value end },
       dispatch = function(value) table.insert(events, value) end }
events = {}
dofile(arg[1])
callback(25, 0, 1)
assert(#events == 0, 'No non-modifier capture without a lease')
_omarchy_shortcuts_lease = 110
callback(25, 0, 1)
callback(25, 0, 0)
assert(events[1] == 'omarchy-shortcuts-key,25,1')
assert(events[2] == 'omarchy-shortcuts-key,25,0')
callback(133, 0, 1)
assert(_omarchy_shortcuts_mods == 64)
callback(50, 0, 1)
assert(_omarchy_shortcuts_mods == 65)
callback(133, 0, 0)
assert(_omarchy_shortcuts_mods == 1)
callback(50, 0, 0)
assert(_omarchy_shortcuts_mods == 0)
local count = #events
callback(25, 0, 2)
assert(#events == count)
now = 111
callback(25, 0, 1)
assert(#events == count, 'Expired lease must stop capture')
'''
        subprocess.run(['lua','-',str(app.PROJECT/'input_bridge.lua')],input=script,text=True,check=True)

    def test_theme_reloads_palette_without_changing_system(self):
        import theme
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'colors.toml'
            p.write_text('background = "#ffffff"\nforeground = "#111111"\nmode = "light"\n')
            with patch.object(theme,'PALETTE',p):
                t=theme.SystemTheme()
                self.assertEqual(t.colors['background'],'#ffffff')
                p.write_text('background = "#111111"\nforeground = "#ffffff"\nmode = "dark"\n')
                t.poll()
                self.assertEqual(t.colors['background'],'#111111')
                app.GLib.source_remove(t.timer)

if __name__=='__main__':unittest.main()
