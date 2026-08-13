#!/usr/bin/env python3
import curses
import json
import os
import platform
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
CHROME_PROFILE = ROOT / ".aem-chrome"
FIREFOX_PROFILE = ROOT / ".aem-firefox"
LOG_DIR = ROOT / "logs"
ENV_FILE = ROOT / ".env"
CDP_ENDPOINT = "http://127.0.0.1:9223"
CDP_ENDPOINTS = ("http://127.0.0.1:9223", "http://127.0.0.1:9222")


def main():
    if hasattr(curses, "set_escdelay"):
        curses.set_escdelay(25)
    while True:
        choice = menu(
            "SJ Design Automation Hub",
            [
                ("Live publishing", aem_publishing, "Publish pending FAQ translations through Jira"),
                ("UK/CA Master", component_copier, "Copy missing author-page components"),
                ("Finalize Authoring", aem_faq_qa, "Audit and copy FAQ content across locales"),
                ("Logs", logs, "Open a saved run log"),
                ("Quit", None, "Close the hub"),
            ],
            back=False,
        )
        if choice is None:
            return
        choice()


def menu(title, items, back=True):
    def draw(screen):
        setup_screen(screen)
        selected = 0
        while True:
            clear_screen(screen)
            height, width = screen.getmaxyx()
            header(screen, title)
            for index, item in enumerate(items):
                label, _, description = (*item, "")[:3]
                attr = curses.color_pair(2) | curses.A_BOLD if index == selected else curses.color_pair(3)
                row = 5 + index * (2 if description else 1)
                marker = ">" if index == selected else " "
                screen.addnstr(row, 4, f"{marker} {label}", width - 8, attr)
                if description:
                    screen.addnstr(row + 1, 7, screen_text(description), width - 11, curses.color_pair(6))
            shortcuts = " Up/Down move  Enter select  q quit " if not back else " Up/Down move  Enter select  b/Esc back "
            footer(screen, shortcuts)
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


def component_copier():
    browser = aem_browser()
    if not panel(
        "AEM Component Copier",
        [
            "Copies missing AEM components from one author page to another.",
            f"{browser.title()} will open for AEM login.",
            "Log into AEM, then return here.",
            "The target container is locked to jcr:content/root/responsivegrid/responsivegrid by default.",
        ],
        wait=True,
    ):
        return
    if browser == "chromium" and not ensure_aem_chrome(["Log into AEM in the Chrome window that just opened.", "Return here when both source and target author domains are logged in."]):
        return
    if browser == "firefox" and not ensure_aem_firefox():
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
    args = ["node", str(ROOT / "copy-aem-components.mjs"), "--source", source, "--target", target]
    args += aem_browser_args(browser)
    if yes:
        args.append("--yes")
    run_logged("AEM Component Copier", args)


def aem_publishing():
    choice = menu(
        "AEM FAQ Publishing",
        [
            ("Publish pending country columns", "publish"),
            ("Validate already-published live URLs", "validate"),
            ("Validate all locale URLs", "validate-all", "Check and write every locale URL without Jira"),
            ("Jira login setup", "login"),
        ],
    )
    if not choice:
        return
    browser = menu("Publishing Browser", [
        ("Firefox", "firefox", "Use Playwright Firefox for Jira and live checks"),
        ("Chromium", "chromium", "Use Playwright Chromium for Jira and live checks"),
    ])
    if not browser:
        return
    if choice == "login":
        return jira_login(browser)
    workbook = ask_path("Publishing workbook", None)
    if not workbook:
        return
    workers = ask("Parallel Jira tabs (1-15)", "10")
    if workers is None:
        return
    args = [python(), str(ROOT / "main.py"), "--workbook", str(workbook), "--workers", workers, "--browser", browser]
    if choice in ("validate", "validate-all"):
        args.append("--validate-all" if choice == "validate-all" else "--validate-only")
    run_logged("AEM FAQ Publishing", args)


def jira_login(browser="chromium"):
    LOG_DIR.mkdir(exist_ok=True)
    log_path = LOG_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}-jira-login-setup.log"
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [python(), str(ROOT / "auth_login.py"), "--browser", browser],
            stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
        if panel("Jira Login", ["Complete SSO/MFA in the browser, then press Enter to save this hub's local session."], wait=True):
            process.stdin.write("\n")
            process.stdin.flush()
            wait_process("Jira Login Setup", process, log_path)
        else:
            process.terminate()


