"""Task-to-PR matching without guessing: exact PR URL or unique branch only."""
import re
from urllib.parse import urlsplit
from director import review

def pr_number(url,repo):
 match=re.fullmatch(r"https://github\.com/"+re.escape(repo)+r"/pull/([1-9][0-9]*)(?:/)?",url.strip())
 return int(match.group(1)) if match else None

def match_task(conn,repo,number,branch):
 rows=conn.execute("SELECT id,title,branch,pr_url,allowed_files FROM tasks").fetchall()
 explicit=[dict(x) for x in rows if pr_number(x["pr_url"],repo)==number]
 if len(explicit)==1:return explicit[0],"explicit"
 if len(explicit)>1:return None,"ambiguous"
 branch_matches=[dict(x) for x in rows if x["branch"] and x["branch"]==branch]
 if len(branch_matches)==1:return branch_matches[0],"branch"
 if len(branch_matches)>1:return None,"ambiguous"
 return None,"missing"

def ensure_schema(conn):
 columns={x[1] for x in conn.execute("PRAGMA table_info(tasks)")}
 if "allowed_files" not in columns:conn.execute("ALTER TABLE tasks ADD COLUMN allowed_files TEXT NOT NULL DEFAULT ''")

def scope_status(paths,task):
 if not task:return "unknown",[]
 return review.file_scope(paths,task.get("allowed_files",""))
