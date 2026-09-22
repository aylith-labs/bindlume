"""Read provider-reported subscription headroom without starting model turns."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import selectors
import shutil
import signal
import subprocess
import time
import threading
from urllib.request import Request, urlopen
from urllib.error import HTTPError

TTL = 300
LOCK = threading.Lock()


def window(name, used, resets=None):
    if isinstance(used, bool) or not isinstance(used, (int,float)) or not 0 <= used <= 100: return None
    return {'name':name, 'remaining_percent':round(100-used,1), 'resets_at':resets}


def normalize_codex(value):
    limits = value.get('rateLimits') or value.get('rateLimitsByLimitId',{}).get('codex') or {}
    windows = []
    for key in ('primary','secondary'):
        item = limits.get(key)
        if not item: continue
        minutes = item.get('windowDurationMins')
        name = '5h' if minutes == 300 else 'weekly' if minutes == 10080 else f'{minutes} min' if minutes else key
        reset = item.get('resetsAt')
        reset = datetime.fromtimestamp(reset, timezone.utc).isoformat() if isinstance(reset,(int,float)) else None
        result = window(name,item.get('usedPercent'),reset)
        if result: windows.append(result)
    return {'status':'available' if windows else 'unknown', 'windows':windows}


def normalize_claude(value):
    windows = []
    for key,name in [('five_hour','5h'),('seven_day','weekly')]:
        item = value.get(key)
        if not isinstance(item,dict): continue
        result = window(name,item.get('utilization'),item.get('resets_at'))
        if result: windows.append(result)
    return {'status':'available' if windows else 'unknown', 'windows':windows}


def omarchy_quota(provider):
    """Reuse a fresh record from Omarchy's collectors; never import global token totals."""
    path = Path(os.environ.get('XDG_STATE_HOME',Path.home()/'.local/state'))/'omarchy/agents/usage'/f'{provider}.json'
    try:
        data = json.loads(path.read_text())
        updated = datetime.fromisoformat(data['updatedAt'].replace('Z','+00:00'))
        age = (datetime.now(timezone.utc)-updated).total_seconds()
        if not data.get('ready') or not 0 <= age < TTL: return None
        windows=[]
        for item in data.get('limits',[]):
            percent=item.get('percent')
            if isinstance(percent,bool) or not isinstance(percent,(int,float)): continue
            result=window(item.get('label','Limit'),percent*100,item.get('resetsAt'))
            if result: windows.append(result)
        if windows: return dict(status='available',windows=windows,tier=str(data.get('tierLabel','')),source='omarchy')
    except (OSError,ValueError,KeyError,TypeError,AttributeError): pass
    return None


def codex_quota():
    cached = omarchy_quota('codex')
    if cached: return cached
    executable = shutil.which('codex')
    if not executable: return {'status':'unavailable','windows':[]}
    process = subprocess.Popen([executable,'app-server'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, start_new_session=True)
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    buffer = b''
    deadline = time.monotonic()+12
    def send(value):
        process.stdin.write((json.dumps(value)+'\n').encode())
        process.stdin.flush()
    try:
        send({'id':1,'method':'initialize','params':{'clientInfo':{'name':'bindlume_quota','version':'1.0'}}})
        while time.monotonic() < deadline:
            if not selector.select(max(0,deadline-time.monotonic())): break
            chunk = os.read(process.stdout.fileno(),65536)
            if not chunk: break
            buffer += chunk
            while b'\n' in buffer:
                line,buffer = buffer.split(b'\n',1)
                event = json.loads(line)
                if event.get('id') == 1:
                    if 'error' in event: return {'status':'unavailable','windows':[]}
                    send({'method':'initialized'})
                    send({'id':2,'method':'account/rateLimits/read','params':{}})
                elif event.get('id') == 2:
                    if 'error' in event: return {'status':'unavailable','windows':[]}
                    return normalize_codex(event.get('result',{}))
        return {'status':'unavailable','windows':[]}
    finally:
        selector.close()
        if process.poll() is None:
            os.killpg(process.pid,signal.SIGTERM)
            try: process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGKILL)
                process.wait()
        process.stdin.close()
        process.stdout.close()


