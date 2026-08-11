# SJ Design Automation Hub

Terminal hub for the AEM FAQ QA and component-copy workflows.

## macOS / Linux setup

```sh
git clone https://github.com/joshuachunggg/sj-automation-hub.git
cd sj-automation-hub
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
npm install
python3 hub.py
```

## Windows setup

This is a one-time setup. You need [Python 3](https://www.python.org/downloads/windows/), [Node.js LTS](https://nodejs.org/), and Google Chrome. In the Python installer, tick **Add Python to PATH**.

1. Get the project folder. If you have Git, open **PowerShell** (Start menu → search `PowerShell`) and run:

   ```powershell
   cd $HOME\Downloads
   git clone https://github.com/joshuachunggg/sj-automation-hub.git
   cd .\sj-automation-hub
   ```

   Without Git, use GitHub’s **Code → Download ZIP**, extract it, then open PowerShell in that extracted folder. Your prompt should end with `sj-automation-hub>`.

2. Confirm Python and Node are available:

   ```powershell
   py --version
   node --version
   npm --version
   ```

   If any command is not recognized, install that item above, close PowerShell, open a new PowerShell window, and try again.

3. Create and activate this project’s private Python environment, then install everything:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   python -m pip install -r requirements.txt
   npm install
   ```

   Activation changes the start of the prompt to `(.venv)`. If PowerShell says scripts are disabled, run this once in the same window, then activate again:

   ```powershell
   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
   ```

4. Start the hub:

   ```powershell
   python hub.py
   ```

### Starting it next time on Windows

Open PowerShell, change to the project folder, activate the environment, and run the hub:

```powershell
cd $HOME\Downloads\sj-automation-hub
.\.venv\Scripts\Activate.ps1
python hub.py
```

If you extracted the ZIP somewhere else, replace that first path with your actual folder. You can avoid activation entirely by running `.\.venv\Scripts\python.exe hub.py` from the project folder.

### Windows troubleshooting

- **Chrome not found:** Chrome is normally detected automatically. For a custom installation, run this before starting the hub (adjust the path):

  ```powershell
  $env:CHROME = 'D:\Apps\Chrome\chrome.exe'
  python hub.py
  ```

- **File picker does not open:** paste the full path to the `.xlsx` workbook into the field instead.
- **`py` is not recognized:** reinstall Python and select **Add Python to PATH**; the official installer also installs the `py` launcher.
- **`npm` is not recognized:** install Node.js LTS, then open a fresh PowerShell window.

## Current Automations

- AEM Component Copier: copies missing AEM components between author pages.
- AEM FAQ QA: audits the three-server FAQ workbook and copies approved parent content into child locales through logged-in AEM Chrome.

The hub is standalone: it needs only the declared Python and Node dependencies, plus Google Chrome. Start Chrome through the hub so the workflows can reuse its logged-in session.

## AEM FAQ QA

Open the hub and choose `AEM FAQ QA`. Press Enter on the blank workbook field to open the native file picker. Or run a plan directly:

```sh
python3 aem_faq_qa.py --workbook ./your-workbook.xlsx --plan
```

For a full pass, log into Global, Europe, and America in dev Chrome. `Audit, review, and copy` audits one parent at a time, opens its editor in the review tab, and shows every heuristic finding before approval. It checks component settings, repeated punctuation, inconsistent bold numbered step labels, and punctuation consistency after each translated step label. Press `y` to write its editor URL to row 3, or `n` to skip with an optional log note. Approved parents are then copied into their children during the same pass, up to three at a time.

```sh
python3 aem_faq_qa.py --workbook ./your-workbook.xlsx --all --review --apply
```
