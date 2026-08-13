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


def open_support_servers(context, page, support):
    """Visit every Support service exposed by the SSO home page."""
    pages = []
    for index in (0, 2, 3):  # The recorded SSO page has these three Support services.
        if support.count() <= index:
            continue
        try:
            with context.expect_page(timeout=10_000) as popup_info:
                support.nth(index).click()
            pages.append(popup_info.value)
        except TimeoutError:
            pages.append(page)  # This Support link reused the SSO tab.
    for service in pages:
        service.wait_for_load_state("domcontentloaded")
    for service in pages:
        if service is not page:
            service.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default=str(FIREFOX_PROFILE))
    args = parser.parse_args()
    with sync_playwright() as p:
        context = p.firefox.launch_persistent_context(args.profile, headless=False, args=["--allow-downgrade"])
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(SSO_LOGIN_URL, wait_until="domcontentloaded")
        support = wait_for_support(page)
        open_support_servers(context, page, support)
        context.close()
    print("Firefox session saved")


if __name__ == "__main__":
    main()
