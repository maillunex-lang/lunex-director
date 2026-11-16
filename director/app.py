"""LUNEX DIRECTOR MVP: isolated local-only task dashboard and GitHub read-only viewer."""
import datetime as dt
import html
import hmac
import http.cookies
import http.server
import json
import os
import re
import secrets
import sqlite3
import threading
import time
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from director import observer

REPO=os.environ.get("DIRECTOR_REPOSITORY","maillunex-lang/LunexEconom")
DB_PATH=Path(os.environ.get("DIRECTOR_DB","./director.sqlite3"))
BIND=os.environ.get("DIRECTOR_BIND","127.0.0.1")
PORT=int(os.environ.get("DIRECTOR_PORT","18798"))
ADMIN_PASSWORD=os.environ.get("DIRECTOR_ADMIN_PASSWORD","")
GITHUB_TOKEN=os.environ.get("DIRECTOR_GITHUB_TOKEN","")
SESSIONS={}
LOCK=threading.Lock()
STYLE=""":root{color-scheme:dark;font-family:system-ui,Arial;background:#0c1c17;color:#eaf5ef}*{box-sizing:border-box}body{margin:0}main{max-width:1024px;margin:auto;padding:20px}h1{font-size:1.4rem}a{color:#9de8ba}nav{display:flex;flex-wrap:wrap;gap:10px;margin:18px 0}nav a,button{display:inline-block;background:#256444;color:#fff;border:0;border-radius:9px;padding:12px;text-decoration:none;font:inherit;cursor:pointer}.card{background:#183127;border:1px solid #3c574a;border-radius:13px;padding:16px;margin:12px 0}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px}.grid .card{margin:0}input,textarea,select{width:100%;background:#10261d;color:#fff;border:1px solid #527761;border-radius:8px;padding:12px;font:inherit;margin:8px 0 14px}textarea{min-height:160px}small{color:#adbbb0}.warn{color:#ffcf91}li{margin:10px 0}button:focus-visible,input:focus-visible{outline:2px solid #e2df75}"""
def e(v): return html.escape(str(v if v is not None else ""),quote=True)
def utc():return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
def get_conn():
 DB_PATH.parent.mkdir(parents=True,exist_ok=True)
 c=sqlite3.connect(DB_PATH,timeout=10)
 c.row_factory=sqlite3.Row
 return c
def init_db():
 with get_conn() as c:
  c.execute("PRAGMA journal_mode=WAL")
  c.execute("CREATE TABLE IF NOT EXISTS tasks(id INTEGER PRIMARY KEY,title TEXT NOT NULL,body TEXT NOT NULL,branch TEXT NOT NULL DEFAULT '',status TEXT NOT NULL DEFAULT 'open',created_at TEXT NOT NULL,pr_url TEXT NOT NULL DEFAULT '',report TEXT NOT NULL DEFAULT '')")
  c.execute("CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,ts TEXT,action TEXT,task_id INTEGER,detail TEXT)")
  observer.init_db(c)
def audit(c,action,task_id=None,detail=""):
 c.execute("INSERT INTO audit(ts,action,task_id,detail) VALUES(?,?,?,?)",(utc(),action,task_id,detail[:250]))
def fetch_repo(path):
 if not re.fullmatch(r"[\w.-]+/[\w.-]+",REPO):raise RuntimeError("Repository configuration invalid")
 req=urllib.request.Request("https://api.github.com/repos/"+REPO+path,headers={"Accept":"application/vnd.github+json","User-Agent":"lunex-director/0.1",**({"Authorization":"Bearer "+GITHUB_TOKEN} if GITHUB_TOKEN else {})})
 try:
  with urllib.request.urlopen(req,timeout=8) as res:return json.load(res)
 except Exception: raise RuntimeError("GitHub data unavailable (possibly private repo or rate limit)") from None