def claude_quota():
    cached = omarchy_quota('claude')
    if cached: return cached
    # Claude Code's own /usage endpoint. Credentials stay in memory, are sent
    # only to Anthropic, and are never included in the cache, UI, or logs.
    root = Path(os.environ.get('CLAUDE_CONFIG_DIR',Path.home()/'.claude'))
    try:
        credentials = json.loads((root/'.credentials.json').read_text())
        token = credentials.get('claudeAiOauth',credentials).get('accessToken')
        if not token: return {'status':'unavailable','windows':[]}
        request = Request('https://api.anthropic.com/api/oauth/usage',headers={
            'Authorization':'Bearer '+token, 'anthropic-beta':'oauth-2025-04-20', 'Accept':'application/json'})
        with urlopen(request,timeout=10) as response:
            return normalize_claude(json.load(response))
    except HTTPError as error:
        return {'status':'unavailable','windows':[], 'reason':'usage_rate_limited' if error.code==429 else 'authentication_or_service'}
    except (OSError, ValueError, TypeError):
        return {'status':'unavailable','windows':[]}


def _read_quotas(providers, root, force=False):
    root = Path(root)
    path = root/'agent-usage.json'
    try: cache = json.loads(path.read_text())
    except (OSError, ValueError): cache = {}
    if not isinstance(cache, dict): cache = {}
    timestamp = time.time()
    def fetch(provider):
        previous = cache.get(provider,{})
        if not isinstance(previous, dict): previous = {}
        checked = previous.get('checked_at', 0)
        if not force and isinstance(checked, (int, float)) and 0 <= timestamp-checked < TTL: return provider,previous
        try:
            value = {'codex':codex_quota,'claude':claude_quota}.get(provider,lambda:{'status':'unknown','windows':[]})()
        except Exception:
            value = {'status':'unavailable','windows':[]}
        return provider,dict(value,checked_at=timestamp)
    with ThreadPoolExecutor(max_workers=max(1,min(4,len(providers)))) as pool:
        result = dict(pool.map(fetch,providers))
    root.mkdir(parents=True,exist_ok=True)
    temporary = path.with_suffix(f'.{os.getpid()}.tmp')
    temporary.write_text(json.dumps(result,indent=2)+'\n')
    temporary.chmod(0o600)
    temporary.replace(path)
    return result


def choose_agent(providers, quotas):
    """Maximize the tightest reported window; unknown is never called 100%."""
    candidates, exhausted = [], set()
    for order,provider in enumerate(providers):
        data = quotas.get(provider,{})
        remaining = [item['remaining_percent'] for item in data.get('windows',[]) if isinstance(item, dict)
                     and isinstance(item.get('remaining_percent'), (int, float)) and not isinstance(item['remaining_percent'], bool)
                     and 0 <= item['remaining_percent'] <= 100]
        if data.get('status') != 'available' or not remaining: continue
        if min(remaining) <= 0:
            exhausted.add(provider)
            continue
        candidates.append((min(remaining),sum(remaining)/len(remaining),-order,provider))
    if candidates: return max(candidates)[-1], 'quota'
    unknown = [provider for provider in providers if provider not in exhausted]
    if unknown: return unknown[0], 'unknown'
    raise RuntimeError('All available agents have exhausted their reported quota. Try again after a reset or choose another agent.')


def read_quotas(providers, root, force=False):
    with LOCK:
        return _read_quotas(providers, root, force)


def cached_quotas(root):
    """Never block sending on a provider's quota endpoint."""
    try:
        data = json.loads((Path(root)/'agent-usage.json').read_text())
        return data if isinstance(data,dict) else {}
    except (OSError, ValueError): return {}
