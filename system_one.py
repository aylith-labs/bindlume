"""Bounded, opt-in System One requests; decisions never execute app actions."""
import json
import math
import os
import re
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler


def tr(source):
    # The optional inference process need not install GTK. Its HTTP errors are generic.
    try:
        from localization import text
    except ModuleNotFoundError as error:
        if error.name != "gi": raise
        return source
    return text(source)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

PROVIDERS = {'jev': 'Jev', 'laya': 'Laya', 'von': 'Von', 'custom': 'Custom API'}
DEFAULTS = {
    'jev': ('https://api.typesafe.ai/v1', 'TYPESAFE_API_KEY', 'jev-latest'),
    'laya': ('http://127.0.0.1:8001/v1', '', 'convaiinnovations/laya'),
    'von': ('http://127.0.0.1:8000/v1', '', 'von-1.0.0'),
    'custom': ('http://127.0.0.1:8002/v1', '', ''),
}
LIMIT = 256_000


def validate_connections(connections):
    if not isinstance(connections, dict) or set(connections) - DEFAULTS.keys():
        raise ValueError(tr('Invalid model connection.'))
    for provider, settings in connections.items():
        if not isinstance(settings, dict) or set(settings) - {'url', 'key_env', 'model', 'enabled'}:
            raise ValueError(tr('Invalid model connection.'))
        if 'enabled' in settings and type(settings['enabled']) is not bool:
            raise ValueError(tr('Invalid model connection.'))
        if any(not isinstance(v, str) or len(v) > 2048 for k, v in settings.items() if k != 'enabled'):
            raise ValueError(tr('Invalid model connection.'))
        base, env, model = DEFAULTS[provider]
        base = settings.get('url', base)
        try:
            parsed = urlsplit(base)
            _ = parsed.port
        except ValueError:
            raise ValueError(tr('Invalid model connection.')) from None
        if (not parsed.hostname or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment or any(c.isspace() or ord(c) < 32 for c in base)
                or (parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1', '::1')))):
            raise ValueError(tr('Invalid model connection.'))
        env = settings.get('key_env', env)
        if env and not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', env):
            raise ValueError(tr('Invalid model connection.'))
        if settings.get('enabled') and not settings.get('model', model).strip():
            raise ValueError(tr('Choose a model in AI companion settings.'))
    return connections


def validate_request(state, questions):
    error = tr('Invalid decision request.')
    if not isinstance(questions, dict) or not 1 <= len(questions) <= 32:
        raise ValueError(error)
    for name, question in questions.items():
        if not isinstance(name, str) or not name or not isinstance(question, dict):
            raise ValueError(error)
        kind = question.get('type')
        if kind not in ('choice', 'score', 'noul') or 'instructions' not in question:
            raise ValueError(error)
        if set(question) - {'type', 'instructions', 'criteria'}:
            raise ValueError(error)
        criteria = question.get('criteria')
        if kind == 'choice' and (not isinstance(criteria, dict) or not 2 <= len(criteria) <= 255 or any(not isinstance(k, str) or not k for k in criteria)):
            raise ValueError(error)
        if kind == 'noul' and criteria is not None and (not isinstance(criteria, dict) or set(criteria) - {'true', 'false'}):
            raise ValueError(error)
        if kind == 'score' and (not isinstance(criteria, list) or not 2 <= len(criteria) <= 255):
            raise ValueError(error)
    try:
        encoded = json.dumps({'state': state, 'questions': questions}, allow_nan=False).encode()
    except (ValueError, TypeError):
        raise ValueError(error) from None
    if len(encoded) > LIMIT:
        raise ValueError(tr('Model response exceeded limits.'))


def validate_response(result, questions):
    def number(value, low, high):
        return type(value) in (int, float) and math.isfinite(value) and low <= value <= high
    def fail():
        raise ValueError(tr('Invalid decision response.'))
    if not isinstance(result, dict) or not isinstance(result.get('answers'), dict) or set(result['answers']) != set(questions):
        fail()
    for name, question in questions.items():
        answer = result['answers'][name]
        kind = question['type']
        if not isinstance(answer, dict) or answer.get('type') != kind:
            fail()
        if 'confidence' in answer and not number(answer['confidence'], 0, 1):
            fail()
        if kind == 'noul':
            if not number(answer.get('noul'), 0, 1): fail()
            continue
        criteria = question['criteria']
        if kind == 'choice':
            if not isinstance(answer.get('choice'), str) or answer['choice'] not in criteria: fail()
            labels = set(criteria)
        else:
            if not number(answer.get('score'), 0, len(criteria) - 1): fail()
            labels = {str(i) for i in range(len(criteria))}
        probabilities = answer.get('probabilities')
        if not isinstance(probabilities, dict) or set(probabilities) != labels:
            fail()
        if any(not number(p, 0, 1) for p in probabilities.values()) or abs(sum(probabilities.values()) - 1) > .01:
            fail()
    return result


def decide(provider, prefs, state, questions):
    validate_request(state, questions)
    connections = prefs.get('decision_connections', {})
    validate_connections(connections)
    if not isinstance(provider, str) or provider not in DEFAULTS:
        raise ValueError(tr('Invalid model connection.'))
    settings = connections.get(provider, {})
    if not settings.get('enabled'):
        raise ValueError(tr('Enable this decision connection first.'))
    base, env, model = DEFAULTS[provider]
    base, env, model = (settings.get('url', base).rstrip('/'), settings.get('key_env', env), settings.get('model', model).strip())
    key = os.environ.get(env, '') if env else ''
    if (provider == 'jev' or env) and not key:
        raise ValueError(tr('Configure an API key before connecting.'))
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
    if key: headers['Authorization'] = 'Bearer ' + key
    body = json.dumps(dict(model=model, state=state, questions=questions), allow_nan=False).encode()
    from model_insights import record, usage
    insight=record(prefs,model,'System One',body.decode('utf-8'))
    request = Request(base + '/systemone', data=body, headers=headers)
    with build_opener(NoRedirect()).open(request, timeout=60) as response:
        raw = response.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise ValueError(tr('Model response exceeded limits.'))
    try:
        result = json.loads(raw)
    except (ValueError, UnicodeError):
        raise ValueError(tr('Invalid decision response.')) from None
    result=validate_response(result, questions)
    usage(insight,result.get('usage',{}))
    return result
