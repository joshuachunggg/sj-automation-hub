# SJ Design Automation Hub

Local web interface for Samsung AEM and Jira workflows. It runs only on `127.0.0.1` and opens Firefox for one shared Samsung SSO session.

## Start

Windows:

```powershell
.\.venv\Scripts\python.exe hub.py
```

macOS:

```bash
.venv/bin/python hub.py
```

Open `http://127.0.0.1:8765` if browser does not open. Click **Open sign in**, complete MFA at Samsung SSO, then click **I finished signing in**. The local Firefox profile is saved in `.firefox-profile`; all jobs reuse it until Samsung expires session.

## Setup

```bash
python -m pip install -r requirements.txt
python -m playwright install firefox
npm install
```

Do not run two hub jobs together. Browser profile permits one Firefox owner at a time.
Each job uses one Firefox window; automation pages open as tabs in that window.
