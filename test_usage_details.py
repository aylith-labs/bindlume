import unittest
from datetime import datetime,timezone
from usage_view import relative_time,token_details,provider_summary
class UsageDetailsTests(unittest.TestCase):
 def test_relative_times(self):
  now=datetime(2026,9,21,12,tzinfo=timezone.utc)
  self.assertEqual(relative_time('2026-09-21T10:00:00+00:00',now),'2 h ago')
  self.assertEqual(relative_time('2026-09-20T10:00:00Z',now),'1 d ago')
  self.assertEqual(relative_time('bad',now),'bad')
 def test_tokens_prefer_aggregate_and_keep_cache_separate(self):
  rows=token_details({'usage_total':{'input_tokens':69437,'cached_input_tokens':59008,'output_tokens':205,'reasoning_output_tokens':0},'usage':{'input_tokens':1}})
  self.assertIn(('Input tokens','69,437'),rows)
  self.assertIn(('Cached input tokens','59,008'),rows)
  self.assertNotIn(('Reasoning tokens','0'),rows)
 def test_selector_includes_quota_summary(self):
  self.assertIn('84% left',provider_summary('codex',{'tier':'pro','windows':[{'name':'weekly','remaining_percent':84}]}))
