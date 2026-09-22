import io
import json
import threading
import unittest
from unittest.mock import patch, MagicMock
import chat_api


def stream(*deltas):
    return io.BytesIO(b''.join(b'data: '+json.dumps({'choices':[{'delta':d}]}).encode()+b'\n\n' for d in deltas)+b'data: [DONE]\n\n')

class DirectApiTests(unittest.TestCase):
    def test_streamed_tool_arguments_and_confirmed_result(self):
        opener=MagicMock()
        opener.open.side_effect=[stream({'tool_calls':[{'index':0,'id':'one','function':{'name':'control','arguments':'{"operation":"search",'}}]},
                                       {'tool_calls':[{'index':0,'function':{'arguments':'"arguments":{"query":"theme"}}'}}]}),
                                 stream({'content':'Theme menu: '},{'content':'Super + Shift + Ctrl + Space.'})]
        with patch('chat_api.build_opener',return_value=opener),patch('agent_control.request',return_value={'key':'SUPER CTRL SHIFT + SPACE'}) as control:
            result=list(chat_api.events('api_ollama',{},'Find theme',threading.Event()))
        control.assert_called_once_with({'operation':'search','arguments':{'query':'theme'}},start=False)
        self.assertEqual(''.join(r.get('delta','') for r in result),'Theme menu: Super + Shift + Ctrl + Space.')
        self.assertIn({'activity':'App tool finished'},result)
        followup=json.loads(opener.open.call_args_list[1].args[0].data)
        self.assertEqual(followup['messages'][-1]['role'],'tool')
        self.assertEqual(followup['reasoning_effort'],'none')

    def test_cancel_before_request(self):
        cancelled=threading.Event();cancelled.set()
        with patch('chat_api.build_opener') as build:
            self.assertEqual(list(chat_api.events('api_ollama',{},'hello',cancelled)),[])
            build.return_value.open.assert_not_called()

    def test_remote_plaintext_and_url_credentials_rejected(self):
        for url in ['http://remote.example/v1','https://secret@example.com/v1','https://example.com/v1?key=secret']:
            with self.assertRaises(ValueError):chat_api.connection('api_custom',{'chat_connections':{'api_custom':{'url':url,'model':'m'}}})

    def test_failed_mutation_is_returned_as_error(self):
        opener=MagicMock();opener.open.side_effect=[stream({'tool_calls':[{'index':0,'id':'a','function':{'name':'control','arguments':'{"operation":"settings","arguments":{"key":"no"}}'}}]}),stream({'content':'Unable to apply.'})]
        with patch('chat_api.build_opener',return_value=opener),patch('agent_control.request',side_effect=ValueError('Unknown setting')):
            events=list(chat_api.events('api_ollama',{},'set',threading.Event()))
        self.assertIn({'activity':'App tool failed'},events)
        self.assertNotIn({'activity':'App tool finished'},events)
