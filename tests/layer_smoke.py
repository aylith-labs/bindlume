"""Opt-in real desktop smoke test; requires a disposable XDG_CONFIG_HOME."""
import sys, json, os
from pathlib import Path
if not os.environ.get('XDG_CONFIG_HOME') or Path(os.environ['XDG_CONFIG_HOME']).resolve() == Path.home()/'.config':
 raise SystemExit('Use a disposable XDG_CONFIG_HOME for this desktop smoke check.')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from unittest.mock import patch
import app, preferences
from keyboard_view import KeyboardView
from gi.repository import GLib
app.APP_ID='com.aylith.Bindlume.SurfaceCheck'
patches=[]
for method in ('refresh','refresh_targets','refresh_source_counts','sync_guide_feature','sync_window_animations','listen_modifiers'):
 if hasattr(app.Shortcuts,method): patches.append(patch.object(app.Shortcuts,method,return_value=False))
for method in ('renew_lease','listen_modifiers','refresh_layout'):
 patches.append(patch.object(KeyboardView,method,return_value=True))
for p in patches:p.start()
ui=app.Shortcuts()
errors=[]
def checked(fn):
 def run():
  try:fn()
  except Exception as e: errors.append(str(e));print('ERROR',repr(e),flush=True)
  return False
 return run
@checked
def main():
 group=ui.overlay_surfaces
 assert group is not None,'No layer shell'
 assert group.backdrop.get_visible(),'Backdrop missing'
 assert group.layer.get_layer(group.backdrop)==group.layer.Layer.TOP
 assert group.layer.get_layer(ui.window)==group.layer.Layer.OVERLAY
 assert group.layer.is_layer_window(ui.window),'Main is not a layer'
 assert group.layer.get_keyboard_mode(ui.window)==group.layer.KeyboardMode.EXCLUSIVE
 ui.search.set_text('overlay smoke check')
 assert group.layer.get_anchor(ui.window,group.layer.Edge.TOP),'Search did not freeze the top edge'
 print('Main layer and backdrop visible, exclusive keyboard focus; search top edge frozen',flush=True)
 ui.window.set_default_size(9000,9000)
 GLib.timeout_add(400,bounded)
@checked
def bounded():
 group=ui.overlay_surfaces
 bounds=group.available_bounds(ui.window)
 surface=ui.window.get_surface()
 assert surface.get_width()<=bounds[0],(surface.get_width(),bounds)
 assert surface.get_height()<=bounds[1],(surface.get_height(),bounds)
 print('Oversized frozen overlay constrained to display',flush=True)
 preferences.show(ui)
 GLib.timeout_add(500,child)
@checked
def child():
 group=ui.overlay_surfaces
 assert group.layer.is_layer_window(ui.preferences_window)
 assert group.layer.get_keyboard_mode(ui.window)==group.layer.KeyboardMode.NONE
 assert group.layer.get_keyboard_mode(ui.preferences_window)==group.layer.KeyboardMode.EXCLUSIVE
 print('Nested settings layer owns focus',flush=True)
 ui.preferences_window.close()
 GLib.timeout_add(500,restored)
@checked
def restored():
 group=ui.overlay_surfaces
 assert group.layer.get_keyboard_mode(ui.window)==group.layer.KeyboardMode.EXCLUSIVE
 ui.hide_main()
 assert not group.backdrop.get_visible(),'Backdrop remains after closing'
 print('Parent focus restored; closing hides backdrop',flush=True)
 ui.quit()
GLib.timeout_add(700,main)
GLib.timeout_add(6000,lambda: ui.quit() or False)
ui.run([])
raise SystemExit(bool(errors))
