"""One-time (or re-run when session expires) manual login. Saves storage_state to SESSION_FILE."""
from playwright.sync_api import sync_playwright
from config import JIRA_BASE_URL, SESSION_FILE


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(JIRA_BASE_URL)
        input("Log in manually (complete SSO/MFA), then press Enter here once Jira is loaded... ")
        context.storage_state(path=SESSION_FILE)
        browser.close()
    print(f"Session saved to {SESSION_FILE}")


if __name__ == "__main__":
    main()

