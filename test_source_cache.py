import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import source_cache

class SourceCacheTests(unittest.TestCase):
    def test_private_roundtrip_and_invalid_data(self):
        with tempfile.TemporaryDirectory() as root,patch.dict('os.environ',{'XDG_CACHE_HOME':root}):
            row=dict(id='one',key='CTRL + T',name='New tab',group='Tabs',dispatcher='',arg='')
            source_cache.write('Chromium',[row],'Defaults')
            self.assertEqual(source_cache.read('Chromium'),([row],'Defaults'))
            self.assertEqual(source_cache.path_for('Chromium').stat().st_mode & 0o777,0o600)
            self.assertIsNone(source_cache.read('Other'))
            source_cache.path_for('Chromium').write_text('{')
            self.assertIsNone(source_cache.read('Chromium'))

    def test_old_schema_and_stale_cache_are_ignored(self):
        with tempfile.TemporaryDirectory() as root,patch.dict('os.environ',{'XDG_CACHE_HOME':root}):
            source_cache.write('Omarchy',[],'')
            p=source_cache.path_for('Omarchy');data=json.loads(p.read_text());data['saved_at']=0;p.write_text(json.dumps(data))
            self.assertIsNone(source_cache.read('Omarchy'))
