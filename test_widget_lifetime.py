"""Widgets that are built and discarded repeatedly must actually be freed.

The long-lived background process rebuilds the keyboard view's extras section on
every search keystroke. A signal handler on a child that captured its parent
strongly kept every discarded section (and all of its rows) alive: about a
gigabyte after a few hours of use.
"""
import gc
import unittest
import weakref

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk

import app


class WidgetLifetimeTests(unittest.TestCase):
    def test_discarded_section_is_freed(self):
        host = Gtk.Box()
        refs = []
        for _ in range(5):
            section = app.ShortcutSection('Media', 3, True, lambda _section: None)
            section.body.append(Gtk.Label(label='row'))
            host.append(section)
            refs.append(weakref.ref(section))
            host.remove(section)
            del section
        gc.collect()
        self.assertEqual([r() for r in refs], [None] * 5)

    def test_section_toggle_still_reports_itself(self):
        seen = []
        section = app.ShortcutSection('Media', 3, True, seen.append)
        section.set_expanded(False)
        self.assertEqual(seen, [section])
        self.assertFalse(section.body.get_visible())


if __name__ == '__main__':
    unittest.main()
