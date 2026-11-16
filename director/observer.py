"""Read-only GitHub observer, resilient polling and deterministic review summaries."""
import datetime as dt
import json
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from director import importer

POLL_INTERVAL=180
MAX_EVENTS=300
def now(): return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
def api(repo,path,token=""):
 if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+",repo):
  raise ValueError("Invalid repository")
 if (path and not path.startswith("/")) or "://" in path:raise ValueError("Invalid API path")
 headers={"Accept":"application/vnd.github+json","User-Agent":"lunex-director/0.2","X-GitHub-Api-Version":"2022-11-28"}
 if token:headers["Authorization"]="Bearer "+token
 request=urllib.request.Request("https://api.github.com/repos/"+repo+path,headers=headers)
 with urllib.request.urlopen(request,timeout=12) as response:return json.load(response)
def init_db(conn):
 conn.execute("CREATE TABLE IF NOT EXISTS github_snapshots(id INTEGER PRIMARY KEY CHECK(id=1),observed_at TEXT NOT NULL, payload TEXT NOT NULL)")
 conn.execute("CREATE TABLE IF NOT EXISTS github_events(id INTEGER PRIMARY KEY,observed_at TEXT NOT NULL,kind TEXT NOT NULL,reference TEXT NOT NULL,summary TEXT NOT NULL,UNIQUE(kind,reference,summary))")
 conn.execute("CREATE TABLE IF NOT EXISTS github_monitor(status TEXT NOT NULL,last_attempt TEXT,last_success TEXT,error TEXT)")
 if not conn.execute("SELECT 1 FROM github_monitor").fetchone():
  conn.execute("INSERT INTO github_monitor(status) VALUES('waiting')")
def review(pr,runs):
 sha=pr.get("head",{}).get("sha","")
 related=[r for r in runs if r.get("head_sha")==sha]
 if pr.get("draft"):return "Черновик: проверка не завершена"
 if not related:return "CI для SHA не подтверждён: требуется ручная проверка"
 if any(r.get("status")!="completed" for r in related):return "CI выполняется: слияние запрещено"
 if any(r.get("conclusion")!="success" for r in related):return "CI неуспешен или пропущен: нужна доработка"
 return "CI в выборке успешен; требуется проверка файлов, политик и актуальности SHA"
def snapshot(repo,token=""):
 info=api(repo,"",token)
 prs=api(repo,"/pulls?state=open&per_page=60",token)
 runs=api(repo,"/actions/runs?per_page=70",token).get("workflow_runs",[])
 return {"repo":repo,"default_branch":info.get("default_branch",""),"prs":[{"number":p["number"],"title":p.get("title",""),"url":p.get("html_url",""),"branch":p.get("head",{}).get("ref",""),"sha":p.get("head",{}).get("sha",""),"draft":p.get("draft",False),"review":review(p,runs)} for p in prs],"runs":[{"id":r.get("id"),"name":r.get("name",""),"status":r.get("status",""),"conclusion":r.get("conclusion"),"sha":r.get("head_sha",""),"branch":r.get("head_branch",""),"url":r.get("html_url","")} for r in runs[:25]],"total_open_pr":len(prs),"total_runs_sampled":len(runs)}
def sync(conn,repo,token=""):
 init_db(conn)
 timestamp=now()
 conn.execute("UPDATE github_monitor SET status='checking',last_attempt=?",(timestamp,))
 conn.commit()
 try:
  state=snapshot(repo,token)
  old=conn.execute("SELECT payload FROM github_snapshots WHERE id=1").fetchone()
  old=json.loads(old[0]) if old else {"prs":[],"runs":[]}
  known_pr={p["number"]:p for p in old["prs"]}
  known_runs={r["id"]:r for r in old["runs"]}
  events=[]
  for p in state["prs"]:
   prev=known_pr.get(p["number"])
   if prev is None:events.append(("pr_detected",str(p["number"]),p["title"][:200]))
   elif prev["sha"]!=p["sha"]:events.append(("pr_commit",str(p["number"]),p["sha"]))
   if p["review"]!= (prev or {}).get("review"):events.append(("review",str(p["number"]),p["review"]))
  for r in state["runs"]:
   prev=known_runs.get(r["id"])
   if prev is None or (prev["status"],prev["conclusion"])!=(r["status"],r["conclusion"]):
    events.append(("ci",str(r["id"]),str(r["status"])+"/"+str(r["conclusion"])))
  for kind,ref,summary in events:
   conn.execute("INSERT OR IGNORE INTO github_events(observed_at,kind,reference,summary) VALUES(?,?,?,?)",(timestamp,kind,ref,summary))
  conn.execute("INSERT INTO github_snapshots(id,observed_at,payload) VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET observed_at=excluded.observed_at,payload=excluded.payload",(timestamp,json.dumps(state,ensure_ascii=False)))
  importer.import_snapshot(conn,repo,state,timestamp)
  conn.execute("UPDATE github_monitor SET status='ok',last_success=?,error=NULL",(timestamp,))
  conn.execute("DELETE FROM github_events WHERE id NOT IN (SELECT id FROM github_events ORDER BY id DESC LIMIT ?)",(MAX_EVENTS,))
  conn.commit()
  return state
 except (urllib.error.URLError,ValueError,TimeoutError,OSError,KeyError,TypeError) as ex:
  conn.execute("UPDATE github_monitor SET status='error',error=?",(type(ex).__name__,))
  conn.commit()
  return None
def read(conn):
 init_db(conn)
 row=conn.execute("SELECT observed_at,payload FROM github_snapshots WHERE id=1").fetchone()
 mon=conn.execute("SELECT status,last_attempt,last_success,error FROM github_monitor").fetchone()
 events=conn.execute("SELECT observed_at,kind,reference,summary FROM github_events ORDER BY id DESC LIMIT 25").fetchall()
 return ({"observed_at":row[0],**json.loads(row[1])} if row else None,dict(mon),[dict(x) for x in events])
def loop(db_factory,repo,token="",stop=None):
 while stop is None or not stop.is_set():
  with db_factory() as conn:sync(conn,repo,token)
  if stop is not None:
   if stop.wait(POLL_INTERVAL):break
  else:time.sleep(POLL_INTERVAL)
def start(db_factory,repo,token=""):
 t=threading.Thread(target=loop,args=(db_factory,repo,token),name="github-observer",daemon=True)
 t.start()
 return t
