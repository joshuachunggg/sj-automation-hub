# SJ Design Automation Hub

Terminal hub for the AEM FAQ QA and component-copy workflows.

## Run

```sh
git clone https://github.com/joshuachunggg/sj-automation-hub.git
cd sj-automation-hub
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
npm install
python3 hub.py
```

On Windows, use `py -m venv .venv`, `.venv\\Scripts\\pip install -r requirements.txt`, then `py hub.py`. The requirements install `windows-curses` automatically. Chrome is found in its usual Windows location; set `CHROME` to the executable path if yours is installed elsewhere.

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