def layout(title,body,auth=True):
 nav='<nav><a href="/">Обзор</a><a href="/tasks">Задания</a><a href="/github">GitHub CI / PR</a><a href="/audit">Журнал</a><form action="/logout" method="post"><input type="hidden" name="csrf" value="CSRF_PLACEHOLDER"><button>Выход</button></form></nav>' if auth else ""
 return ('<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><title>'+e(title)+' | LUNEX DIRECTOR</title><style>'+STYLE+'</style></head><body><main><h1>⬡ LUNEX DIRECTOR</h1><small>Умный директор · безопасный прототип · GitHub только чтение</small>'+nav+body+'<p><small>Модуль AI и слияние PR пока не включены.</small></p></main></body></html>').encode()
def task_card(t):
 return '<section class="card"><h3>#'+e(t["id"])+' '+e(t["title"])+'</h3><small>'+e(t["branch"])+' · '+e(t["status"])+'</small><p><a href="/tasks/'+e(t["id"])+'">Открыть промпт →</a></p></section>'
def render_dashboard():
 with get_conn() as c:
  counts=dict((r["status"],r["n"]) for r in c.execute("SELECT status,count(*) n FROM tasks GROUP BY status"))
  tasks=c.execute("SELECT * FROM tasks ORDER BY id DESC LIMIT 8").fetchall()
 cells=''.join('<div class="card"><h2>'+str(counts.get(s,0))+'</h2><small>'+name+'</small></div>' for s,name in [("open","В очереди"),("in_review","На проверке"),("done","Завершено")])
 return layout("Обзор",'<div class="grid">'+cells+'</div><section class="card"><h2>Проект: '+e(REPO)+'</h2><p>Состояние PR и CI проверяется по запросу в разделе GitHub.</p></section><h2>Последние задания</h2>'+''.join(map(task_card,tasks)))
def render_audit():
 with get_conn() as c: rows=c.execute("SELECT * FROM audit ORDER BY id DESC LIMIT 60").fetchall()
 return layout("Журнал",'<section class="card"><h2>Журнал действий</h2><ul>'+''.join('<li>'+e(r["ts"])+' · '+e(r["action"])+' · задача '+e(r["task_id"])+'</li>' for r in rows)+'</ul></section>')
def render_tasks():
 with get_conn() as c: rows=c.execute("SELECT * FROM tasks ORDER BY id DESC LIMIT 100").fetchall()
 return layout("Задачи",'<section class="card"><h2>Новое задание</h2><form action="/tasks" method="post"><label>Название<input name="title" maxlength="200" required></label><label>Ветка<input name="branch" maxlength="160"></label><label>Промпт<textarea name="body" maxlength="8000" required></textarea></label><input name="csrf" type="hidden" value="CSRF_PLACEHOLDER"><button>Создать задачу</button></form></section><h2>Очередь</h2>'+''.join(map(task_card,rows)))
def render_task(t):
 sel=''.join('<option value="'+k+'"'+(' selected' if t["status"]==k else '')+'>'+v+'</option>' for k,v in [("open","Ожидает"),("in_review","На проверке"),("done","Готово (ручная отметка)"),("blocked","Заблокировано")])
 return layout("Задача",'<a href="/tasks">← Все задачи</a><section class="card"><h2>#'+e(t["id"])+' '+e(t["title"])+'</h2><label>Промпт<textarea id="prompt" readonly>'+e(t["body"])+'</textarea></label><button type="button" onclick="navigator.clipboard.writeText(document.getElementById(\'prompt\').value).then(()=>this.textContent=\'Скопировано\')">Копировать промпт</button></section><section class="card"><h2>Отчёт исполнителя</h2><form action="/tasks/'+e(t["id"])+'/report" method="post"><label>Ссылка на PR<input name="pr_url" maxlength="400" value="'+e(t["pr_url"])+'"></label><label>Отчёт<textarea name="report" maxlength="8000">'+e(t["report"])+'</textarea></label><label>Статус<select name="status">'+sel+'</select></label><input type="hidden" name="csrf" value="CSRF_PLACEHOLDER"><button>Сохранить</button></form><p><small>Статус не подтверждает успешный CI и не запускает merge.</small></p></section>')
