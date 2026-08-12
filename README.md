# SJ Design Automation Hub

A native terminal hub for AEM FAQ publishing, FAQ QA, and component copying. It runs on macOS and Windows, uses Google Chrome for AEM, and stores its Samsung WMC credentials only in your ignored local `.env`.

## First-time setup: macOS

1. Install [Python 3](https://www.python.org/downloads/), [Node.js LTS](https://nodejs.org/), and Google Chrome.

2. Open Terminal and run:

   ```sh
   git clone https://github.com/joshuachunggg/sj-automation-hub.git
   cd sj-automation-hub
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   .venv/bin/playwright install chromium
   npm install
   ```

3. Configure Samsung WMC login for FAQ QA:

   ```sh
   cp .env.example .env
   ```

   Fill `WMC_LOGIN_URL`, `WMC_USERNAME`, and `WMC_PASSWORD` in `.env`. This file is ignored by Git; do not share it.

4. Start the hub:

   ```sh
   .venv/bin/python hub.py
   ```

## Later starts: macOS

```sh
cd /path/to/sj-automation-hub
.venv/bin/python hub.py
```

## First-time setup: Windows

1. Install [Python 3](https://www.python.org/downloads/windows/) (select **Add Python to PATH**), [Node.js LTS](https://nodejs.org/), and Google Chrome.

2. Open PowerShell and clone the hub:

   ```powershell
   cd $HOME\Downloads
   git clone https://github.com/joshuachunggg/sj-automation-hub.git
   cd .\sj-automation-hub
   ```

   Without Git, download the repository ZIP from GitHub, extract it, and open PowerShell in the extracted folder.

3. Install the project dependencies:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   python -m playwright install chromium
   npm install
   ```

   If activation is blocked, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` once in that PowerShell window, then activate again.

4. Create `.env` by copying `.env.example`, then fill the three `WMC_…` values. Keep this file private.

   ```powershell
   Copy-Item .env.example .env
   notepad .env
   ```

5. Start the hub:

   ```powershell
   .\.venv\Scripts\python.exe hub.py
   ```

## Later starts: Windows

```powershell
cd $HOME\Downloads\sj-automation-hub
.\.venv\Scripts\python.exe hub.py
```

## Automations

- **AEM FAQ Publishing:** publish pending country columns through Jira or validate live URLs. Run its Jira login setup when the saved session expires.
- **AEM Component Copier:** copy missing components between AEM author pages.
- **AEM FAQ QA:** audit parent FAQs, collect your review decisions, then copy approved content to child locales.

When FAQ QA starts, the hub reuses an active WMC Chrome session. If it is not already signed in, it opens WMC, fills the local credentials, pauses for your phone approval, and continues only after you press Enter. The browser remains visible throughout.

## Troubleshooting

- **Chrome not found:** install Google Chrome, or set the `CHROME` environment variable to its executable.
- **Workbook picker does not open:** paste the full `.xlsx` path into the hub.
- **WMC login is missing:** create `.env` from `.env.example`; never commit it.
- **Jira session expired:** select **AEM FAQ Publishing → Jira login setup**.
