import sqlite3
import unittest
from director import tasklink
class TaskLinkTests(unittest.TestCase):
 def setUp(self):
  self.c=sqlite3.connect(":memory:");self.c.row_factory=sqlite3.Row
  self.c.execute("CREATE TABLE tasks(id INTEGER PRIMARY KEY,title TEXT,branch TEXT,pr_url TEXT)")
  tasklink.ensure_schema(self.c)
 def tearDown(self):self.c.close()
 def test_match_exact_branch(self):
  self.c.execute("INSERT INTO tasks(title,branch,pr_url) VALUES('Consent','v2/consent-1','')")
  task,how=tasklink.match_task(self.c,"maillunex-lang/LunexEconom",86,"v2/consent-1")
  self.assertEqual(how,"branch");self.assertEqual(task["title"],"Consent")
 def test_ambiguous_branch_is_not_assumed(self):
  for i in range(2):self.c.execute("INSERT INTO tasks(title,branch,pr_url) VALUES('Consent','v2/consent-1','')")
  task,how=tasklink.match_task(self.c,"maillunex-lang/LunexEconom",86,"v2/consent-1")
  self.assertIsNone(task);self.assertEqual(how,"ambiguous")
 def test_pr_url_validation(self):
  self.assertEqual(tasklink.pr_number("https://github.com/maillunex-lang/LunexEconom/pull/86","maillunex-lang/LunexEconom"),86)
  self.assertIsNone(tasklink.pr_number("https://github.com/other/repo/pull/86","maillunex-lang/LunexEconom"))
 def test_schema_migration_is_idempotent(self):
  tasklink.ensure_schema(self.c)
  self.assertIn("allowed_files",[x[1] for x in self.c.execute("PRAGMA table_info(tasks)")])
