import sqlite3
import unittest
from unittest.mock import patch
from director import observer

class ObserverTests(unittest.TestCase):
 def setUp(self):
  self.c=sqlite3.connect(":memory:")
  self.c.row_factory=sqlite3.Row
  observer.init_db(self.c)
 def tearDown(self):self.c.close()
 def test_repository_restriction(self):
  with self.assertRaises(ValueError):observer.api("bad/repo/extra","")
  with self.assertRaises(ValueError):observer.api("good/repo","https://evil.invalid/")
 def test_review_is_not_merge_permission(self):
  pr={"head":{"sha":"abc"},"draft":False}
  self.assertIn("не подтверждён",observer.review(pr,[]))
  self.assertIn("запрещено",observer.review(pr,[{"head_sha":"abc","status":"queued","conclusion":None}]))
  self.assertIn("требуется проверка",observer.review(pr,[{"head_sha":"abc","status":"completed","conclusion":"success"}]))
 def test_sync_and_event_dedup(self):
  state={"repo":"test/repo","default_branch":"main","prs":[{"number":3,"title":"Test","url":"https://github.com/test/repo/pull/3","branch":"fix","sha":"a","draft":False,"review":"CI не подтверждён"}],"runs":[],"total_open_pr":1,"total_runs_sampled":0}
  with patch.object(observer,"snapshot",return_value=state):
   self.assertIsNotNone(observer.sync(self.c,"test/repo"))
   first=self.c.execute("SELECT count(*) FROM github_events").fetchone()[0]
   self.assertIsNotNone(observer.sync(self.c,"test/repo"))
   self.assertEqual(first,self.c.execute("SELECT count(*) FROM github_events").fetchone()[0])
   self.assertEqual(observer.read(self.c)[1]["status"],"ok")
 def test_stale_snapshot_kept_on_failure(self):
  state={"repo":"test/repo","default_branch":"main","prs":[],"runs":[],"total_open_pr":0,"total_runs_sampled":0}
  with patch.object(observer,"snapshot",return_value=state):observer.sync(self.c,"test/repo")
  with patch.object(observer,"snapshot",side_effect=ValueError("bad")):self.assertIsNone(observer.sync(self.c,"test/repo"))
  data,mon,_=observer.read(self.c)
  self.assertEqual(mon["status"],"error")
  self.assertEqual(data["default_branch"],"main")
