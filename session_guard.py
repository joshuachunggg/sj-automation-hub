class SessionExpiredError(Exception):
    pass


async def dismiss_jira_notice(page):
    try:
        clicked = await page.evaluate("""
            () => {
                const button = document.querySelector("#hideTodayBtn") || document.querySelector("#closeBtn");
                if (!button) return false;
                button.click();
                return true;
            }
        """)
        if clicked:
            try:
                await page.locator("#announcement-banner, #noticeOverlay, #noticeFooter").wait_for(state="hidden", timeout=5000)
            except Exception:
                pass
        return clicked
    except Exception:
        return False


async def ensure_logged_in(page):
    """Call before + during a run. Raises if Jira shows a login form (session.json stale)."""
    if await page.locator('text="Log in"').is_visible():
        raise SessionExpiredError(
            "Jira session expired (found a 'Log in' element on page). "
            "Re-run auth_login.py to redo the manual SSO login, then retry this script."
        )

