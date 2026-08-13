# SJ Design Automation Hub

Run all SJ Design Studio automations from one terminal menu:

- **Live publishing** — publishes FAQ translations through Jira, then verifies live URLs.
- **UK/CA Master** — copies missing AEM author-page components.
- **Finalize Authoring** — audits parent FAQ pages, collects approval, then copies approved content to child locales.

The hub defaults to Firefox on Windows and Chromium on macOS. Set `AEM_BROWSER=firefox` or `AEM_BROWSER=chromium` to override. Jira publishing always asks which browser to use.

## Setup

Install Python 3.11+, Node.js LTS, and Git. Browser install comes from Playwright; Google Chrome is not required.

### Windows (PowerShell)

```powershell
git clone https://github.com/joshuachunggg/sj-automation-hub.git
cd .\sj-automation-hub
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install firefox chromium
npm install
Copy-Item .env.example .env
notepad .env
.\.venv\Scripts\python.exe hub.py
```

If PowerShell blocks activation, do not activate it; commands above use virtual-environment Python directly.

### macOS (Terminal)

```sh
git clone https://github.com/joshuachunggg/sj-automation-hub.git
cd sj-automation-hub
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m playwright install firefox chromium
npm install
cp .env.example .env
open -e .env
.venv/bin/python hub.py
```

Fill `WMC_LOGIN_URL`, `WMC_USERNAME`, and `WMC_PASSWORD` in `.env`. Never share or commit it.

## Run flow

1. Start `hub.py` with virtual-environment Python above.
2. Choose automation.
3. Read on-screen confirmation; enter workbook path or select it.
4. Sign in when browser opens; complete MFA if prompted.
5. Keep browser open until hub says automation completed. Open **Logs** for full saved output.

### Browser behavior

Windows Finalize Authoring runs login, review, and copy work in one Firefox window. Keep that window open until the hub completes. Its signed-in project profile is `.aem-firefox`; do not delete it unless you need a clean login.

macOS defaults AEM work to Chromium. It keeps project browser data in `.aem-chrome` and attaches to that browser for AEM work.

To change default for one PowerShell session:

```powershell
$env:AEM_BROWSER = "chromium"
.\.venv\Scripts\python.exe hub.py
```

## Recovery

- **Browser does not open:** rerun `python -m playwright install firefox chromium` using virtual-environment Python.
- **WMC login missing:** recreate `.env` from `.env.example` and fill all three values.
- **Jira session expired:** choose **Live publishing**, then **Jira login setup**.
- **Run failed:** choose **Logs**, open latest file, and keep workbook unchanged until cause is known.
