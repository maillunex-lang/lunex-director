import sqlite3
import unittest
from director import importer
class ImportTests(unittest.TestCase):
 def setUp(self):
  self.c=sqlite3.connect(":memory:");self.c.row_factory=sqlite3.Row
  self.c.execute("CREATE TABLE tasks(id INTEGER PRIMARY KEY,title TEXT NOT NULL,body TEXT NOT NULL,branch TEXT NOT NULL DEFAULT '',status TEXT NOT NULL DEFAULT 'open',created_at TEXT NOT NULL,pr_url TEXT NOT NULL DEFAULT '',report TEXT NOT NULL DEFAULT '')")
  importer.ensure_schema(self.c)
  self.state={"prs":[{"number":86,"title":"Consent","branch":"v2/consent-1"}]}
 def tearDown(self):self.c.close()
 def test_import_idempotent_and_unverified(self):
  self.assertEqual(importer.import_snapshot(self.c,"maillunex-lang/LunexEconom",self.state,"2026-11-16"),1)
  self.assertEqual(importer.import_snapshot(self.c,"maillunex-lang/LunexEconom",self.state,"2026-11-16"),0)
  row=self.c.execute("SELECT * FROM tasks").fetchone()
  self.assertEqual(row["source"],"github")
  self.assertEqual(row["allowed_files"],"")
  self.assertIn("неизвестны",row["body"])
 def test_manual_branch_not_duplicated(self):
  self.c.execute("INSERT INTO tasks(title,body,branch,created_at) VALUES('Manual','Prompt','v2/consent-1','now')")
  self.assertEqual(importer.import_snapshot(self.c,"maillunex-lang/LunexEconom",self.state,"now"),0)
  self.assertEqual(self.c.execute("SELECT count(*) FROM tasks").fetchone()[0],1)
 def test_no_unsafe_scope_inference(self):
  self.state["prs"][0]["files"]=["server/platform/api.py"]
  importer.import_snapshot(self.c,"maillunex-lang/LunexEconom",self.state,"now")
  self.assertEqual(self.c.execute("SELECT allowed_files FROM tasks").fetchone()[0],"")
