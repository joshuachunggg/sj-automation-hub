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
from browser_owner import request as browser_request

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
        if data.get("skip_countries"):
            args += ["--skip-country", data["skip_countries"]]
        if data.get("mode") == "validate": args.append("--validate-only")
        if data.get("mode") == "validate-all": args.append("--validate-all")
        return args
    if action == "qa":
        args = [sys.executable, str(ROOT / "aem_faq_qa.py"), "--workbook", data["workbook"], "--browser", "firefox", "--user-data-dir", profile]
        return args + (["--plan"] if data.get("mode") == "plan" else ["--retry-failed"] if data.get("mode") == "retry" else ["--all", "--review", "--apply"])
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
            for site in event.get("skipped", []): view["locales"][site] = {"site": site, "status": "skipped — not processed"}
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
            if self.path == "/api/open-editor": return self.json(200, {"ok": browser_request("open", url=data["url"])})
            if self.path == "/api/start": return self.json(201, {"id": start(data["action"], data)})
            job = jobs[self.path.rsplit("/", 2)[-2]]
            if self.path.endswith("/input"):
                if job["action"] == "login" and data.get("value") == "done":
                    browser_request("done")
                    return self.json(200, {"ok": True})
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
<style>*{box-sizing:border-box}body{font:15px system-ui;margin:0;min-height:100vh;background:radial-gradient(circle at 75% 0,#152845 0,#0b111b 42rem);color:#e6edf6}.app{max-width:1540px;margin:auto;padding:28px;display:grid;grid-template-columns:minmax(310px,390px) 1fr;gap:28px}.left{position:sticky;top:0;height:100vh;overflow:auto;padding-bottom:28px}.brand{margin:9px 2px 24px;padding-left:13px;border-left:2px solid #36c9e8}.brand small,.summary,.card small{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.03em}h1{font-size:23px;letter-spacing:-.04em;margin:0}h2{font-size:14px;text-transform:uppercase;letter-spacing:.1em;margin:0 0 13px;color:#f3f7fb}h3{font-size:13px;letter-spacing:.04em;margin:22px 0 9px;color:#9eb1c8}small,p{color:#8fa1b7}section,.panel{background:linear-gradient(145deg,#121d2b,#0e1723);border:1px solid #26384d;border-radius:7px;padding:17px;margin:12px 0;box-shadow:0 18px 40px #03070d33}input,button{font:inherit;padding:10px;border-radius:5px}input{width:100%;margin:5px 0;background:#09111b;color:#e6edf6;border:1px solid #2e435c}input:focus{outline:1px solid #36c9e8;border-color:#36c9e8}button{cursor:pointer;background:#36c9e8;color:#05121c;border:1px solid #36c9e8;font-weight:750;letter-spacing:.01em;margin:4px 3px 0 0}button:hover{background:#72dcf1;border-color:#72dcf1}button.alt{background:transparent;color:#a9dced;border-color:#345a70}.right{min-width:0}.top{display:flex;justify-content:space-between;align-items:center;padding:9px 2px 12px;border-bottom:1px solid #26384d}.summary{color:#36c9e8;font-size:12px;text-transform:uppercase}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(145px,1fr));gap:9px}.card{border:1px solid #26384d;border-left:3px solid #65778e;border-radius:5px;padding:10px;background:#101b28}.card b{display:block;font-size:14px}.card small{display:block;margin-top:5px;font-size:11px;text-transform:uppercase;color:#91a5bc}.pending{border-left-color:#e5ac42}.live,.validated,.copied,.approved{border-left-color:#43d69b}.error,.not-live,.not-copied,.not-approved{border-left-color:#f36d72}.copying,.qa-done,.checking-live,.opening-jira,.starting,.retrying{border-left-color:#36c9e8}.findings{margin:8px 0 0;padding:10px 0 0 18px;border-top:1px solid #26384d;color:#f1c46d}.worker{background:#132236}a{color:#55d7f1;word-break:break-all}pre{white-space:pre-wrap;max-height:380px;overflow:auto;background:#070d15;color:#b7cbe1;border:1px solid #26384d;padding:15px;border-radius:5px;margin:10px 0 0;font:12px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace}@media(max-width:850px){.app{display:block;padding:18px}.left{position:static;height:auto}}</style>
<main class="app"><aside class="left"><div class="brand"><h1>SJ Automation Hub</h1><small>One Firefox SSO session.</small></div><section><h2>1. Sign in</h2><p>Firefox waits for MFA and finishes when WMC home is ready.</p><button onclick="start('login')">Sign in</button><button class="alt" onclick="send('done')">I'm done logging in</button></section><section><h2>Live publishing</h2><input id="publish-workbook" placeholder="Choose workbook" readonly><button class="alt" onclick="pick('publish-workbook')">Choose .xlsx</button><input id="workers" type="number" min="1" max="15" value="10"><input id="skip-countries" placeholder="Country codes to skip, e.g. uk, ca"><button onclick="start('publish',{workbook:v('publish-workbook'),workers:v('workers'),skip_countries:v('skip-countries'),mode:'publish'})">Publish</button><button class="alt" onclick="start('publish',{workbook:v('publish-workbook'),workers:v('workers'),skip_countries:v('skip-countries'),mode:'validate'})">Validate pending</button><button class="alt" onclick="start('publish',{workbook:v('publish-workbook'),workers:v('workers'),skip_countries:v('skip-countries'),mode:'validate-all'})">Validate all</button></section><section><h2>UK/CA Master</h2><input id="source" placeholder="Source AEM URL"><input id="target" placeholder="Target AEM URL"><button onclick="start('copy',{source:v('source'),target:v('target')})">Copy components</button></section><section><h2>Finalize authoring</h2><input id="qa-workbook" placeholder="Choose workbook" readonly><button class="alt" onclick="pick('qa-workbook')">Choose .xlsx</button><button class="alt" onclick="start('qa',{workbook:v('qa-workbook'),mode:'plan'})">Show plan</button><button onclick="start('qa',{workbook:v('qa-workbook'),mode:'review'})">Audit, review, copy</button><button class="alt" onclick="start('qa',{workbook:v('qa-workbook'),mode:'retry'})">Retry failed child copies</button></section></aside><section class="right"><div class="top"><h2 id="title">Run dashboard</h2><span id="state" class="summary">Idle</span></div><div id="dashboard"><small>Start an automation to see live progress.</small></div><div id="review"></div><h2>Raw log</h2><pre id="log"></pre></section></main>
<script>let id='',reviewing=false;const v=x=>document.getElementById(x).value,esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),cls=s=>String(s||'pending').toLowerCase().replaceAll(' ','-');async function openEditor(url){await fetch('/api/open-editor',{method:'POST',body:JSON.stringify({url})})}function card(x,extra=''){return '<div class="card '+cls(x.status)+' '+extra+'"><b>'+esc(x.site||'Worker')+'</b><small>'+esc(x.status||'pending')+'</small>'+(x.error?'<p>'+esc(x.error)+'</p>':'')+(x.link?'<br><button class="alt" onclick="openEditor(\''+esc(x.link)+'\')">Open AEM editor</button>':'')+'</div>'}function draw(d,review){let el=document.getElementById('dashboard');if(!d.kind){el.innerHTML='<small>Waiting for automation progress.</small>';return}if(d.kind==='publish'){let locales=Object.values(d.locales),done=locales.filter(x=>/live$|error/.test(x.status)).length,skipped=locales.filter(x=>x.status.startsWith('skipped')).length;if(d.mode.startsWith('validate'))locales=locales.map(x=>({...x,status:x.status==='live'?'validated':x.status}));el.innerHTML='<h2>Live publishing · '+done+'/'+(d.total||locales.length)+' processed'+(skipped?' · '+skipped+' skipped':'')+'</h2><h3>Workers</h3><div class="grid">'+Object.entries(d.workers).map(([n,x])=>card({site:'Worker '+n+(x.site?' · '+x.site:''),status:x.status},'worker')).join('')+'</div><h3>Countries</h3><div class="grid">'+locales.map(card).join('')+'</div>';return}let parents=Object.values(d.parents),children=Object.values(d.children),finished=parents.filter(x=>x.status!=='auditing').length,current=d.current||{},decision=review?'<section><b>QA decision needed</b><p>'+esc(review)+'</p><button onclick="send(\'y\')">Approve (Y)</button><button class="alt" onclick="send(\'n\')">Skip (N)</button></section>':'';el.innerHTML='<h3>'+finished+'/'+(d.total||parents.length)+' pages audited</h3>'+(current.site?'<section><h3>Current QA · '+esc(current.site)+'</h3><button onclick="openEditor(\''+esc(current.link)+'\')">Open AEM editor</button>'+(current.findings?.length?'<h3>Heuristic differentials</h3><ul class="findings">'+current.findings.map(x=>'<li>'+esc(x)+'</li>').join('')+'</ul>':'<p>No heuristic differentials found.</p>')+decision+'</section>':'')+'<h3>QA status</h3><div class="grid">'+parents.map(card).join('')+'</div><h3>Child copies · '+children.filter(x=>x.status==='copied').length+'/'+(d.children_total||children.length)+'</h3><div class="grid">'+children.map(card).join('')+'</div>'}async function pick(field){let r=await fetch('/api/pick-workbook',{method:'POST',body:'{}'}),j=await r.json();if(j.path)document.getElementById(field).value=j.path}async function start(action,data={}){let r=await fetch('/api/start',{method:'POST',body:JSON.stringify({action,...data})}),j=await r.json();if(j.error)return alert(j.error);id=j.id;poll()}async function send(value){if(!id)return alert('Start sign in first.');await fetch('/api/job/'+id+'/input',{method:'POST',body:JSON.stringify({value})})}document.addEventListener('keydown',e=>{if(reviewing&&!e.metaKey&&!e.ctrlKey&&['y','n'].includes(e.key.toLowerCase()))send(e.key.toLowerCase())});async function poll(){if(!id)return;let r=await fetch('/api/job/'+id),j=await r.json();document.getElementById('log').textContent=j.output||'';document.getElementById('state').textContent=j.running?'Running':'Finished'+(j.code?' · failed':'');document.getElementById('title').textContent=j.action==='qa'?'Finalize authoring':j.action==='publish'?'Live publishing':'Run dashboard';reviewing=!!j.review;draw(j.dashboard,j.review);document.getElementById('review').innerHTML=j.locked?'<section><b>Workbook locked</b><p>'+esc(j.locked)+'</p><button onclick="send(\'\')">I closed it — retry</button></section>':'';if(j.running)setTimeout(poll,800)}</script>'''


def main():
    subprocess.Popen(["node", str(ROOT / "browser_owner.mjs")], cwd=ROOT, env={**os.environ, "AEM_PROFILE": str(PROFILE)}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
