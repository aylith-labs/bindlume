"""Common keyboard and focus behavior for every application dialog."""
from gi.repository import Gtk, Gdk, GLib


def walk(widget):
    yield widget
    child = widget.get_first_child()
    while child:
        yield from walk(child)
        child = child.get_next_sibling()


def install(app):
    def added(_app, window):
        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        def pressed(_controller, key, _code, _state):
            main = getattr(app, 'window', None)
            if key != Gdk.KEY_Escape or window is main: return False
            if not window.get_transient_for() and not window.get_modal(): return False
            # Capturing a shortcut and dismissing a popup are inner Escape scopes.
            for widget in walk(window):
                capture = getattr(widget, 'capture', None)
                if isinstance(capture, Gtk.ToggleButton) and capture.get_active():
                    capture.set_active(False)
                    return True
            popovers = [widget for widget in walk(window) if isinstance(widget, Gtk.Popover) and widget.get_visible()]
            if popovers:
                popovers[-1].popdown()
            else:
                window.close()
            return True
        keys.connect('key-pressed', pressed)
        window.add_controller(keys)
        window.dialog_keys = keys
        def closed(*_):
            def restore():
                main = getattr(app, 'window', None)
                if main is None or main is window or not main.get_visible(): return False
                parent = window.get_transient_for()
                if parent and parent is not main and parent.get_visible():
                    parent.present()
                    return False
                if any(other is not main and other is not window and other.get_modal() and other.get_visible()
                       for other in app.get_windows()): return False
                main.present()
                if main.get_focus() is None:
                    app.search.grab_focus()
                return False
            GLib.idle_add(restore)
        window.connect('unmap', closed)
    app.connect('window-added', added)
