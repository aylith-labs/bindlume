import os
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta
import activity_log as log
import agent_control
import test_companion_ui as companion_tests
from test_ui_workflows import pump
from gi.repository import Gtk

@unittest.skipUnless(os.environ.get('GDK_BACKEND')=='broadway','Private display required')
class ActivityTests(unittest.TestCase):
    setUp=companion_tests.CompanionUiTests.setUp
    tearDown=companion_tests.CompanionUiTests.tearDown
    def call(self,operation,**arguments):
        return agent_control.execute(self.ui,dict(operation=operation,arguments=arguments))
    def test_settings_undo_redo_and_branch(self):
        previous=self.ui.preferences['font_size']
        self.call('settings',key='font_size',value=previous+1)
        self.call('activity',action='undo')
        self.assertEqual(self.ui.preferences['font_size'],previous)
        self.call('activity',action='redo')
        self.assertEqual(self.ui.preferences['font_size'],previous+1)
        self.call('activity',action='undo')
        self.call('settings',key='font_size',value=previous+2)
        self.assertFalse(self.call('activity')['can_redo'])
    def test_view_undo_restores_prerequisites(self):
        self.ui.set_feature('layouts',False)
        before=log.snapshot(self.ui)
        self.call('view',show_filters=True,modifiers=['CTRL'])
        self.call('activity',action='undo')
        self.assertEqual(log.snapshot(self.ui),before)
        self.call('activity',action='redo')
        self.assertTrue(self.ui.feature_enabled('layouts'))
        self.assertEqual(self.ui.keyboard.manual,{'CTRL'})
    def test_retention_dates_unlimited_and_validation(self):
        self.call('activity',action='retention',max_operations=2)
        for n in range(4): self.call('search',query=str(n))
        self.assertEqual(self.call('activity')['retained'],2)
        self.call('activity',action='retention',max_operations=0,max_age_days=0)
        for n in range(4): self.call('search',query=str(n))
        self.assertGreater(self.call('activity')['retained'],2)
        before=log.policy(self.ui)
        with self.assertRaises(ValueError):self.call('activity',action='retention',max_operations=1,max_age_days=-1)
        self.assertEqual(log.policy(self.ui),before)
        store=log.journal()
        with store.connect() as db:
            store.insert(db,dict(id='yesterday',time=(datetime.now().astimezone()-timedelta(days=1)).isoformat(),operation='search',arguments={}))
        self.assertEqual(self.call('activity',date='yesterday')['operations'][0]['id'],'yesterday')
        self.call('activity',action='retention',max_age_days=1)
        self.assertEqual(self.call('activity',date='yesterday')['matching'],0)
    def test_conflict_does_not_change_settings(self):
        self.call('settings',key='font_size',value=19)
        self.ui.preferences['font_size']=20
        with self.assertRaises(ValueError):self.call('activity',action='undo')
        self.assertEqual(self.ui.preferences['font_size'],20)
    def test_activity_commands(self):
        from decision_commands import plan
        self.assertEqual(plan('show last ten operations')['arguments']['limit'],10)
        self.assertEqual(plan('show me operations of yesterday')['arguments']['date'],'yesterday')
        self.assertEqual(plan('make activity log store indefinitely')['arguments']['max_operations'],0)
    def test_responsive_layout_and_activity_window(self):
        self.ui.window.set_size_request(1300,700)
        self.ui.show_chat();pump(.3)
        self.ui.main_pane.set_position(100);pump(.3)
        self.assertGreaterEqual(self.ui.main_root.get_allocated_width(),620)
        self.assertFalse(self.ui.main_pane.get_shrink_start_child())
        self.ui.update_column_width()
        width=self.ui.shortcut_column_width
        self.ui.show_chat(False);pump(.3)
        self.assertGreaterEqual(self.ui.shortcut_column_width,140)
        self.ui.view_toggle.set_active(True);pump(.3)
        self.assertIsInstance(self.ui.keyboard.toolbar,Gtk.FlowBox)
        self.ui.view_toggle.set_active(False);pump(.2)
        self.assertIs(self.ui.type_filter.get_parent(),self.ui.filter_bar)
        log.show(self.ui);pump(.2)
        self.assertTrue(self.ui.activity_window.get_mapped())
        if os.environ.get('LAYOUT_REVIEW'):
            self.capture(self.ui.activity_window,'activity')
            self.ui.activity_window.close()
            self.ui.show_chat();pump(.3)
            self.assertLess(self.ui.shortcut_column_width, self.ui.main_root.get_width()*.5)
            self.capture(self.ui.window,'split-list')
            from keyboard_view import XkbLayout
            self.ui.keyboard.layout=XkbLayout({'layout':'us'})
            self.ui.keyboard.build_keys()
            self.ui.view_toggle.set_active(True);pump(.3)
            self.capture(self.ui.window,'split-keyboard')
    def capture(self,window,name):
        import ctypes, subprocess, shlex
        path=self.fixture.temp.name+'/capture.so'
        flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','gtk4'],text=True))
        subprocess.run(['cc','-shared','-fPIC','tests/visual_capture.c','-o',path,*flags],check=True,stderr=subprocess.DEVNULL)
        native=ctypes.CDLL(path);native.capture.argtypes=[ctypes.c_void_p,ctypes.c_char_p]
        pointer=ctypes.pythonapi.PyCapsule_GetPointer;pointer.argtypes=[ctypes.py_object,ctypes.c_char_p];pointer.restype=ctypes.c_void_p
        self.assertEqual(native.capture(pointer(window.__gpointer__,None),('/tmp/bindlume-'+name+'.png').encode()),0)