def render_github():
 with get_conn() as c: state,monitor,events=observer.read(c)
 if not state:
  return layout("GitHub",'<section class="card"><h2>Мониторинг запускается</h2><p>Система получает первые данные GitHub. Обновите страницу через несколько секунд.</p><p>Состояние: '+e(monitor["status"])+'</p></section>')
 status='<section class="card"><h2>Автоматический наблюдатель</h2><p>Последняя проверка: '+e(monitor["last_attempt"])+' · последняя успешная: '+e(monitor["last_success"])+'</p><p>Состояние: '+e(monitor["status"])+'</p><small>Обновление каждые 3 минуты, без права изменять GitHub. Проверки носят предварительный характер.</small></section>'
 if monitor["status"]!="ok":status+='<p class="warn">GitHub временно недоступен. Показаны последние сохранённые данные.</p>'
 def link(url,label):
  return '<a target="_blank" rel="noopener noreferrer" href="'+e(url)+'">'+e(label)+'</a>' if url.startswith("https://github.com/") else e(label)
 prs=''.join('<section class="card"><h3>'+link(p["url"],'#'+str(p["number"])+' '+p["title"])+'</h3><p>Ветка: '+e(p["branch"])+'</p><p>Проверка: '+e(p["review"])+'</p></section>' for p in state["prs"])
 runs=''.join('<li>'+link(r["url"],r["name"])+' · '+e(r["branch"])+' · '+e(r["status"])+' / '+e(r["conclusion"])+'</li>' for r in state["runs"][:12])
 events_html=''.join('<li>'+e(ev["observed_at"])+' · '+e(ev["kind"])+' · '+e(ev["reference"])+' · '+e(ev["summary"])+'</li>' for ev in events)
 return layout("GitHub",status+'<div class="grid"><section class="card">PR открыто: '+str(state["total_open_pr"])+'</section><section class="card">Основная ветка: '+e(state["default_branch"])+'</section></div><h2>Открытые PR</h2>'+(prs or '<p>Открытых PR нет.</p>')+'<h2>Последние CI</h2><ul>'+runs+'</ul><h2>Обнаруженные изменения</h2><ul>'+events_html+'</ul>')
def session_id(headers):
 cookies=http.cookies.SimpleCookie()
 try:cookies.load(headers.get("Cookie",""))
 except Exception:return ""
 item=cookies.get("director_session")
 return item.value if item else ""