def aem_faq_qa():
    browser = aem_browser()
    if not panel(
        "AEM FAQ QA",
        [
            "Audits and reviews each unapproved parent, then copies approved children.",
            f"Uses {browser.title()} for AEM.",
            "Log into Global, Europe, and America before starting the full pass.",
        ],
        wait=True,
    ):
        return
    workbook = ask_path("FAQ workbook", None)
    if not workbook:
        return
    mode = menu(
        "AEM FAQ QA",
        [
            ("Show workbook plan", "plan"),
            ("Audit, review, and copy", "review"),
        ],
    )
    if not mode:
        return
    args = [python(), str(ROOT / "aem_faq_qa.py"), "--workbook", str(workbook)]
    if mode == "plan":
        args.append("--plan")
        return run_logged("AEM FAQ QA Plan", args)

    if browser == "chromium" and not ensure_faq_chrome():
        return
    if not confirm("Audit and review every unapproved parent, then copy approved children?", False):
        return
    args.append("--all")
    args += aem_browser_args(browser)
    args += ["--review", "--apply"]
    run_logged("AEM FAQ QA Full Pass", args, review=True, env=load_env() if browser == "firefox" else None)


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
        setup_screen(screen)
        while True:
            clear_screen(screen)
            height, width = screen.getmaxyx()
            header(screen, title)
            for row, line in enumerate(lines, 3):
                screen.addnstr(row, 4, screen_text(line), width - 8)
            label = " Enter continue  b/Esc back " if wait else " b/Esc back "
            footer(screen, label)
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
        setup_screen(screen, cursor=True)
        value = default or ""
        while True:
            clear_screen(screen)
            height, width = screen.getmaxyx()
            header(screen, label)
            screen.addnstr(4, 4, screen_text(value), width - 8)
            footer(screen, " Enter accept  Esc back  Backspace delete ")
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
        answer = ask(label, str(default) if default else "")
        if answer is None:
            return None
        if not answer:
            picked = pick_file()
            if picked:
                answer = picked
            else:
                continue
        value = Path(answer).expanduser()
        if value.exists():
            return value
        panel("File Not Found", [str(value)], wait=True)


def confirm(label, default):
    chosen = menu(label, [("Yes", True), ("No", False)])
    return chosen


def ensure_aem_chrome(login_lines):
    if use_existing_dev_chrome():
        return True
    if not launch_dev_chrome():
        return False
    activate_dev_chrome()
    return panel("Chrome Login", login_lines, wait=True)


def ensure_faq_chrome():
    if use_existing_dev_chrome():
        return True
    if not dev_chrome_ready():
        if not launch_dev_chrome():
            return False
        for _ in range(40):
            if dev_chrome_ready():
                break
            time.sleep(0.25)
        else:
            panel("Dev Chrome Did Not Start", ["Close a stale Hub Chrome process and try again."], wait=True)
            return False
    activate_dev_chrome()
    values = load_env()
    return run_logged(
        "Samsung WMC Login",
        ["node", str(ROOT / "aem_wmc_login.mjs")],
        env=values, mfa=True, return_on_success=True,
    )


def ensure_faq_browser(browser):
    return ensure_faq_chrome() if browser == "chromium" else ensure_aem_firefox()


def ensure_aem_firefox():
    return run_logged(
        "Samsung WMC Login",
        ["node", str(ROOT / "aem_wmc_login.mjs"), *aem_browser_args("firefox")],
        env=load_env(), mfa=True, return_on_success=True,
    )


def aem_browser():
    default = "firefox" if platform.system() == "Windows" else "chromium"
    return os.environ.get("AEM_BROWSER", default).lower() if os.environ.get("AEM_BROWSER", default).lower() in ("chromium", "firefox") else default


def aem_browser_args(browser):
    return ["--browser", browser, "--user-data-dir", str(FIREFOX_PROFILE)] if browser == "firefox" else []


def dev_chrome_ready():
    return bool(dev_chrome_endpoint())


def dev_chrome_endpoint():
    for endpoint in CDP_ENDPOINTS:
        if endpoint_ready(endpoint):
            return endpoint
    return ""


def endpoint_ready(endpoint):
    try:
        with urlopen(f"{endpoint}/json/version", timeout=0.2) as response:
            version = json.load(response)
            return response.status == 200 and "Chrome" in version.get("Browser", "") and bool(version.get("webSocketDebuggerUrl"))
    except (OSError, ValueError):
        return False


def use_existing_dev_chrome():
    global CDP_ENDPOINT
    endpoint = dev_chrome_endpoint()
    if endpoint:
        CDP_ENDPOINT = endpoint
        return True
    return False


def chrome_ready():
    """Backward-compatible name for callers that only need the dev-Chrome check."""
    return dev_chrome_ready()


def python():
    return os.environ.get("PYTHON", sys.executable)


