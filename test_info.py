import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import app
from info_view import linked_markup, load_preview, ReadableHTML, dialog_size, local_preview_path, reveal_file, InfoWindow
from shortcut_data import tooltip_widget

class InfoTests(unittest.TestCase):
    def test_escape_closes_only_info(self):
        from unittest.mock import Mock
        dialog=Mock()
        self.assertTrue(InfoWindow.key_pressed(dialog,None,app.Gdk.KEY_Escape,0,0))
        dialog.close.assert_called_once()
        self.assertFalse(InfoWindow.key_pressed(dialog,None,app.Gdk.KEY_a,0,0))
        dialog.close.assert_called_once()

    def test_show_in_folder_selects_local_file_with_spaces(self):
        with tempfile.TemporaryDirectory() as directory:
            file=Path(directory)/'my notes.md'
            file.write_text('notes')
            self.assertEqual(local_preview_path(file.as_uri()),file)
            with patch('info_view.subprocess.Popen') as launch:
                reveal_file(file.as_uri())
                self.assertEqual(launch.call_args.args[0],['nautilus','--select',str(file)])
            self.assertIsNone(local_preview_path('https://example.com/readme.md'))
            self.assertIsNone(local_preview_path('file://remote-host/etc/passwd'))

    def test_info_size_fits_scaled_display_and_smaller_monitors(self):
        self.assertEqual(dialog_size(1200, 649), (1060, 601))
        for width, height in [(800, 600), (600, 400), (1920, 1080)]:
            w, h = dialog_size(width, height)
            self.assertLessEqual(w, width - 48)
            self.assertLessEqual(h, height - 48)

    def test_markup_escapes_text_and_links_files(self):
        text=linked_markup('A < B & **bold** '+str(app.PROJECT/'app.py')+' and [Site](https://example.com/a?x=1&y=2)',app.PROJECT)
        self.assertIn('A &lt; B &amp;',text)
        self.assertIn('<b>bold</b>',text)
        self.assertIn('file://',text)
        self.assertIn('x=1&amp;y=2',text)

    def test_slashes_in_prose_do_not_become_file_links(self):
        markup=linked_markup('primary/default, press/release and Rust/GTK4',app.PROJECT)
        self.assertNotIn('<a ',markup)

    def test_file_directory_and_missing_previews(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'example.md';p.write_text('# Heading\n\n**Bold**')
            self.assertEqual(load_preview(p.as_uri())['kind'],'markdown')
            result=load_preview(Path(d).as_uri())
            self.assertEqual(result['entries'],[('example.md',p.as_uri())])
            self.assertEqual(load_preview((Path(d)/'absent.json').as_uri())['kind'],'message')

    def test_html_readable_preview_preserves_links_not_scripts(self):
        parser=ReadableHTML('https://example.com/docs/')
        parser.feed('<title>Docs</title><script>private script</script><h1>Title</h1><p>Read <a href="next">Next</a></p>')
        self.assertEqual(parser.title,'Docs')
        self.assertNotIn('private script',parser.text())
        self.assertIn('[Next](https://example.com/docs/next)',parser.text())

    def test_reject_nonpreview_schemes(self):
        with self.assertRaises(ValueError):load_preview('javascript:alert(1)')

    def test_tooltip_natural_height_does_not_reserve_blank_space(self):
        item=dict(key='SUPER ALT + F',name='Full width',group='Windows',dispatcher='lua',
                  arg='hl.dsp.window.fullscreen({ mode = "maximized" })')
        widget=tooltip_widget([item])
        self.assertLess(widget.measure(app.Gtk.Orientation.VERTICAL,-1).natural,180)

    def test_keyboard_tooltip_omits_dispatch_metadata(self):
        item=dict(key='SUPER + W',name='Close window',group='Windows',dispatcher='lua',arg='hl.dsp.window.close()')
        widget=tooltip_widget([item], technical=False)
        grid=widget.get_first_child().get_next_sibling()
        self.assertEqual(grid.get_child_at(1,0).get_label(), 'Close window')
        self.assertIsNone(grid.get_child_at(0,2))

    def test_tooltip_fields_are_aligned_and_literal(self):
        item=dict(key='SUPER + W',name='Close <window>',group='Windows',dispatcher='lua',arg='hl.dsp.window.close()')
        widget=tooltip_widget([item])
        grid=widget.get_first_child().get_next_sibling()
        self.assertEqual(grid.get_child_at(0,0).get_label(),'Description')
        self.assertEqual(grid.get_child_at(1,0).get_label(),'Close <window>')
        self.assertEqual(grid.get_child_at(0,3).get_width_chars(),12)
        self.assertTrue(grid.get_child_at(1,3).has_css_class('monospace'))

if __name__=='__main__':unittest.main()
