#!/usr/bin/env python3
"""Local web front end for SJ Design Automation Hub."""
import json
import os
import platform
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROFILE = ROOT / ".firefox-profile"
LOG_DIR = ROOT / "logs"
SSO_URL = "https://wds.samsung.com/wds/sso/login/forwardLogin.do"
jobs = {}
lock = threading.Lock()


def command(action, data):
    profile = str(PROFILE)
    if action == "login":
        return [sys.executable, str(ROOT / "auth_login.py"), "--profile", profile]
    if action == "copy":
        return ["node", str(ROOT / "copy-aem-components.mjs"), "--source", data["source"], "--target", data["target"], "--yes", "--user-data-dir", profile]
    if action == "publish":
        args = [sys.executable, str(ROOT / "main.py"), "--workbook", data["workbook"], "--workers", str(data.get("workers") or 10)]
        if data.get("mode") == "validate": args.append("--validate-only")
        if data.get("mode") == "validate-all": args.append("--validate-all")
        return args
    if action == "qa":
        args = [sys.executable, str(ROOT / "aem_faq_qa.py"), "--workbook", data["workbook"], "--browser", "firefox", "--user-data-dir", profile]
        return args + (["--plan"] if data.get("mode") == "plan" else ["--all", "--review", "--apply"])
    raise ValueError("Unknown action")


def start(action, data):
    if action != "login" and not data.get("workbook") and action in {"publish", "qa"}:
        raise ValueError("Workbook path required")
    if action == "copy" and (not data.get("source") or not data.get("target")):
        raise ValueError("Source and target URLs required")
    with lock:
        if any(job["process"].poll() is None for job in jobs.values()):
            raise ValueError("Another job is running")
        LOG_DIR.mkdir(exist_ok=True)
        job_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        log = LOG_DIR / f"{job_id}-{action}.log"
        stream = log.open("w", encoding="utf-8")
        process = subprocess.Popen(command(action, data), stdin=subprocess.PIPE, stdout=stream, stderr=subprocess.STDOUT, text=True, bufsize=1, env={**os.environ, "AEM_PROFILE": str(PROFILE), "PYTHONIOENCODING": "utf-8"})
        jobs[job_id] = {"process": process, "log": log, "action": action}
    return job_id


def state(job_id):
    job = jobs.get(job_id)
    if not job: raise ValueError("Job not found")
    output = job["log"].read_text(encoding="utf-8", errors="replace") if job["log"].exists() else ""
    review = next((line for line in reversed(output.splitlines()) if line.startswith("REVIEW ITEM ")), "")
    locked = next((line for line in reversed(output.splitlines()) if line.startswith("WORKBOOK LOCKED:")), "")
    raw = "\n".join(line for line in output.splitlines() if not line.startswith("UI "))
    return {"id": job_id, "action": job["action"], "running": job["process"].poll() is None, "code": job["process"].poll(), "output": raw[-12000:], "review": review, "locked": locked, "dashboard": dashboard(output)}


def dashboard(output):
    view = {"kind": "", "workers": {}, "locales": {}, "parents": {}, "children": {}, "current": {}}
    for line in output.splitlines():
        if not line.startswith("UI "):
            continue
        try:
            event = json.loads(line[3:])
        except json.JSONDecodeError:
            continue
        view["kind"] = event.get("kind", view["kind"])
        kind, name = event.get("kind"), event.get("event")
        if name == "start":
            view["total"] = event.get("total") or event.get("parents") or 0
            view["mode"] = event.get("mode", "")
            view["children_total"] = event.get("children", 0)
            for site in event.get("locales", []): view["locales"][site] = {"status": "pending"}
            for site in event.get("child_sites", []): view["children"][site] = {"site": site, "status": "not copied"}
        elif kind == "publish" and name == "worker":
            view["workers"][str(event["slot"])] = {key: event[key] for key in ("site", "status") if key in event}
        elif kind == "publish" and name == "locale":
            view["locales"][event["site"]] = {"site": event["site"], "status": event["status"]}
        elif kind == "qa" and name == "parent":
            view["parents"][event["site"]] = {key: event[key] for key in ("sheet", "site", "link", "status", "findings", "index", "total") if key in event}
            view["current"] = view["parents"][event["site"]]
        elif kind == "qa" and name == "child":
            view["children"][event["site"]] = {key: event[key] for key in ("sheet", "site", "status", "error", "index", "total") if key in event}
    return view


