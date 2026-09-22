"""Desktop icons and bounded, cached, first-party web favicons."""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import time
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

from .catalog import CatalogDiscovery
from .shortcuts import ShortcutManager

MAX_BYTES = 256 * 1024


def origin(url):
    parsed = urlsplit(url)
    if parsed.scheme not in ('https', 'http') or not parsed.hostname:
        return ''
    return f'{parsed.scheme}://{parsed.netloc}'


class IconLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag.lower() == 'link' and 'icon' in attrs.get('rel', '').lower():
            if attrs.get('href'):
                self.links.append(attrs['href'])


def read_url(url):
    if not origin(url):
        raise ValueError('Unsupported icon URL')
    request = Request(url, headers={'User-Agent': 'Omarchy-Shortcuts/1.0 (favicon lookup)'})
    with urlopen(request, timeout=2) as response:
        data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError('Icon response too large')
        return data


def image_extension(data):
    if data.startswith(b'\x89PNG\r\n\x1a\n'): return '.png'
    if data.startswith(b'\x00\x00\x01\x00'): return '.ico'
    if data.startswith(b'\xff\xd8\xff'): return '.jpg'
    if data.startswith(b'RIFF') and data[8:12] == b'WEBP': return '.webp'
    try:
        if ET.fromstring(data).tag.split('}')[-1] == 'svg': return '.svg'
    except ET.ParseError:
        pass
    return ''


def favicon(site):
    cache = Path(os.environ.get('XDG_CACHE_HOME', str(Path.home()/'.cache'))) / 'bindlume/favicons'
    cache.mkdir(parents=True, exist_ok=True)
    key = sha256(site.encode()).hexdigest()
    for extension in ('.png', '.ico', '.jpg', '.webp', '.svg'):
        path = cache / (key + extension)
        if path.is_file():
            return str(path)
    failed = cache / (key + '.missing-v2')
    if failed.exists() and time.time() - failed.stat().st_mtime < 86400:
        return ''
    candidates = [site + '/favicon.ico']
    for attempt in range(2):
        for url in candidates[:4]:
            try:
                data = read_url(url)
                extension = image_extension(data)
                if not extension:
                    continue
                path = cache / (key + extension)
                temporary = cache / (key + f'.{os.getpid()}.tmp')
                temporary.write_bytes(data)
                temporary.replace(path)
                return str(path)
            except Exception:
                continue
        if attempt == 0:
            try:
                parser = IconLinks()
                parser.feed(read_url(site + '/').decode('utf-8', errors='replace'))
                candidates = [urljoin(site + '/', link) for link in parser.links if not link.startswith('data:')]
            except Exception:
                break
    failed.touch()
    return ''


def assets():
    applications, _warnings = CatalogDiscovery()._applications('en')
    icons = {item.target_id: item.icon for item in applications if item.icon}
    actions = ShortcutManager().status()['actions']
    targets = {action.get('targetId', '') for action in actions}
    sites = {origin(target[7:]) for target in targets if target.startswith('webapp:')}
    sites.discard('')
    # Installed web-app icons also cover alternate paths at the same site.
    for target, icon in list(icons.items()):
        if target.startswith('webapp:'):
            icons.setdefault('webapp:' + origin(target[7:]), icon)
    with ThreadPoolExecutor(max_workers=8) as pool:
        for site, icon in zip(sorted(sites), pool.map(favicon, sorted(sites))):
            if icon:
                icons['webapp:' + site] = icon
                for target in targets:
                    if target.startswith('webapp:') and origin(target[7:]) == site:
                        icons[target] = icon
    return icons
