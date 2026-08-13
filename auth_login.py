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
    try:
        support.wait_for(timeout=3000)
        return support  # Existing Firefox cookies already completed SSO.
    except TimeoutError:
        pass
    try:
        page.locator("div").filter(has_text="close").nth(2).click(timeout=3000)
    except TimeoutError:
        pass
    try:
        page.get_by_role("row", name="To login, please click on").get_by_role("link").click(timeout=5000)
        page.locator("#loginButton").click(timeout=5000)
    except TimeoutError:
        pass  # Samsung may have sent an existing session directly to its login page.
    email = page.get_by_role("textbox", name="Login ID (e-mail)")
    try:
        email.wait_for(timeout=5000)
    except TimeoutError:
        print("Waiting for existing SSO session or MFA approval…", flush=True)
    else:
        email.fill(env("WMC_USERNAME"))
        page.get_by_role("textbox", name="Password").fill(env("WMC_PASSWORD"))
        page.get_by_role("button", name="Sign In", exact=True).click()
        print("Waiting for MFA approval…", flush=True)
    support.wait_for(timeout=300_000)
    return support


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default=str(FIREFOX_PROFILE))
    args = parser.parse_args()
    with sync_playwright() as p:
        context = p.firefox.launch_persistent_context(args.profile, headless=False)
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(SSO_LOGIN_URL, wait_until="domcontentloaded")
        support = wait_for_support(page)
        with context.expect_page(timeout=10_000) as popup_info:
            support.click()
        popup_info.value.wait_for_load_state("domcontentloaded")
        context.close()
    print("Firefox session saved")


if __name__ == "__main__":
    main()
