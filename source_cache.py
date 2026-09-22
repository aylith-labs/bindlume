"""Small, private display cache. Refresh live sources without blanking the UI."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time


def path_for(source):
    root = Path(os.environ.get('XDG_CACHE_HOME') or Path.home()/'.cache')/'bindlume/shortcuts'
    return root/(hashlib.sha256(source.encode()).hexdigest()+'.json')


def read(source):
    try:
        data = json.loads(path_for(source).read_text())
        if data.get('version') != 1 or data.get('source') != source: return None
        if not 0 <= time.time()-data['saved_at'] < 7*86400: return None
        rows = data['items']
        if not isinstance(rows, list) or len(rows)>20000: return None
        if any(not isinstance(row,dict) or any(not isinstance(row.get(k),str) for k in ('id','key','name','group','dispatcher','arg')) for row in rows): return None
        return rows, str(data.get('note',''))
    except (OSError, ValueError, TypeError, KeyError): return None


def write(source, items, note):
    path = path_for(source)
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as f:
            json.dump(dict(version=1,source=source,saved_at=time.time(),items=items,note=note),f)
            temporary = Path(f.name)
        temporary.replace(path)
    except OSError:
        if 'temporary' in locals(): temporary.unlink(missing_ok=True)
