"""Validate shipped HTML references and JavaScript before publishing static assets."""
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit,unquote
import subprocess
root=Path(__file__).resolve().parents[1]/'public'
class Links(HTMLParser):
    def handle_starttag(self,tag,attrs):
        for key,value in attrs:
            if key not in ('src','href') or not value:continue
            url=urlsplit(value)
            if url.scheme or url.netloc or not url.path:continue
            path=root/unquote(url.path.lstrip('/')) if url.path.startswith('/') else current.parent/unquote(url.path)
            if path.is_dir():path=path/'index.html'
            assert path.is_file(),f'{current}: missing {value}'
for current in root.rglob('*.html'):
    text=current.read_text();Links().feed(text)
    assert '<title>' in text and 'name="viewport"' in text,current
for script in root.rglob('*.js'):subprocess.run(['node','--check',str(script)],check=True)
print('Static pages, local links, assets and JavaScript checks passed.')