class Handler(http.server.BaseHTTPRequestHandler):
 server_version="LunexDirector/0.1"
 def log_message(self,*args):pass
 def send(self,code,body,ctype="text/html; charset=utf-8"):
  if ctype.startswith("text/html"):
   body=body.replace(b'href="/',b'href="/director/').replace(b'action="/',b'action="/director/')
  self.send_response(code)
  for k,v in [("Content-Type",ctype),("Content-Length",str(len(body))),("Cache-Control","no-store"),("X-Content-Type-Options","nosniff"),("X-Frame-Options","DENY"),("Referrer-Policy","no-referrer"),("Content-Security-Policy","default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'")]:self.send_header(k,v)
  self.end_headers();self.wfile.write(body)
 def redirect(self,url,cookie=None):
  self.send_response(303);self.send_header("Location","/director"+url);self.send_header("Cache-Control","no-store")
  if cookie:self.send_header("Set-Cookie",cookie)
  self.end_headers()
 def get_form(self):
  n=int(self.headers.get("Content-Length","0"))
  if not 0<n<=16384:raise ValueError()
  return {k:v[-1] for k,v in parse_qs(self.rfile.read(n).decode(),keep_blank_values=True).items()}
 def auth(self):
  self.session=session_id(self.headers)
  with LOCK:return bool(self.session and SESSIONS.get(self.session,0)>time.time())
 def csrf(self,form):
  origin=self.headers.get("Origin")
  if origin:
   u=urlsplit(origin)
   if u.netloc!=self.headers.get("Host") or u.scheme not in ("http","https"):return False
  return hmac.compare_digest(form.get("csrf",""),self.session)
 def do_GET(self):
  path=urlsplit(self.path).path
  if path=="/health":return self.send(200,b'{"ok":true,"mode":"readonly"}',"application/json")
  if path=="/login":return self.send(200,layout("Вход",'<section class="card"><h2>Вход</h2><form action="/login" method="post"><label>Пароль<input type="password" name="password" required></label><button>Войти</button></form></section>',False))
  if not self.auth():return self.redirect("/login")
  if path=="/":content=render_dashboard()
  elif path=="/tasks":content=render_tasks()
  elif path=="/github":content=render_github()
  elif path=="/audit":content=render_audit()
  elif re.fullmatch(r"/tasks/[0-9]+",path):
   with get_conn() as c: t=c.execute("SELECT * FROM tasks WHERE id=?",(int(path.split("/")[-1]),)).fetchone()
   if not t:return self.send(404,b"Not found","text/plain")
   content=render_task(t)
  else:return self.send(404,b"Not found","text/plain")
  return self.send(200,content.replace(b"CSRF_PLACEHOLDER",e(self.session).encode()))
 def do_POST(self):
  path=urlsplit(self.path).path
  try: form=self.get_form()
  except Exception:return self.send(400,b"Invalid request","text/plain")
  if path=="/login":
   if ADMIN_PASSWORD and hmac.compare_digest(form.get("password",""),ADMIN_PASSWORD):
    token=secrets.token_urlsafe(32)
    with LOCK:SESSIONS[token]=time.time()+12*3600
    return self.redirect("/",f"director_session={token}; HttpOnly; Secure; SameSite=Strict; Path=/director/; Max-Age=43200")
   time.sleep(0.3)
   return self.send(403,layout("Ошибка","<p>Неверный пароль</p>",False))
  if not self.auth():return self.send(401,b"Unauthorized","text/plain")
  if not self.csrf(form):return self.send(403,b"CSRF rejected","text/plain")
  if path=="/logout":
   with LOCK:SESSIONS.pop(self.session,None)
   return self.redirect("/login","director_session=; HttpOnly; Secure; SameSite=Strict; Path=/director/; Max-Age=0")
  if path=="/tasks":
   title=form.get("title","").strip()[:200];body=form.get("body","").strip()[:8000]
   if not title or not body:return self.send(400,b"Missing title or body","text/plain")
   with get_conn() as c:
    cur=c.execute("INSERT INTO tasks(title,body,branch,created_at) VALUES(?,?,?,?)",(title,body,form.get("branch","")[:160],utc()))
    audit(c,"task_created",cur.lastrowid)
   return self.redirect("/tasks")
  m=re.fullmatch(r"/tasks/([0-9]+)/report",path)
  if m:
   status=form.get("status","open")
   if status not in ("open","in_review","done","blocked"):return self.send(400,b"Bad status","text/plain")
   ident=int(m.group(1))
   with get_conn() as c:
    cur=c.execute("UPDATE tasks SET pr_url=?,report=?,status=? WHERE id=?",(form.get("pr_url","")[:400],form.get("report","")[:8000],status,ident))
    if not cur.rowcount:return self.send(404,b"Not found","text/plain")
    audit(c,"task_report_saved",ident,status)
   return self.redirect("/tasks/"+str(ident))
  return self.send(404,b"Not found","text/plain")
def main():
 if len(ADMIN_PASSWORD)<16:raise SystemExit("DIRECTOR_ADMIN_PASSWORD must be at least 16 chars")
 if BIND!="127.0.0.1":raise SystemExit("Public binding disabled")
 init_db()
 observer.start(get_conn,REPO,GITHUB_TOKEN)
 server=http.server.ThreadingHTTPServer((BIND,PORT),Handler)
 print("LUNEX DIRECTOR read-only MVP",BIND,PORT,flush=True)
 server.serve_forever()
if __name__=="__main__":main()
