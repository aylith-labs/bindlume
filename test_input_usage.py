import json
from datetime import date,datetime,timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import native_style
from input_controls import devices,direction
from usage_view import summarize
import agent_quota

class InputUsageTests(unittest.TestCase):
    def test_device_interfaces_group_without_exposing_serial(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'devices'
            path.write_text('I: Bus=0003 Vendor=16d0 Product=113c Version=0100\nN: Name="Azeron"\nH: Handlers=kbd event1\n\nI: Bus=0003 Vendor=16d0 Product=113c Version=0100\nN: Name="Azeron"\nU: Uniq=private\nH: Handlers=js0 event2\n')
            found=devices(path)
        self.assertEqual(len(found),1)
        self.assertEqual(found[0]['kinds'],['Controller','Keyboard'])
        self.assertEqual(found[0]['joysticks'],['/dev/input/js0'])
        self.assertNotIn('private',str(found))
        self.assertIsNone(direction(3,4));self.assertEqual(direction(-70,10),'left')

    def test_usage_scope_dates_models_and_cache_not_double_counted(self):
        session={'provider':'codex','turn_usage':[{'input_tokens':100,'cached_input_tokens':80,'output_tokens':20,'created_at':'2026-09-20T12:00:00+00:00','model':'model-a'}, {'input_tokens':5,'output_tokens':3}, {'provider':'claude','input_tokens':999}]}
        stats=summarize([session],'codex',date(2026,9,20))
        self.assertEqual(stats['total'],128)
        self.assertEqual(stats['days']['2026-09-20'],120)
        self.assertEqual(stats['undated'],8)
        self.assertEqual(stats['models']['model-a'],120)

    def test_shell_record_reuses_limits_but_not_machine_totals(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict('os.environ',{'XDG_STATE_HOME':folder}):
            path=Path(folder)/'omarchy/agents/usage/codex.json';path.parent.mkdir(parents=True)
            record={'ready':True,'updatedAt':datetime.now(timezone.utc).isoformat(),'limits':[{'label':'Weekly','percent':.08}], 'tierLabel':'pro','todayTotalTokens':999999}
            path.write_text(json.dumps(record));result=agent_quota.omarchy_quota('codex')
            self.assertEqual(result['windows'][0]['remaining_percent'],92)
            self.assertNotIn('todayTotalTokens',result)
            record['updatedAt']='2000-01-01T00:00:00+00:00';path.write_text(json.dumps(record))
            self.assertIsNone(agent_quota.omarchy_quota('codex'))

    def test_named_gradient_border_and_edge_widths(self):
        css=native_style.border_css({'menu':{'border':'hyprland.active-border','border-width':'1 2','border-width-bottom':3},'hyprland':{'active-border':'rgba(26a269ee) rgba(2ec27eee) 45deg'}})
        self.assertIn('linear-gradient(45deg',css)
        self.assertIn('rgba(38,162,105,0.93333)',css)
        self.assertIn('border-width: 1px 2px 3px 2px;',css)

    def test_controller_initial_state_never_executes_and_focus_loss_closes(self):
        import os,struct
        from unittest.mock import Mock
        from input_controls import Controls
        reader,writer=os.pipe();os.set_blocking(reader,False)
        controls=Controls.__new__(Controls)
        controls.fd=reader;controls.open_device='/dev/input/js0'
        controls.config={'controller':True,'device':'/dev/input/js0','buttons':{'0':'search'}}
        controls.app=Mock();controls.app.feature_enabled.return_value=True
        controls.active=Mock(return_value=True);controls.execute=Mock()
        controls.window=None
        os.write(writer,struct.pack('IhBB',0,1,0x81,0)+struct.pack('IhBB',0,1,1,0))
        try:
            controls.poll();controls.execute.assert_called_once_with('search')
            controls.active.return_value=False;controls.poll();self.assertIsNone(controls.fd)
        finally:
            os.close(writer)
            if controls.fd is not None:controls.close_device()
