"""Keep the public entry points aligned with the shipped application identity."""
from pathlib import Path
import unittest
import app
import agent_control

class BrandingTests(unittest.TestCase):
    def test_public_identity(self):
        root = Path(__file__).parent
        self.assertEqual(app.APP_ID, 'com.aylith.Bindlume')
        self.assertEqual(agent_control.BUS, app.APP_ID)
        self.assertEqual(agent_control.OBJECT, '/com/aylith/Bindlume/Control')
        for name in ('README.md', 'bindlume.desktop', '.aylith/project.md', 'skills/bindlume/SKILL.md'):
            text = (root/name).read_text()
            self.assertIn('Bindlume', text)
            self.assertNotIn('Omarchy Shortcuts', text)
            self.assertNotIn('omarchy-shortcuts', text)
        self.assertIn('https://bindlume.aylith.com', (root/'.aylith/project.md').read_text())
