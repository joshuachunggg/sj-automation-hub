#!/usr/bin/env python3
import curses
import shlex
import subprocess
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AEM_PUBLISHING = Path("/Users/joshuachung/Documents/projects/aem-publishing/translation_pipeline")
COMPONENT_COPIER = Path("/Users/joshuachung/Downloads/authoring")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CHROME_PROFILE = "/tmp/aem-chrome"
LOG_DIR = ROOT / "logs"


def main():
    if hasattr(curses, "set_escdelay"):
        curses.set_escdelay(25)
    while True:
        choice = menu(
            "SJ Design Automation Hub",
            [
                ("AEM FAQ Publishing", aem_publishing),
                ("AEM Component Copier", component_copier),
                ("Jira Login Setup", jira_login),
                ("Logs", logs),
                ("Quit", None),
            ],
            back=False,
        )
        if choice is None:
            return
        choice()


def menu(title, items, back=True):
    def draw(screen):
        curses.curs_set(0)
        selected = 0
        while True:
            screen.erase()
            height, width = screen.getmaxyx()
            screen.addnstr(1, 2, title, width - 4, curses.A_BOLD)
            for index, (label, _) in enumerate(items):
                attr = curses.A_REVERSE if index == selected else curses.A_NORMAL
                screen.addnstr(5 + index, 4, label, width - 8, attr)
            shortcuts = " ↑/↓ move  Enter select  q quit " if not back else " ↑/↓ move  Enter select  b/Esc back "
            screen.addnstr(height - 1, 0, shortcuts, width - 1, curses.A_REVERSE)
            key = screen.getch()
            if key == ord("q") or (back and key in (ord("b"), 27)):
                return None
            if key in (curses.KEY_UP, ord("k")):
                selected = (selected - 1) % len(items)
            elif key in (curses.KEY_DOWN, ord("j")):
                selected = (selected + 1) % len(items)
            elif key in (10, 13):
                return items[selected][1]

    return curses.wrapper(draw)


def aem_publishing():
    if not panel(
        "AEM FAQ Publishing",
        [
            "Publishes pending country columns from an Excel workbook through Jira.",
            "Progress is saved back to the workbook as each live URL is confirmed.",
            "Use Jira Login Setup first if the saved Jira session expired.",
        ],
        wait=True,
    ):
        return
    workbook = ask_path("Workbook path", AEM_PUBLISHING / "mob27.xlsx")
    if not workbook:
        return
    workers = ask("Parallel Jira tabs", "10")
    if workers is None:
        return
    validate = confirm("Only validate already-published live URLs?", False)
    if validate is None:
        return
    args = [python(), str(ROOT / "run_aem_publishing.py"), "--workbook", str(workbook), "--workers", workers]
    if validate:
        args.append("--validate-only")
    run_logged("AEM FAQ Publishing", args)