def pick_workbook():
    if platform.system() == "Darwin":
        result = subprocess.run(
            ["osascript", "-e", 'POSIX path of (choose file with prompt "Choose workbook" of type {"org.openxmlformats.spreadsheetml.sheet"})'],
            capture_output=True, text=True,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    try:
        from tkinter import Tk, filedialog
        root = Tk(); root.withdraw(); root.attributes("-topmost", True)
        selected = filedialog.askopenfilename(title="Choose workbook", filetypes=[("Excel workbooks", "*.xlsx")])
        root.destroy()
        return selected
    except Exception:
        return ""


class App(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/": return self.reply(200, PAGE, "text/html")
        if self.path.startswith("/api/job/"):
            try: return self.json(200, state(self.path.rsplit("/", 1)[-1]))
            except ValueError as error: return self.json(404, {"error": str(error)})
        return self.reply(404, "Not found")

    def do_POST(self):
        try:
            data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or "{}")
            if self.path == "/api/pick-workbook": return self.json(200, {"path": pick_workbook()})
            if self.path == "/api/start": return self.json(201, {"id": start(data["action"], data)})
            job = jobs[self.path.rsplit("/", 2)[-2]]
            if self.path.endswith("/input"):
                job["process"].stdin.write(data.get("value", "") + "\n"); job["process"].stdin.flush()
                return self.json(200, {"ok": True})
            raise ValueError("Unknown endpoint")
        except (KeyError, ValueError, BrokenPipeError) as error: return self.json(400, {"error": str(error)})

    def reply(self, code, body, content_type="text/plain"):
        encoded = body.encode()
        self.send_response(code); self.send_header("Content-Type", f"{content_type}; charset=utf-8"); self.send_header("Content-Length", len(encoded)); self.end_headers(); self.wfile.write(encoded)

    def json(self, code, value): self.reply(code, json.dumps(value), "application/json")
    def log_message(self, *_): pass


PAGE = r'''<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><title>SJ Automation Hub</title>
<style>*{box-sizing:border-box}body{font:15px system-ui;margin:0;background:#f1f5f9;color:#0f172a}.app{max-width:1500px;margin:auto;padding:24px;display:grid;grid-template-columns:minmax(310px,390px) 1fr;gap:22px}.left{position:sticky;top:0;height:100vh;overflow:auto;padding-bottom:24px}.brand{margin:4px 0 18px}h1{font-size:24px;margin:0}h2{font-size:17px;margin:0 0 12px}small,p{color:#64748b}section,.panel{background:white;border:1px solid #e2e8f0;border-radius:12px;padding:16px;margin:12px 0;box-shadow:0 1px 2px #0f172a0a}input,button{font:inherit;padding:9px;border-radius:7px;border:1px solid #cbd5e1}input{width:100%;margin:5px 0}button{cursor:pointer;background:#16a34a;color:white;border:0;font-weight:700;margin:4px 3px 0 0}button.alt{background:#e0f2fe;color:#075985}.right{min-width:0}.top{display:flex;justify-content:space-between;align-items:center}.summary{font-weight:700}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:8px}.card{border:1px solid #e2e8f0;border-left:5px solid #94a3b8;border-radius:8px;padding:9px;background:#fff}.card b{display:block}.pending{border-left-color:#f59e0b}.live,.validated,.copied,.approved{border-left-color:#22c55e}.error,.not-live,.not-copied,.not-approved{border-left-color:#ef4444}.copying,.qa-done,.checking-live,.opening-jira,.starting,.retrying{border-left-color:#3b82f6}.findings{margin:6px 0 0;padding-left:16px;color:#b45309}.worker{background:#f8fafc}a{color:#2563eb;word-break:break-all}pre{white-space:pre-wrap;max-height:380px;overflow:auto;background:#0f172a;color:#dbeafe;padding:14px;border-radius:8px;margin:10px 0 0}@media(max-width:850px){.app{display:block}.left{position:static;height:auto}}</style>
<main class="app"><aside class="left"><div class="brand"><h1>SJ Automation Hub</h1><small>One Firefox SSO session.</small></div><section><h2>1. Sign in</h2><p>Firefox enters credentials and waits for MFA. Finish Support links manually.</p><button onclick="start('login')">Sign in</button><button class="alt" onclick="send('')">I'm done signing in</button></section><section><h2>Live publishing</h2><input id="publish-workbook" placeholder="Choose workbook" readonly><button class="alt" onclick="pick('publish-workbook')">Choose .xlsx</button><input id="workers" type="number" min="1" max="15" value="10"><button onclick="start('publish',{workbook:v('publish-workbook'),workers:v('workers'),mode:'publish'})">Publish</button><button class="alt" onclick="start('publish',{workbook:v('publish-workbook'),workers:v('workers'),mode:'validate'})">Validate pending</button><button class="alt" onclick="start('publish',{workbook:v('publish-workbook'),workers:v('workers'),mode:'validate-all'})">Validate all</button></section><section><h2>UK/CA Master</h2><input id="source" placeholder="Source AEM URL"><input id="target" placeholder="Target AEM URL"><button onclick="start('copy',{source:v('source'),target:v('target')})">Copy components</button></section><section><h2>Finalize authoring</h2><input id="qa-workbook" placeholder="Choose workbook" readonly><button class="alt" onclick="pick('qa-workbook')">Choose .xlsx</button><button class="alt" onclick="start('qa',{workbook:v('qa-workbook'),mode:'plan'})">Show plan</button><button onclick="start('qa',{workbook:v('qa-workbook'),mode:'review'})">Audit, review, copy</button></section></aside><section class="right"><div class="top"><h2 id="title">Run dashboard</h2><span id="state" class="summary">Idle</span></div><div id="dashboard"><small>Start an automation to see live progress.</small></div><div id="review"></div><h2>Raw log</h2><pre id="log"></pre></section></main>
<script>let id='';const v=x=>document.getElementById(x).value,esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),cls=s=>String(s||'pending').toLowerCase().replaceAll(' ','-');function card(x,extra=''){let f=x.findings?.length?'<ul class="findings">'+x.findings.map(y=>'<li>'+esc(y)+'</li>').join('')+'</ul>':'';return '<div class="card '+cls(x.status)+' '+extra+'"><b>'+esc(x.site||'Worker')+'</b><small>'+esc(x.status||'pending')+'</small>'+(x.link?'<br><a target="_blank" href="'+esc(x.link)+'">Open AEM editor</a>':'')+f+'</div>'}function draw(d,running){let el=document.getElementById('dashboard');if(!d.kind){el.innerHTML='<small>Waiting for automation progress.</small>';return}if(d.kind==='publish'){let locales=Object.values(d.locales),done=locales.filter(x=>/live$|error/.test(x.status)).length;if(d.mode.startsWith('validate'))locales=locales.map(x=>({...x,status:x.status==='live'?'validated':x.status}));el.innerHTML='<h2>Live publishing · '+done+'/'+(d.total||locales.length)+'</h2><h3>Workers</h3><div class="grid">'+Object.entries(d.workers).map(([n,x])=>card({site:'Worker '+n+(x.site?' · '+x.site:''),status:x.status},'worker')).join('')+'</div><h3>Countries</h3><div class="grid">'+locales.map(card).join('')+'</div>';return}let parents=Object.values(d.parents),children=Object.values(d.children),finished=parents.filter(x=>x.status!=='auditing').length;el.innerHTML='<h2>Finalize authoring · '+finished+'/'+(d.total||parents.length)+' audited</h2>'+(d.current.site?'<p>Current: <b>'+esc(d.current.site)+'</b> '+(d.current.link?'<a target="_blank" href="'+esc(d.current.link)+'">Open AEM editor</a>':'')+'</p>':'')+'<h3>QA status</h3><div class="grid">'+parents.map(card).join('')+'</div><h3>Child copies · '+children.filter(x=>x.status==='copied').length+'/'+(d.children_total||children.length)+'</h3><div class="grid">'+children.map(card).join('')+'</div>'}async function pick(field){let r=await fetch('/api/pick-workbook',{method:'POST',body:'{}'}),j=await r.json();if(j.path)document.getElementById(field).value=j.path}async function start(action,data={}){let r=await fetch('/api/start',{method:'POST',body:JSON.stringify({action,...data})}),j=await r.json();if(j.error)return alert(j.error);id=j.id;poll()}async function send(value){if(!id)return alert('Start sign in first.');await fetch('/api/job/'+id+'/input',{method:'POST',body:JSON.stringify({value})})}async function poll(){if(!id)return;let r=await fetch('/api/job/'+id),j=await r.json();document.getElementById('log').textContent=j.output||'';document.getElementById('state').textContent=j.running?'Running':'Finished'+(j.code?' · failed':'');document.getElementById('title').textContent=j.action==='qa'?'Finalize authoring':j.action==='publish'?'Live publishing':'Run dashboard';draw(j.dashboard,j.running);document.getElementById('review').innerHTML=j.locked?'<section><b>Workbook locked</b><p>'+esc(j.locked)+'</p><button onclick="send(\'\')">I closed it — retry</button></section>':j.review?'<section><b>Review needed</b><p>'+esc(j.review)+'</p><button onclick="send(\'y\')">Approve</button><button class="alt" onclick="send(\'n\')">Skip</button></section>':'';if(j.running)setTimeout(poll,800)}</script>'''


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 8765), App)
    url = "http://127.0.0.1:8765"
    print(f"SJ Automation Hub: {url}")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__": main()
