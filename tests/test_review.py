import unittest
from unittest.mock import patch
from director import review
class ReviewTests(unittest.TestCase):
 def test_ru_status(self):
  self.assertEqual(review.status_ru("completed","failure"),"Ошибка")
  self.assertEqual(review.status_ru("in_progress",None),"Выполняется")
 def test_scope(self):
  self.assertEqual(review.file_scope(["server/platform/api.py"],"server/platform/**")[0],"within")
  self.assertEqual(review.file_scope(["server/platform/api.py","client/main.gd"],"server/platform/**")[0],"outside")
  self.assertEqual(review.file_scope(["client/main.gd"],"")[0],"unknown")
 def test_review_does_not_claim_merge_ready(self):
  with patch("director.review.observer.api") as mock:
   def get(repo,path,token=""):
    if path.startswith("/pulls/86/files"):return [{"filename":"server/platform/api.py"}]
    if path.startswith("/pulls/86"):return {"title":"Consent","html_url":"https://github.com/a/b/pull/86","head":{"sha":"abc","ref":"v2/consent-1"}}
    if path.startswith("/commits/"):return {"check_runs":[{"name":"test","status":"completed","conclusion":"failure"}]}
    if path.startswith("/actions/runs?"):return {"workflow_runs":[]}
    raise ValueError(path)
   mock.side_effect=get
   r=review.inspect_pr("a/b",86,allowed="server/platform/**")
   self.assertEqual(r["scope"],"within")
   self.assertIn("доработка",r["decision"])
   self.assertIn("Не сливать",r["draft"])
