"""Omarchy-compatible layer-shell surfaces with a shared modal backdrop."""
import os
import gi
from gi.repository import Gtk, Gdk
from native_style import menu_tokens

def install(app):
    app.overlay_surfaces = None
    if os.environ.get('GDK_BACKEND') == 'broadway': return
    from theme import detected_look
    if detected_look() != 'square': return
    try:
        gi.require_version('Gtk4LayerShell', '1.0')
        from gi.repository import Gtk4LayerShell as Layer
        if not Layer.is_supported(): return
    except (ImportError, ValueError): return
    app.overlay_surfaces = controller = SurfaceGroup(app, Layer)
    app.connect('window-added', lambda _app, window: controller.add(window))
    app.connect('shutdown', lambda *_: controller.backdrop.destroy())

class SurfaceGroup:
    def __init__(self, app, layer):
        self.app, self.layer, self.visible = app, layer, []
        self.backdrop = Gtk.Window(decorated=False)
        self.backdrop.add_css_class('bindlume-backdrop')
        layer.init_for_window(self.backdrop)
        layer.set_namespace(self.backdrop, 'bindlume-backdrop')
        layer.set_layer(self.backdrop, layer.Layer.TOP)
        layer.set_exclusive_zone(self.backdrop, -1)
        layer.set_keyboard_mode(self.backdrop, layer.KeyboardMode.NONE)
        for edge in (layer.Edge.TOP,layer.Edge.BOTTOM,layer.Edge.LEFT,layer.Edge.RIGHT):
            layer.set_anchor(self.backdrop,edge,True)
        click = Gtk.GestureClick(button=1)
        click.connect('released', lambda *_: self.visible[-1].close() if self.visible else None)
        self.backdrop.add_controller(click)
        self.provider=Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),self.provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION+10)

    def update_backdrop(self):
        menu=menu_tokens()['menu']
        color=Gdk.RGBA()
        if not color.parse(menu.get('scrim','#1e1e2e')): color.parse('#1e1e2e')
        alpha=max(0,min(1,float(menu.get('scrim-alpha',.5))))
        self.provider.load_from_data(f'window.bindlume-backdrop {{ background: rgba({round(color.red*255)},{round(color.green*255)},{round(color.blue*255)},{alpha}); border: none; box-shadow: none; }}'.encode())

    def monitor(self, window):
        monitor = self.layer.get_monitor(window)
        if monitor: return monitor
        surface = window.get_surface()
        if surface:
            monitor = window.get_display().get_monitor_at_surface(surface)
            if monitor: return monitor
        monitors = window.get_display().get_monitors()
        return monitors.get_item(0) if monitors.get_n_items() else None

    def available_bounds(self, window):
        monitor = self.monitor(window)
        if not monitor: return 800, 600
        geometry = monitor.get_geometry()
        top = getattr(window, '_overlay_top', 20)
        return max(200,geometry.width-40), max(100,geometry.height-top-20)

    def fit_window(self, window, *_):
        if getattr(window, '_fitting_overlay', False): return
        width, height = window.get_default_size()
        max_width, max_height = self.available_bounds(window)
        desired = (min(width if width > 0 else 800,max_width), min(height if height > 0 else 600,max_height))
        if desired != (width,height):
            window._fitting_overlay = True
            window.set_default_size(*desired)
            window._fitting_overlay = False

    def freeze_top(self, window):
        if getattr(window, '_overlay_top_frozen', False) or not window.get_mapped(): return
        surface = window.get_surface()
        monitor = window.get_display().get_monitor_at_surface(surface)
        if monitor:
            top = max(5, (monitor.get_geometry().height-surface.get_height())//2)
            self.layer.set_margin(window,self.layer.Edge.TOP,top)
            self.layer.set_anchor(window,self.layer.Edge.TOP,True)
            window._overlay_top_frozen = True
            window._overlay_top = top
            self.fit_window(window)

    def add(self, window):
        layer=self.layer
        layer.init_for_window(window)
        layer.set_namespace(window,'bindlume-overlay')
        layer.set_layer(window,layer.Layer.OVERLAY)
        layer.set_exclusive_zone(window,-1)
        layer.set_keyboard_mode(window,layer.KeyboardMode.EXCLUSIVE)
        window.set_decorated(False)
        # Show the dimming surface before GTK maps the foreground card.
        def showing(*_):
            if window.get_visible():
                parent = window.get_transient_for()
                if parent and parent.get_surface():
                    monitor = parent.get_display().get_monitor_at_surface(parent.get_surface())
                    layer.set_monitor(window,monitor)
                self.fit_window(window)
                self.update_backdrop()
                if not self.backdrop.get_visible(): self.backdrop.present()
        window.connect('notify::visible',showing)
        window.connect('notify::default-width',self.fit_window)
        window.connect('notify::default-height',self.fit_window)
        def mapped(*_):
            self.fit_window(window)
            if window in self.visible: self.visible.remove(window)
            for other in self.visible: layer.set_keyboard_mode(other,layer.KeyboardMode.NONE)
            self.visible.append(window)
            layer.set_keyboard_mode(window,layer.KeyboardMode.EXCLUSIVE)
        def unmapped(*_):
            if getattr(window, '_overlay_top_frozen', False):
                layer.set_anchor(window,layer.Edge.TOP,False)
                layer.set_margin(window,layer.Edge.TOP,0)
                window._overlay_top_frozen = False
                window._overlay_top = 20
            if window in self.visible: self.visible.remove(window)
            self.visible=[item for item in self.visible if item.get_visible()]
            if self.visible: layer.set_keyboard_mode(self.visible[-1],layer.KeyboardMode.EXCLUSIVE)
            else: self.backdrop.set_visible(False)
        window.connect('map',mapped)
        window.connect('unmap',unmapped)
