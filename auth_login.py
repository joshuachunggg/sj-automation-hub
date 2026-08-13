"""Automatic Samsung SSO login for the hub's shared Firefox profile."""
import argparse
import os
from pathlib import Path

from playwright.sync_api import TimeoutError, sync_playwright
from config import FIREFOX_PROFILE, SSO_LOGIN_URL


def env(name):
    value = os.getenv(name)
    if value:
        return value
    for line in (Path(__file__).with_name(".env")).read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip() == name:
            return value.strip().strip('"').strip("'")
    raise RuntimeError(f"{name} is missing from .env")


def wait_for_support(page):
    support = page.get_by_role("link", name="Support").first
    waiting = False
    while True:
        try:
            support.wait_for(timeout=2000)
            return support  # Existing Firefox cookies already completed SSO.
        except TimeoutError:
            pass
        try:
            page.locator("div").filter(has_text="close").nth(2).click(timeout=1000)
        except TimeoutError:
            pass
        try:
            page.get_by_role("row", name="To login, please click on").get_by_role("link").click(timeout=1000)
        except TimeoutError:
            pass
        try:
            page.locator("#loginButton").click(timeout=1000)
        except TimeoutError:
            pass  # Already at a later SSO state, or a page error awaiting refresh.
        email = page.get_by_role("textbox", name="Login ID (e-mail)")
        try:
            email.wait_for(timeout=1000)
        except TimeoutError:
            if not waiting:
                print("Waiting for Support. If Firefox shows an error, refresh it; sign-in will continue.", flush=True)
                waiting = True
            page.wait_for_timeout(3000)
            continue
        email.fill(env("WMC_USERNAME"))
        page.get_by_role("textbox", name="Password").fill(env("WMC_PASSWORD"))
        page.get_by_role("button", name="Sign In", exact=True).click()
        print("Waiting for MFA approval…", flush=True)
        waiting = False
        page.wait_for_timeout(3000)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default=str(FIREFOX_PROFILE))
    args = parser.parse_args()
    with sync_playwright() as p:
        context = p.firefox.launch_persistent_context(args.profile, headless=False, args=["--allow-downgrade"])
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(SSO_LOGIN_URL, wait_until="domcontentloaded")
        wait_for_support(page)
        input("WMC home is ready. Finish Support links manually, then press Enter. ")
        context.close()
    print("Firefox session saved")


if __name__ == "__main__":
    main()
