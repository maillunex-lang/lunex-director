import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from director import app

class MVPTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory()
        self.orig=app.DB_PATH
        app.DB_PATH=Path(self.t.name)/'test.sqlite'
        app.init_db()

    def tearDown(self):
        app.DB_PATH=self.orig
        self.t.cleanup()

    def test_database_and_audit(self):
        with app.get_conn() as c:
            cur=c.execute('INSERT INTO tasks(title,body,created_at) VALUES(?,?,?)',('test','prompt',app.utc()))
            app.audit(c,'task_created',cur.lastrowid)
        self.assertIn('test',app.render_dashboard().decode())
        self.assertIn('task_created',app.render_audit().decode())

    def test_html_escaping(self):
        self.assertEqual(app.e('<img src=x>'),'&lt;img src=x&gt;')

    def test_no_github_write_methods(self):
        import inspect
        s=inspect.getsource(app.fetch_repo)
        self.assertNotIn('method="POST"',s)
        self.assertNotIn('method="PATCH"',s)

    def test_repo_validation(self):
        with patch.object(app,'REPO','evil?injection'):
            with self.assertRaises(RuntimeError):app.fetch_repo('/pulls')

if __name__=='__main__':unittest.main()