def component_copier():
    if not panel(
        "AEM Component Copier",
        [
            "Copies missing AEM components from one author page to another.",
            "Chrome will open with remote debugging enabled.",
            "Log into AEM in that Chrome window, then return here.",
            "The target container is locked to jcr:content/root/responsivegrid/responsivegrid by default.",
        ],
        wait=True,
    ):
        return
    subprocess.Popen([CHROME, "--remote-debugging-port=9222", f"--user-data-dir={CHROME_PROFILE}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not panel("Chrome Login", ["Log into AEM in the Chrome window that just opened.", "Return here when both source and target author domains are logged in."], wait=True):
        return
    source = ask("Source/read page URL")
    if not source:
        return
    target = ask("Target/write page URL")
    if not target:
        return
    yes = confirm("Bypass per-component Enter prompts?", True)
    if yes is None:
        return
    args = ["npm", "run", "aem:copy", "--", "--source", source, "--target", target]
    if yes:
        args.append("--yes")
    run_logged("AEM Component Copier", args, cwd=COMPONENT_COPIER)


def jira_login():
    if not panel(
        "Jira Login Setup",
        [
            "Opens Jira in Chromium and saves a local session file.",
            "Run this initially, or whenever publishing says the Jira session expired.",
        ],
        wait=True,
    ):
        return
    run_login()


def logs():
    LOG_DIR.mkdir(exist_ok=True)
    files = sorted(LOG_DIR.glob("*.log"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not files:
        panel("Logs", ["No logs yet."], wait=True)
        return
    chosen = menu("Logs", [(path.name, path) for path in files[:30]])
    if chosen:
        view_log(chosen)


def panel(title, lines, wait=False):
    def draw(screen):
        curses.curs_set(0)
        while True:
            screen.erase()
            height, width = screen.getmaxyx()
            screen.addnstr(1, 2, title, width - 4, curses.A_BOLD)
            for row, line in enumerate(lines, 3):
                screen.addnstr(row, 4, line, width - 8)
            label = " Enter continue  b/Esc back " if wait else " b/Esc back "
            screen.addnstr(height - 1, 0, label, width - 1, curses.A_REVERSE)
            if not wait:
                screen.getch()
                return True
            key = screen.getch()
            if key in (10, 13):
                return True
            if key in (ord("b"), 27):
                return False

    return curses.wrapper(draw)


def ask(label, default=None):
    def draw(screen):
        curses.curs_set(1)
        value = default or ""
        while True:
            screen.erase()
            height, width = screen.getmaxyx()
            screen.addnstr(2, 2, label, width - 4, curses.A_BOLD)
            screen.addnstr(4, 4, value, width - 8)
            screen.addnstr(height - 1, 0, " Enter accept  Esc back  Backspace delete ", width - 1, curses.A_REVERSE)
            key = screen.getch()
            if key in (10, 13):
                return value.strip()
            if key == 27:
                return None
            if key in (curses.KEY_BACKSPACE, 127, 8):
                value = value[:-1]
            elif 32 <= key <= 126:
                value += chr(key)

    return curses.wrapper(draw)


def ask_path(label, default):
    while True:
        answer = ask(label, str(default))
        if answer is None:
            return None
        value = Path(answer).expanduser()
        if value.exists():
            return value
        panel("File Not Found", [str(value)], wait=True)


def confirm(label, default):
    chosen = menu(label, [("Yes", True), ("No", False)])
    return chosen


def python():
    venv = AEM_PUBLISHING / ".venv/bin/python"
    return str(venv if venv.exists() else Path("/usr/bin/python3"))


def run_logged(title, args, cwd=None):
    LOG_DIR.mkdir(exist_ok=True)
    log_path = LOG_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}-{slug(title)}.log"
    with log_path.open("w") as log:
        log.write("$ " + " ".join(shlex.quote(str(arg)) for arg in args) + "\n\n")
        process = subprocess.Popen(args, cwd=cwd, stdout=log, stderr=subprocess.STDOUT)
        wait_process(title, process, log_path)


def run_login():
    LOG_DIR.mkdir(exist_ok=True)
    log_path = LOG_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}-jira-login-setup.log"
    args = [str(AEM_PUBLISHING / ".venv/bin/python"), "auth_login.py"]
    with log_path.open("w") as log:
        log.write("$ " + " ".join(shlex.quote(str(arg)) for arg in args) + "\n\n")
        process = subprocess.Popen(args, cwd=AEM_PUBLISHING, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT, text=True)
        if panel("Jira Login", ["Complete SSO/MFA in the browser that opened.", "Press Enter here after Jira is fully loaded."], wait=True):
            process.stdin.write("\n")
            process.stdin.flush()
            wait_process("Jira Login Setup", process, log_path)
        else:
            process.terminate()


def wait_process(title, process, log_path):
    def draw(screen):
        curses.curs_set(0)
        started = time.time()
        while process.poll() is None:
            screen.erase()
            height, width = screen.getmaxyx()
            screen.addnstr(1, 2, title, width - 4, curses.A_BOLD)
            screen.addnstr(3, 4, "Running in the background. Logs are being saved.", width - 8)
            screen.addnstr(5, 4, f"Elapsed: {int(time.time() - started)}s", width - 8)
            screen.addnstr(6, 4, f"Log: {log_path}", width - 8)
            screen.addnstr(height - 1, 0, " Ctrl+C stop  logs available from hub ", width - 1, curses.A_REVERSE)
            screen.refresh()
            time.sleep(0.25)
        screen.erase()
        status = "completed" if process.returncode == 0 else f"exited with code {process.returncode}"
        height, width = screen.getmaxyx()
        screen.addnstr(1, 2, title, width - 4, curses.A_BOLD)
        screen.addnstr(3, 4, f"Automation {status}.", width - 8)
        screen.addnstr(5, 4, f"Log: {log_path}", width - 8)
        screen.addnstr(height - 1, 0, " Enter return to hub  l view log ", width - 1, curses.A_REVERSE)
        while True:
            key = screen.getch()
            if key in (10, 13):
                return
            if key == ord("l"):
                return view_log(log_path)

    try:
        curses.wrapper(draw)
    except KeyboardInterrupt:
        process.terminate()


def view_log(path):
    text = path.read_text(errors="replace").splitlines()
    def draw(screen):
        curses.curs_set(0)
        offset = max(0, len(text) - 1)
        while True:
            screen.erase()
            height, width = screen.getmaxyx()
            screen.addnstr(0, 2, path.name, width - 4, curses.A_BOLD)
            rows = height - 2
            start = max(0, min(offset, len(text) - rows))
            for row, line in enumerate(text[start:start + rows], 1):
                screen.addnstr(row, 0, line, width - 1)
            screen.addnstr(height - 1, 0, " ↑/↓ scroll  b/Esc back  q quit ", width - 1, curses.A_REVERSE)
            key = screen.getch()
            if key in (ord("b"), ord("q"), 27):
                return
            if key in (curses.KEY_UP, ord("k")):
                offset = max(0, offset - 1)
            elif key in (curses.KEY_DOWN, ord("j")):
                offset = min(len(text), offset + 1)

    return curses.wrapper(draw)


def slug(value):
    return "".join(char.lower() if char.isalnum() else "-" for char in value).strip("-")


if __name__ == "__main__":
    main()
