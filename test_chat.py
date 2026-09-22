import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from chat import SessionStore, AgentRun, invocation, parse_event


class ChatTests(unittest.TestCase):
    def test_session_storage_export_rename_and_resume(self):
        with tempfile.TemporaryDirectory() as folder:
            store = SessionStore(folder)
            session = store.create('codex','Help with screenshots')
            self.assertEqual(len(store.list()),1)
            session['messages'].append(dict(role='user',content='Hello István',created_at=session['created_at']))
            session['provider_session_id'] = 'abc-123'
            store.save(session)
            stale = dict(session)
            store.rename(session,'My screenshot shortcuts')
            store.save(stale)  # a finishing worker cannot undo a manual rename
            restored = store.load(session['id'])
            self.assertEqual(restored['title'],'My screenshot shortcuts')
            self.assertEqual(restored['message_count'],1)
            copies = store.copy_values(restored)
            self.assertIn('Hello István', copies['transcript'])
            self.assertEqual(copies['id'],session['id'])
            self.assertTrue(Path(copies['path']).is_file())
            self.assertIn('codex resume abc-123',copies['resume'])
            self.assertEqual(os.stat(copies['path']).st_mode & 0o777,0o600)
            with self.assertRaises(ValueError): store.load('../../outside')
            with self.assertRaises(ValueError): store.rename(session,'  ')

    def test_read_only_tools_do_not_claim_app_updated(self):
        result = parse_event('codex',{'type':'item.completed','item':{'type':'mcp_tool_call','status':'completed'}})
        self.assertEqual(result['activity'],'App tool finished')
        failed = parse_event('codex',{'type':'item.completed','item':{'type':'mcp_tool_call','error':'oops'}})
        self.assertEqual(failed['activity'],'App tool failed')

    def test_provider_commands_and_events(self):
        fixtures = {
            'codex':{'type':'item.completed','item':{'type':'agent_message','text':'Done'}},
            'claude':{'type':'assistant','message':{'content':[{'type':'text','text':'Done'}]}},
            'gemini':{'type':'message','role':'assistant','content':'Done'},
            'opencode':{'type':'text','part':{'text':'Done'},'sessionID':'session-1'},
        }
        with tempfile.TemporaryDirectory() as folder, patch('chat.shutil.which', side_effect=lambda name:'/usr/bin/'+name):
            for provider,event in fixtures.items():
                session = {'provider':provider, 'provider_session_id':'session-1'}
                argv, env = invocation(session,Path(folder),Path('/tmp/agent_control.py'))
                self.assertEqual(argv[0],'/usr/bin/'+provider)
                if provider == 'codex':
                    self.assertIn('mcp_servers.bindlume.tools.control.approval_mode="approve"',argv)
                    self.assertTrue(any('env.DBUS_SESSION_BUS_ADDRESS=' in arg for arg in argv))
                self.assertIn('session-1',argv)
                self.assertNotIn('--dangerously-bypass-approvals-and-sandbox',argv)
                self.assertNotIn('--dangerously-skip-permissions',argv)
                self.assertIn('Done',parse_event(provider,event).values())
        self.assertEqual(parse_event('codex',{'type':'item.completed','item':{'type':'reasoning','text':'private'}}),{})

    def test_runner_persists_messages_and_errors_without_shell(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            fake = root/'fake-agent'
            fake.write_text('#!/usr/bin/python\nimport json,sys\nprompt=sys.stdin.read()\nprint(json.dumps({"type":"thread.started","thread_id":"native-id"}))\nprint(json.dumps({"type":"item.completed","item":{"type":"agent_message","text":"Saved your shortcut."}}))\n')
            fake.chmod(0o700)
            store = SessionStore(root/'chats')
            session = store.create('codex','Remember screenshot')
            events=[]
            with patch('chat.shutil.which',return_value=str(fake)):
                AgentRun(store,session,lambda *args:events.append(args)).run('Remember screenshot')
            saved = store.load(session['id'])
            self.assertEqual(saved['status'],'ready')
            self.assertEqual(saved['provider_session_id'],'native-id')
            self.assertEqual([m['role'] for m in saved['messages']],['user','assistant'])
            self.assertEqual(events[-1][0],'done')
            fake.write_text('#!/usr/bin/python\nimport sys\nsys.stdin.read()\nprint("Sign in first",file=sys.stderr)\nsys.exit(2)\n')
            with patch('chat.shutil.which',return_value=str(fake)):
                AgentRun(store,session,lambda *_:None).run('Continue')
            self.assertEqual(session['status'],'error')
            self.assertIn('Sign in first',session['messages'][-1]['content'])
