"""Import observed open PRs as unverified task cards, without inventing scopes."""
import re
from director import tasklink

def ensure_schema(conn):
 if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='tasks'").fetchone():return
 tasklink.ensure_schema(conn)
 columns={x[1] for x in conn.execute("PRAGMA table_info(tasks)")}
 if "source" not in columns:conn.execute("ALTER TABLE tasks ADD COLUMN source TEXT NOT NULL DEFAULT 'manual'")
 conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS imported_pr_url_unique ON tasks(pr_url) WHERE source='github' AND pr_url<>''")

def import_snapshot(conn,repo,state,timestamp):
 ensure_schema(conn)
 if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='tasks'").fetchone():return 0
 inserted=0
 for pr in state.get("prs",[]):
  number=pr.get("number")
  branch=pr.get("branch","")
  if not isinstance(number,int) or not 0<number<10000000 or not isinstance(branch,str) or not branch:continue
  url="https://github.com/"+repo+"/pull/"+str(number)
  existing,match=tasklink.match_task(conn,repo,number,branch)
  if existing or match=="ambiguous":continue
  # Never replace manual tasks, scope, prompt, status, or reports.
  title=pr.get("title","PR #"+str(number))
  title=(title if isinstance(title,str) else "PR #"+str(number))[:200]
  prompt="Автоматически обнаружено в GitHub: PR #"+str(number)+". Исходный промпт и разрешённая зона файлов неизвестны. Проверьте описание PR и задание автора; не считать изменённые файлы разрешёнными."
  conn.execute("INSERT INTO tasks(title,body,branch,status,created_at,pr_url,allowed_files,source) VALUES(?,?,?,?,?,?,?,?)",(title,prompt,branch[:160],"in_review",timestamp,url,"","github"))
  inserted+=1
 return inserted
