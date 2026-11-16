"""Read-only PR diagnostics and safe executor feedback drafts."""
import re
from director import observer

def status_ru(status,conclusion):
 if status!="completed":return "Выполняется"
 return {"success":"Успешно","failure":"Ошибка","cancelled":"Отменено","skipped":"Пропущено","timed_out":"Превышено время","action_required":"Требует действий"}.get(conclusion,"Неизвестно")
def kind(status,conclusion):
 if status!="completed":return "pending"
 if conclusion=="success":return "success"
 return "failure"
def file_scope(paths,allowed):
 if not allowed:return ("unknown",[])
 patterns=[x.strip().rstrip("/") for x in re.split(r"[,;\n]",allowed) if x.strip()]
 if not patterns:return ("unknown",[])
 def permitted(path,pattern):
  if pattern.endswith("/**"):return path.startswith(pattern[:-3]+"/")
  if "*" in pattern:
   import fnmatch
   return fnmatch.fnmatchcase(path,pattern)
  return path==pattern or path.startswith(pattern+"/")
 unexpected=[p for p in paths if not any(permitted(p,a) for a in patterns)]
 return ("outside" if unexpected else "within",unexpected)
def inspect_pr(repo,number,token="",allowed=""):
 if not isinstance(number,int) or number<1:raise ValueError("Invalid PR number")
 pr=observer.api(repo,"/pulls/"+str(number),token)
 files=observer.api(repo,"/pulls/"+str(number)+"/files?per_page=100",token)
 checks=observer.api(repo,"/commits/"+pr["head"]["sha"]+"/check-runs?per_page=100",token).get("check_runs",[])
 runs=observer.api(repo,"/actions/runs?head_sha="+pr["head"]["sha"]+"&per_page=50",token).get("workflow_runs",[])
 failed_steps=[]
 for r in runs[:8]:
  if r.get("status")=="completed" and r.get("conclusion") not in ("success","neutral"):
   try:
    jobs=observer.api(repo,"/actions/runs/"+str(r["id"])+"/jobs?per_page=50",token).get("jobs",[])
    for job in jobs:
     for step in job.get("steps",[]):
      if step.get("conclusion") in ("failure","timed_out","action_required"):
       failed_steps.append({"workflow":r.get("name",""),"job":job.get("name",""),"step":step.get("name",""),"url":job.get("html_url","")})
   except Exception:pass
 paths=[f.get("filename","") for f in files]
 scope,unexpected=file_scope(paths,allowed)
 failed=[{"name":c.get("name",""),"url":c.get("html_url",""),"conclusion":c.get("conclusion")} for c in checks if c.get("status")=="completed" and c.get("conclusion") not in ("success","neutral")]
 pending=[c.get("name","") for c in checks if c.get("status")!="completed"]
 run_fail=[r for r in runs if r.get("status")=="completed" and r.get("conclusion") not in ("success","neutral")]
 if failed or run_fail:decision="Требуется доработка CI"
 elif pending or any(r.get("status")!="completed" for r in runs):decision="Ожидание CI"
 elif not checks and not runs:decision="Нет подтверждённых проверок для SHA"
 else:decision="CI успешен в полученной выборке; требуется ручная проверка"
 if scope=="outside":decision="Обнаружены файлы вне разрешённой зоны; требуется проверка"
 elif scope=="unknown":decision+="; зона файлов не задана"
 notes=["PR #"+str(number)+": "+pr.get("title",""),"Ветка: "+pr["head"].get("ref",""),"SHA: "+pr["head"]["sha"][:12],"Заключение: "+decision]
 if failed:notes.append("Неуспешные проверки: "+", ".join(x["name"] for x in failed[:12]))
 if pending:notes.append("Выполняются: "+", ".join(pending[:12]))
 if unexpected:notes.append("Вне разрешённой зоны: "+", ".join(unexpected[:20]))
 if failed_steps:notes.append("Проблемные шаги: "+", ".join(x["job"]+" / "+x["step"] for x in failed_steps[:12]))
 notes.append("Исправить выявленные ошибки, повторно запустить CI и предоставить отчёт. Не сливать PR автоматически.")
 return {"number":number,"title":pr.get("title",""),"url":pr.get("html_url",""),"branch":pr["head"].get("ref",""),"sha":pr["head"]["sha"],"files":paths,"files_truncated":len(files)>=100,"checks":checks,"runs":runs,"failed":failed,"failed_steps":failed_steps,"pending":pending,"scope":scope,"unexpected":unexpected,"decision":decision,"draft":"\n".join(notes)}
