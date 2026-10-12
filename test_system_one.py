import copy
import io
import json
import threading
import unittest
from http.server import HTTPServer
from unittest.mock import MagicMock, patch
import system_one as one
from system_one_server import handler

QUESTIONS = {
    'route': {'type': 'choice', 'instructions': 'Pick a route', 'criteria': {'search': 'Find shortcuts', 'other': 'Other'}},
    'relevance': {'type': 'score', 'instructions': 'Rate relevance', 'criteria': ['unrelated', 'related']},
    'urgent': {'type': 'noul', 'instructions': 'Urgent?'},
}
RESULT = {'model': 'test', 'answers': {
    'route': {'type': 'choice', 'choice': 'search', 'probabilities': {'search': .8, 'other': .2}},
    'relevance': {'type': 'score', 'score': .7, 'probabilities': {'0': .3, '1': .7}},
    'urgent': {'type': 'noul', 'noul': .3},
}}


class DecisionTests(unittest.TestCase):
    def test_all_primitives_over_real_loopback_bridge(self):
        agent = MagicMock();agent.predict.return_value = copy.deepcopy(RESULT)
        server = HTTPServer(('127.0.0.1', 0), handler(agent, 'test'))
        worker = threading.Thread(target=server.serve_forever, daemon=True);worker.start()
        try:
            prefs = {'decision_connections': {'laya': {'enabled': True, 'model': 'test', 'url': f'http://127.0.0.1:{server.server_port}/v1'}}}
            self.assertEqual(one.decide('laya', prefs, {'query': 'terminal'}, QUESTIONS), RESULT)
            agent.predict.assert_called_once_with({'query': 'terminal'}, QUESTIONS)
        finally:
            server.shutdown();server.server_close();worker.join()

    def test_disabled_and_invalid_requests_never_connect(self):
        with patch('system_one.build_opener') as opener:
            with self.assertRaises(ValueError):one.decide('laya', {}, '', QUESTIONS)
            for questions in [{}, {'a': {'type': 'chat', 'instructions': 'hello'}}, {'a': {'type':'choice','instructions':'pick','criteria':{'only':'one'}}}]:
                with self.assertRaises(ValueError):one.decide('laya', {}, '', questions)
            with self.assertRaises(ValueError):one.validate_request(float('nan'), QUESTIONS)
            opener.assert_not_called()

    def test_connection_validation(self):
        for value in [{'laya':{'url':'http://remote/v1'}}, {'laya':{'url':'https://secret@host/v1'}}, {'laya':{'url':'https:///v1'}}, {'laya':{'url':'https://host/v1?secret=x'}}, {'laya':{'enabled':'yes'}}, {'custom':{'enabled':True}}, {'unknown':{}}]:
            with self.assertRaises(ValueError):one.validate_connections(value)

    def test_jev_wire_format_and_key(self):
        opener = MagicMock();opener.open.return_value = io.BytesIO(json.dumps(RESULT).encode())
        prefs = {'decision_connections':{'jev':{'enabled':True}}}
        with patch.dict('os.environ', {'TYPESAFE_API_KEY':'test-secret'}), patch('system_one.build_opener', return_value=opener):
            one.decide('jev', prefs, 'state', QUESTIONS)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, 'https://api.typesafe.ai/v1/systemone')
        self.assertEqual(request.get_header('Authorization'), 'Bearer test-secret')
        self.assertEqual(json.loads(request.data), dict(model='jev-latest',state='state',questions=QUESTIONS))
        with patch.dict('os.environ', {}, clear=True), patch('system_one.build_opener') as build:
            with self.assertRaises(ValueError):one.decide('jev', prefs, '', QUESTIONS)
            build.assert_not_called()

    def test_bad_model_answers_rejected(self):
        for name, field, value in [('route','choice','invented'),('route','probabilities',{'search':.3}),('urgent','noul',True),('urgent','noul',float('nan')),('relevance','score',2),('route','confidence',float('inf'))]:
            result = copy.deepcopy(RESULT);result['answers'][name][field] = value
            with self.assertRaises(ValueError):one.validate_response(result, QUESTIONS)
        with self.assertRaises(ValueError):one.validate_response({'answers':{}}, QUESTIONS)

    def test_oversized_and_non_json_responses(self):
        for raw in [b'x'*(one.LIMIT+1), b'<html>error</html>']:
            opener = MagicMock();opener.open.return_value = io.BytesIO(raw)
            with patch('system_one.build_opener',return_value=opener):
                with self.assertRaises(ValueError):one.decide('laya', {'decision_connections':{'laya':{'enabled':True}}}, '', QUESTIONS)


