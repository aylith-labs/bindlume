import threading
import tempfile
import unittest
from unittest.mock import patch
from decision_commands import plan, execute, AMBIGUOUS
from chat import AgentRun, SessionStore


class CommandTests(unittest.TestCase):
    def test_command_families_and_negations(self):
        cases={'enable filters':('view',{'show_filters':True}),
               'disable filters':('features',{'name':'layouts','enabled':False}),
               'enable all features':('features',{'name':'all','enabled':True}),
               'show hidden shortcuts':('view',{'visibility':'hidden'}),
               'use keyboard layout':('view',{'layout':'keyboard'}),
               'open settings':('open',{'surface':'settings'}),
               'Switch to dark theme.':('settings',{'key':'theme','value':'dark'}),
               'set font size to 16':('settings',{'key':'font_size','value':16}),
               'enable token tracking':('settings',{'key':'chat_token_usage','value':True}),
               'filter by ctrl shift':('view',{'modifiers':['CTRL','SHIFT']})}
        for text,(operation,args) in cases.items():
            with self.subTest(text=text):self.assertEqual(plan(text),{'operation':operation,'arguments':args})
        for text in ['do not enable filters','explain how to enable filters','enable filters and delete everything','set font size to 400']:
            self.assertIsNone(plan(text))

    def test_reported_examples_use_actual_control_results(self):
        rows=[dict(id='theme',title='Theme picker',keys='SUPER CTRL SHIFT + SPACE',source='Omarchy')]
        with patch('agent_control.request',return_value=rows) as control:
            reply=execute('show themes shortcut',control,threading.Event())
            self.assertIn('SUPER CTRL SHIFT + SPACE',reply[0]['delta'])
            self.assertEqual(control.call_args.args[0]['operation'],'search')
        with patch('agent_control.request',return_value={'enabled_features':['layouts'],'filters':{'show_filters':True}}) as control:
            reply=execute('enable filters',control,threading.Event())
            self.assertIn('layouts',reply[0]['delta'])
            control.assert_called_once_with({'operation':'view','arguments':{'show_filters':True}},start=False)

    def test_ambiguous_bookmark_does_not_mutate(self):
        rows=[dict(id=str(i),title='Screenshot '+str(i),keys='PRINT',source='Omarchy') for i in range(2)]
        with patch('agent_control.request',return_value=rows) as control:
            reply=execute('bookmark screenshot',control,threading.Event())
            self.assertIn(AMBIGUOUS,reply[0]['delta']);self.assertEqual(control.call_count,1)

    def test_cancelled_command_never_calls_control(self):
        stop=threading.Event();stop.set()
        with patch('agent_control.request') as control:
            self.assertEqual(execute('enable filters',control,stop),[])
            control.assert_not_called()

    def test_auto_handoff_preserves_one_user_message_and_final_provider(self):
        with tempfile.TemporaryDirectory() as folder:
            store=SessionStore(folder);session=store.create('decision_laya','Explain this')
            session['selection']='auto';session['companion_preferences']={'decision_connections':{'laya':{'enabled':True}}}
            emitted=[]
            with patch('decision_workflows.events',return_value=iter([{'handoff':True,'delta':'No supported setting change was selected.'}])),patch('chat.available_agents',return_value=['decision_laya','api_ollama']),patch('chat_api.events',return_value=iter([{'delta':'Here is the explanation.','model':'general'}])):
                AgentRun(store,session,lambda *event:emitted.append(event)).run('Explain this')
            self.assertEqual(session['provider'],'api_ollama')
            self.assertEqual(session['selection'],'auto')
            self.assertEqual([m['role'] for m in session['messages']],['user','assistant'])
            self.assertEqual(session['messages'][-1]['content'],'Here is the explanation.')
            self.assertFalse(any('No supported' in str(event) for event in emitted))

    def test_auto_does_not_replay_failed_app_mutation(self):
        with tempfile.TemporaryDirectory() as folder:
            store=SessionStore(folder);session=store.create('decision_laya','enable filters');session['selection']='auto'
            with patch('decision_workflows.events',side_effect=ValueError('App write failed')),patch('chat.available_agents') as agents:
                AgentRun(store,session,lambda *_:None).run('enable filters')
            agents.assert_not_called();self.assertEqual(session['status'],'error')

    def test_local_detection_excludes_remote_custom_connection(self):
        from decision_workflows import local_agents
        self.assertEqual(local_agents({'decision_connections':{'laya':{'enabled':True},'jev':{'enabled':True},'custom':{'enabled':True,'url':'https://example.com/v1'}}}),['decision_laya'])
