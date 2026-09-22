import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).parent / 'keyguide/src/backend'))
from keyguide_backend import icon_assets

class IconAssetsTests(unittest.TestCase):
    def test_svg_is_recognized_but_html_is_not(self):
        self.assertEqual(icon_assets.image_extension(b'<svg xmlns="http://www.w3.org/2000/svg"/>'),'.svg')
        self.assertEqual(icon_assets.image_extension(b'<html>not an icon</html>'),'')

    def test_tries_additional_html_icons_and_caches_success(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict('os.environ', {'XDG_CACHE_HOME':temp}):
            def read(url):
                if url.endswith('/favicon.ico'): return b'not an icon'
                if url.endswith('/'): return b'<link rel="icon" href="/bad"><link rel="icon" href="/good.svg">'
                if url.endswith('/bad'): return b'<html/>'
                return b'<svg xmlns="http://www.w3.org/2000/svg"/>'
            with patch.object(icon_assets, 'read_url', side_effect=read):
                path = icon_assets.favicon('https://example.test')
                self.assertTrue(path.endswith('.svg'))
                self.assertTrue(Path(path).exists())
            with patch.object(icon_assets, 'read_url') as network:
                self.assertEqual(icon_assets.favicon('https://example.test'),path)
                network.assert_not_called()

    def test_gtk_image_decodes_ico_through_pixbuf(self):
        import struct
        import app
        pixbuf = app.GdkPixbuf.Pixbuf.new(app.GdkPixbuf.Colorspace.RGB, True, 8, 16, 16)
        pixbuf.fill(0x4488bbff)
        ok, png = pixbuf.save_to_bufferv('png', [], [])
        self.assertTrue(ok)
        ico = struct.pack('<HHH',0,1,1) + struct.pack('<BBBBHHII',16,16,0,0,1,32,len(png),22) + png
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'favicon.ico'
            path.write_bytes(ico)
            image = app.application_icon(str(path))
            self.assertIsNotNone(image.get_paintable())
            self.assertGreater(image.get_paintable().get_intrinsic_width(),0)