class WorkflowTests(unittest.TestCase):
    def response(self, state, questions, probability=1):
        answers = {}
        for key, question in questions.items():
            if key == 'applicable': answers[key] = {'type':'choice','choice':'apply','probabilities':{'apply':1,'other':0}};continue
            choice = 'dark' if key == 'theme' else 'keep'
            probs = {k: 0 for k in question['criteria']};probs[choice] = probability
            if probability != 1: probs['keep'] = 1 - probability
            answers[key] = dict(type='choice', choice=choice, probabilities=probs)
        return {'model':'test','answers':answers}

    def test_settings_bot_applies_only_validated_decisions_and_prints_result(self):
        import decision_workflows as flow
        def decide(provider, prefs, state, questions): return self.response(state, questions)
        with patch.object(flow, 'decide', side_effect=decide), patch('agent_control.request', side_effect=[{}, {'theme':'dark'}]) as control:
            events = list(flow.events('decision_laya', {}, 'Dark theme please', threading.Event()))
        self.assertEqual(control.call_args_list[-1].args[0], {'operation':'decision_apply','arguments':{'values':{'theme':'dark'}}})
        self.assertIn('"theme": "dark"', events[0]['delta'])
        self.assertIn('Applied settings:', events[0]['delta'])
        for values in [{'chat_memory_enabled':True}, {'chat_token_usage':True}, {'theme':'dark','compact':1}]:
            with self.assertRaises(ValueError):flow.validate_settings(values)

    def test_uncertainty_and_cancellation_do_not_mutate(self):
        import decision_workflows as flow
        with patch.object(flow,'decide',side_effect=lambda p,prefs,s,q:self.response(s,q,.6)), patch('agent_control.request',return_value={}) as control:
            events = list(flow.events('decision_laya', {}, 'Maybe dark', threading.Event()))
            self.assertIn('uncertain', events[0]['delta'])
            self.assertEqual(control.call_count,1)
        cancelled=threading.Event()
        def decide(p,prefs,s,q):cancelled.set();return self.response(s,q)
        with patch.object(flow,'decide',side_effect=decide),patch('agent_control.request',return_value={}) as control:
            self.assertEqual(list(flow.events('decision_laya',{},'Dark',cancelled)),[])
            self.assertEqual(control.call_count,1)

    def test_router_uses_settings_bot_only_for_confident_settings_request(self):
        import decision_workflows as flow
        prefs={'decision_router':'laya'}
        with patch.object(flow,'decide',return_value={'answers':{'route':{'choice':'settings','probabilities':{'settings':.95,'assistant':.05}}}}):
            self.assertEqual(flow.route(prefs,'dark',['codex','decision_laya'],'codex'),'decision_laya')
            self.assertEqual(flow.route(prefs,'dark',['codex'],'codex'),'codex')
        with patch.object(flow,'decide',return_value={'answers':{'route':{'choice':'settings','probabilities':{'settings':.55,'assistant':.45}}}}):
            self.assertEqual(flow.route(prefs,'help',['codex','decision_laya'],'codex'),'codex')

    def test_rank_preserves_ids_and_uses_scores(self):
        import decision_workflows as flow
        items=[{'id':str(i),'name':'shortcut','key':'SUPER + A'} for i in range(26)]
        with patch.object(flow,'decide',return_value={'answers':{str(i):{'score': i/24} for i in range(24)}}):
            ranked=flow.rank('laya',{},'shortcut',items)
        self.assertEqual([r['id'] for r in ranked],[str(i) for i in reversed(range(24))]+['24','25'])

    def test_decision_provider_runs_through_chat_storage(self):
        import tempfile
        from chat import SessionStore, AgentRun
        with tempfile.TemporaryDirectory() as folder:
            store=SessionStore(folder);session=store.create('decision_laya','dark')
            with patch('decision_workflows.events',return_value=iter([{'delta':'Applied settings: dark','model':'laya-test'}])):
                AgentRun(store,session,lambda *_:None).run('dark')
            saved=store.load(session['id'])
            self.assertEqual(saved['status'],'ready')
            self.assertEqual(saved['model'],'laya-test')
            self.assertEqual(saved['messages'][-1]['content'],'Applied settings: dark')

    def test_setting_shortlist_matches_labels_and_avoids_substrings(self):
        import decision_workflows as flow
        self.assertEqual(flow.requested_settings('Switch to dark theme.'), ['theme'])
        self.assertEqual(flow.requested_settings('Please highlight this text.'), [])
        self.assertEqual(flow.requested_settings('Sötét téma'), ['theme'])
        self.assertEqual(flow.requested_settings('Disable window animations'), ['window_animations'])