def run_logged(title, args, cwd=None, review=False, env=None, mfa=False, return_on_success=False):
    LOG_DIR.mkdir(exist_ok=True)
    log_path = LOG_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}-{slug(title)}.log"
    with log_path.open("w", encoding="utf-8") as log:
        log.write("$ " + " ".join(shlex.quote(str(arg)) for arg in args) + "\n\n")
        log.flush()
        process = subprocess.Popen(args, cwd=cwd, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT, text=True, bufsize=1, env={**os.environ, **(env or {}), "CDP": CDP_ENDPOINT, "PYTHONIOENCODING": "utf-8"})
        return wait_process(title, process, log_path, review, mfa, return_on_success)


def wait_process(title, process, log_path, review=False, mfa=False, return_on_success=False):
    def draw(screen):
        setup_screen(screen)
        screen.timeout(250)
        started = time.time()
        handled_review = ""
        handled_server_setup = False
        previous_lines = None
        while process.poll() is None:
            height, width = screen.getmaxyx()
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            if lines != previous_lines:
                clear_screen(screen)
                header(screen, title)
                progress = next((line for line in reversed(lines) if line.startswith("PROGRESS ")), "Running")
                findings = sum(line.startswith("FINDING ") for line in lines)
                copies = sum(line.startswith("COPY DONE ") for line in lines)
                screen.addnstr(3, 4, screen_text(progress), width - 8, curses.color_pair(2) | curses.A_BOLD)
                screen.addnstr(4, width // 3, f"Findings {findings}", width // 3 - 4, curses.color_pair(4))
                screen.addnstr(4, 2 * width // 3, f"Copies {copies}", width // 3 - 4, curses.color_pair(5))
                screen.addnstr(6, 4, "Recent activity", width - 8, curses.A_BOLD | curses.color_pair(3))
                rows = max(1, height - 10)
                for row, line in enumerate(lines[-rows:], 7):
                    screen.addnstr(row, 4, screen_text(line), width - 8, curses.color_pair(3))
                footer(screen, " Ctrl+C stop  live log is saved ")
                previous_lines = lines
            screen.addnstr(4, 4, f"Elapsed {int(time.time() - started)}s", width // 3 - 6, curses.color_pair(3))
            screen.refresh()
            key = screen.getch()
            if review:
                pending = next((line for line in reversed(lines) if line.startswith("REVIEW ITEM ")), "")
                if pending and pending != handled_review:
                    handled_review = pending
                    if not review_prompt(screen, process, lines, pending):
                        process.terminate()
                        return False
                    continue
            if mfa and not handled_server_setup and "SERVER SETUP READY" in lines:
                handled_server_setup = True
                if server_setup_prompt(screen):
                    process.stdin.write("\n")
                    process.stdin.flush()
                    continue
                process.terminate()
                return False
            if key == 3:
                process.terminate()
                return False
        clear_screen(screen)
        if return_on_success and process.returncode == 0:
            return True
        status = "completed" if process.returncode == 0 else f"exited with code {process.returncode}"
        height, width = screen.getmaxyx()
        header(screen, title)
        screen.addnstr(3, 4, f"Automation {status}.", width - 8)
        screen.addnstr(5, 4, screen_text(f"Log: {log_path}"), width - 8)
        footer(screen, " Enter return to hub  l view log ")
        while True:
            key = screen.getch()
            if key in (10, 13):
                return process.returncode == 0
            if key == ord("l"):
                view_log(log_path)

    try:
        return curses.wrapper(draw)
    except KeyboardInterrupt:
        process.terminate()
        return False


def server_setup_prompt(screen):
    screen.timeout(-1)
    while True:
        clear_screen(screen)
        height, width = screen.getmaxyx()
        header(screen, "Prepare AEM Support servers")
        screen.addnstr(5, 4, "Complete Samsung 2FA if prompted, then open Support for Global, Europe, and America.", width - 8, curses.color_pair(3))
        screen.addnstr(7, 4, "Wait until all three AEM pages finish loading, then return here.", width - 8, curses.color_pair(6))
        footer(screen, " Enter continue with FAQ QA  Esc cancel ")
        key = screen.getch()
        if key in (10, 13):
            screen.timeout(250)
            return True
        if key == 27:
            screen.timeout(250)
            return False


def review_prompt(screen, process, lines, review_line):
    screen.timeout(-1)
    _, _, target, link = review_line.split(" ", 3)
    while True:
        clear_screen(screen)
        height, width = screen.getmaxyx()
        header(screen, f"Review {target}")
        screen.addnstr(3, 4, screen_text(link), width - 8)
        findings = [line for line in lines if line.startswith(f"FINDING {target}:")]
        screen.addnstr(5, 4, "Found:", width - 8, curses.A_BOLD)
        shown = findings or ["No heuristic differentials found."]
        for row, finding in enumerate(shown[-max(1, height - 9):], 6):
            screen.addnstr(row, 4, screen_text(finding), width - 8)
        footer(screen, " y approve and write row 3   n skip (then optional note) ")
        key = screen.getch()
        if key == ord("y"):
            process.stdin.write("y\n")
            process.stdin.flush()
            screen.timeout(250)
            return True
        if key == ord("n"):
            process.stdin.write(f"n {review_note(screen)}\n")
            process.stdin.flush()
            screen.timeout(250)
            return True
        if key in (27, ord("b")):
            screen.timeout(250)
            return False


def review_note(screen):
    value = ""
    while True:
        clear_screen(screen)
        height, width = screen.getmaxyx()
        header(screen, "Optional review note")
        screen.addnstr(4, 4, screen_text(value), width - 8)
        footer(screen, " Enter save note  Esc no note ")
        key = screen.getch()
        if key in (10, 13):
            return value.strip()
        if key == 27:
            return ""
        if key in (curses.KEY_BACKSPACE, 127, 8):
            value = value[:-1]
        elif 32 <= key <= 126:
            value += chr(key)


def view_log(path):
    text = path.read_text(encoding="utf-8", errors="replace").splitlines()
    def draw(screen):
        setup_screen(screen)
        offset = max(0, len(text) - 1)
        while True:
            clear_screen(screen)
            height, width = screen.getmaxyx()
            header(screen, path.name)
            rows = height - 4
            start = max(0, min(offset, len(text) - rows))
            for row, line in enumerate(text[start:start + rows], 3):
                screen.addnstr(row, 0, screen_text(line), width - 1)
            footer(screen, " Up/Down scroll  b/Esc back  q quit ")
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


def pick_file():
    """Use the platform file chooser; return empty when it is cancelled or unavailable."""
    if platform.system() == "Darwin":
        result = subprocess.run(
            ["osascript", "-e", 'POSIX path of (choose file with prompt "Choose FAQ workbook" of type {"org.openxmlformats.spreadsheetml.sheet"})'],
            text=True, capture_output=True,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    try:
        from tkinter import Tk, filedialog
        root = Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askopenfilename(title="Choose FAQ workbook", filetypes=[("Excel workbooks", "*.xlsx")])
        root.destroy()
        return selected
    except Exception:
        return ""


def load_env():
    values = {}
    if not ENV_FILE.exists():
        return values
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and key and not key.startswith("#"):
            values[key.strip()] = value.strip()
    return values


def chrome_command():
    configured = os.environ.get("CHROME")
    if configured:
        return configured
    system = platform.system()
    candidates = {
        "Darwin": ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"],
        "Windows": [
            str(Path(folder) / "Google/Chrome/Application/chrome.exe")
            for folder in (os.environ.get("LOCALAPPDATA"), os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"))
            if folder
        ],
    }.get(system, [])
    candidates.extend(filter(None, (shutil.which(name) for name in ("google-chrome", "chromium", "chromium-browser", "chrome"))))
    return next((candidate for candidate in candidates if Path(candidate).exists()), None)


def launch_dev_chrome():
    chrome = chrome_command()
    if not chrome:
        panel("Chrome Not Found", ["Install Google Chrome, or set CHROME to its executable path."], wait=True)
        return False
    args = [
        "--new-window",
        "--no-first-run",
        "--no-default-browser-check",
        "--remote-debugging-port=9223",
        f"--user-data-dir={CHROME_PROFILE}",
        "about:blank",
    ]
    subprocess.Popen([chrome, *args], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True


def activate_dev_chrome():
    if platform.system() == "Darwin":
        subprocess.run(
            ["osascript", "-e", 'tell application "Google Chrome" to activate'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )


def setup_screen(screen, cursor=False):
    curses.curs_set(1 if cursor else 0)
    if curses.has_colors():
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_CYAN)
        curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_CYAN)
        curses.init_pair(3, curses.COLOR_WHITE, -1)
        curses.init_pair(4, curses.COLOR_YELLOW, -1)
        curses.init_pair(5, curses.COLOR_GREEN, -1)
        curses.init_pair(6, curses.COLOR_CYAN, -1)


def clear_screen(screen):
    (screen.clear if platform.system() == "Windows" else screen.erase)()


def screen_text(value):
    text = str(value)
    return text.encode("ascii", "backslashreplace").decode() if platform.system() == "Windows" else text


def header(screen, title):
    height, width = screen.getmaxyx()
    screen.addnstr(0, 2, "SJ DESIGN  /  AUTOMATION HUB", width - 4, curses.A_BOLD | curses.color_pair(6))
    screen.addnstr(1, 4, screen_text(title), width - 8, curses.A_BOLD | curses.color_pair(2))
    screen.hline(2, 2, curses.ACS_HLINE, max(0, width - 4), curses.color_pair(2))


def footer(screen, text):
    height, width = screen.getmaxyx()
    screen.addnstr(height - 1, 0, screen_text(text.center(max(1, width - 1))), width - 1, curses.color_pair(1) | curses.A_BOLD)


if __name__ == "__main__":
    main()
