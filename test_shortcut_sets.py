import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import shortcut_sets as sets
import binding_sources as sources


class PluginTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.patches=[patch.object(sets,'BUILTIN',self.root/'bundled'),
                      patch.object(sets,'user_directory',return_value=self.root/'user')]
        for p in self.patches:p.start();self.addCleanup(p.stop)
        self.data=dict(version=1,id='example',name='Example',description='Test reference',
                       shortcuts=[dict(id='find',keys='CTRL + F',title='Find')])
        self.addCleanup(self.restore)

    def restore(self):
        for p in self.patches:p.stop()
        sources.refresh_registry()

    def write(self, data=None, name='example.json'):
        root=self.root/'user';root.mkdir(exist_ok=True)
        path=root/name;path.write_text(json.dumps(data or self.data));return path

    def test_discovery_skips_invalid_empty_and_duplicate_plugins(self):
        self.write()
        self.write(dict(self.data,shortcuts=[]),'empty.json')
        self.write(dict(self.data,id='duplicate'),'duplicate.json')
        names=sources.refresh_registry()
        self.assertEqual(names.count('Example'),1)
        self.assertEqual(len(sets.ERRORS),2)
        self.assertTrue(sets.installed('Example'))
        rows,_=sources.load('Example')
        self.assertEqual(len(rows),1)
        self.assertFalse(rows[0]['dispatcher'])

    def test_detection_missing_present_and_desktop_install(self):
        self.write(dict(self.data,detect=dict(executables=['example'],desktop_ids=['example.desktop'])))
        sources.refresh_registry()
        with patch.object(sets.shutil,'which',return_value=None), patch.dict(os.environ,{'XDG_DATA_HOME':str(self.root/'data'),'XDG_DATA_DIRS':str(self.root/'system')}):
            self.assertFalse(sets.installed('Example'))
            self.assertEqual(sources.load('Example')[0],[])
            desktop=self.root/'data/applications/example.desktop';desktop.parent.mkdir(parents=True);desktop.touch()
            self.assertTrue(sets.installed('Example'))
        with patch.object(sets.shutil,'which',return_value='/bin/example'):
            self.assertTrue(sets.installed('Example'))

    def test_ids_survive_label_and_chord_edits(self):
        self.write();sources.refresh_registry();before=sources.load('Example')[0][0]['id']
        self.data['shortcuts'][0].update(title='Search',keys='CTRL + G')
        self.write();sources.refresh_registry();self.assertEqual(sources.load('Example')[0][0]['id'],before)

    def test_import_validation_is_non_destructive(self):
        file=self.root/'import.json';file.write_text(json.dumps(self.data));sources.refresh_registry()
        path=sets.install_file(file);sources.refresh_registry()
        with self.assertRaises(ValueError):sets.install_file(file)
        self.assertEqual(json.loads(path.read_text()),self.data)
        for change in ({'command':'rm anything'}, {'shortcuts':[]}, {'version':2}, {'detect':{'executables':['../foo']}}):
            with self.assertRaises(ValueError):sets.validate(dict(self.data,**change))
        malicious=copy.deepcopy(self.data);malicious['shortcuts'][0]['dispatcher']='exec'
        with self.assertRaises(ValueError):sets.validate(malicious)

    def test_template_is_valid_and_unique(self):
        sources.refresh_registry()
        first=sets.create_template();second=sets.create_template()
        self.assertNotEqual(first,second)
        self.assertTrue(sets.read(first)['shortcuts'])

    def test_live_integrations_require_installed_commands(self):
        with patch.object(sets.shutil,'which',return_value=None):
            for name in sets.LIVE:self.assertFalse(sets.installed(name))
            for name in ('Tmux','Herdr','Shefrd'):
                with patch.object(sources,'run') as run:
                    self.assertEqual(sources.load(name)[0],[]);run.assert_not_called()

    def test_bundled_browser_sets_validate(self):
        directory=Path(__file__).with_name('bundled-shortcut-sets')
        for name in ('google-chrome','chromium'):
            data=sets.read(directory/(name+'.json'))
            self.assertEqual(len(data['shortcuts']),30)
            self.assertTrue(data['detect']['executables'])
