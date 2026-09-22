import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import agent_quota as quota


class QuotaTests(unittest.TestCase):
    def test_normalize_and_choose_tightest_window(self):
        codex=quota.normalize_codex({'rateLimits':{'primary':{'usedPercent':10,'windowDurationMins':300},'secondary':{'usedPercent':75,'windowDurationMins':10080}}})
        claude=quota.normalize_claude({'five_hour':{'utilization':30},'seven_day':{'utilization':40}})
        self.assertEqual([w['name'] for w in codex['windows']],['5h','weekly'])
        self.assertEqual(quota.choose_agent(['codex','claude'],{'codex':codex,'claude':claude}),('claude','quota'))
        self.assertIsNone(quota.window('5h',float('nan')))
        self.assertIsNone(quota.window('5h',True))

    def test_unknown_is_not_unlimited_and_exhausted_is_not_selected(self):
        exhausted={'status':'available','windows':[{'remaining_percent':0}]}
        available={'status':'available','windows':[{'remaining_percent':1}]}
        self.assertEqual(quota.choose_agent(['gemini','claude'],{'claude':available}),('claude','quota'))
        self.assertEqual(quota.choose_agent(['codex','gemini'],{'codex':exhausted}),('gemini','unknown'))
        with self.assertRaisesRegex(RuntimeError,'exhausted'):quota.choose_agent(['codex'],{'codex':exhausted})

    def test_cache_expiry_refresh_and_malformed_cache(self):
        with tempfile.TemporaryDirectory() as root,patch('agent_quota.codex_quota',return_value={'status':'available','windows':[{'remaining_percent':87}]}) as read:
            path=Path(root)/'agent-usage.json';path.write_text('[]')
            with patch('agent_quota.time.time',return_value=1000):
                quota.read_quotas(['codex'],root)
                quota.read_quotas(['codex'],root)
                self.assertEqual(read.call_count,1)
                quota.read_quotas(['codex'],root,force=True)
                self.assertEqual(read.call_count,2)
            with patch('agent_quota.time.time',return_value=1400):quota.read_quotas(['codex'],root)
            self.assertEqual(read.call_count,3)
            self.assertEqual(path.stat().st_mode & 0o777,0o600)
            self.assertNotIn('accessToken',path.read_text())
