"""Raised keyboard rendering and pointer mapping on the private test display."""
import os
from pathlib import Path
import unittest
from unittest.mock import patch
import cairo
from keyboard_view import KeyboardView

class RaisedKeyboardTests(unittest.TestCase):
    def test_default_and_explicit_flat_preference(self):
        for preferences, expected in ((None, True), ({}, True), ({'raised_keys': False}, False)):
            with self.subTest(preferences=preferences):
                view=KeyboardView(lambda *_:None,lambda:{},preferences,preview=True)
                try:
                    self.assertEqual(view.raised_keys,expected)
                    self.assertEqual(view.option_buttons['raised_keys'].get_active(),expected)
                finally:view.stop()

    def test_preference_persistence_and_transformed_key_targets(self):
        saved=[]
        view=KeyboardView(lambda *_:None,lambda:{}, {'raised_keys':True,'show_numpad':True},saved.append,preview=True)
        try:
            with patch.object(view.area,'get_width',return_value=1000),patch.object(view.area,'get_height',return_value=320):
                unit=view.geometry(1000,320)
                for key in view.keys:
                    x,y=view.surface_transform(1000,320).transform_point((key['x']+key['w']/2)*unit,(key['y']+key['h']/2)*unit)
                    self.assertEqual(view.hit(x,y)['name'],key['name'])
                self.assertIsNone(view.hit(-20,-20))
            view.option_buttons['raised_keys'].set_active(False)
            self.assertFalse(saved[-1]['raised_keys'])
            self.assertEqual(view.surface_transform(1000,320).transform_point(50,60),(50,60))
        finally:view.stop()

    def test_render_both_palettes_with_modifier_and_matching_key(self):
        view=KeyboardView(lambda *_:None,lambda:palette,{'raised_keys':True},preview=True)
        try:
            view.items=[dict(key='CTRL + T',name='New tab')];view.manual={'CTRL'}
            for mode in ('light','dark'):
                palette=dict(background='#f8f7f4' if mode=='light' else '#131110',foreground='#1c1a16' if mode=='light' else '#faf8f5',lighter_background='#f0eee9' if mode=='light' else '#26231e',accent='#c97a3a',selection='#c97a3a')
                surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,1000,320)
                view.draw(view.area,cairo.Context(surface),1000,320)
                if os.environ.get('RAISED_SHOTS'):
                    path=Path(os.environ['RAISED_SHOTS']);path.mkdir(parents=True,exist_ok=True)
                    surface.write_to_png(str(path/f'raised-{mode}.png'))
                self.assertEqual(surface.get_width(),1000)
        finally:view.stop()
