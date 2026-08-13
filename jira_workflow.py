import re
from pathlib import Path
from urllib.parse import urljoin
from session_guard import dismiss_jira_notice, ensure_logged_in

SCREENSHOT_DIR = Path("/private/tmp/aem-publishing-screenshots")


async def _screenshot(page, col, description):
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    shot = SCREENSHOT_DIR / f"fail_{col.site_code}_{description.replace(' ', '_')}.png"
    await page.screenshot(path=str(shot))
    return shot


async def _click_or_report(page, locator, description, col):
    """Wait for locator, click it. On any failure: screenshot + raise with expected-vs-context."""
    try:
        await locator.wait_for(state="visible", timeout=20000)
        await page.wait_for_timeout(1000)  # settle buffer after detection, in case of site lag
        try:
            await locator.click()
        except Exception:
            await locator.click(force=True)
    except Exception as e:
        shot = await _screenshot(page, col, description)
        raise RuntimeError(
            f"[{col.sheet_name} col {col.col_idx}] Expected '{description}' to be clickable, "
            f"but it failed: {e}. Site code: {col.site_code}. Screenshot: {shot}"
        )


async def _workflow_state(page):
    try:
        dropdown = page.locator("#opsbar-transitions_more")
        return (await dropdown.inner_text()).strip().upper() if await dropdown.is_visible() else ""
    except Exception:
        return ""


async def _status_is_live(page):
    """Ground truth: the status dropdown reads 'LIVE'."""
    return await _workflow_state(page) == "LIVE"


def _production_dropdown(page):
    return page.locator("#opsbar-transitions_more").filter(has_text=re.compile(r"\bPRODUCTION\b", re.IGNORECASE))


async def _is_in_production(page):
    """True after Start AEM Workflow has advanced the ticket to PRODUCTION."""
    return await _workflow_state(page) == "PRODUCTION"


async def _submit_and_wait_close(page, confirm_locator, modal_heading, description, col,
                                 retries=6, poll_ms=5000, success_check=None):
    """
    Click confirm_locator; verify modal_heading actually goes away (the signal that the
    submit registered), retrying the click if it doesn't - instead of guessing a fixed delay.
    If modal_heading was never shown to begin with (no modal for this action), the first
    wait_for(hidden) resolves immediately and we return after one click.

    success_check: optional extra ground-truth check (e.g. status dropdown reads LIVE).
    Some actions succeed for real even when modal_heading never reports hidden (flaky/wrong
    element) - checked from the halfway point of the retry budget onward, and once more
    before giving up.
    """
    try:
        await confirm_locator.wait_for(state="visible", timeout=20000)
        await page.wait_for_timeout(1000)  # settle buffer after detection, in case of site lag
    except Exception as e:
        shot = await _screenshot(page, col, description)
        raise RuntimeError(
            f"[{col.sheet_name} col {col.col_idx}] Expected '{description}' to be visible, "
            f"but it failed: {e}. Site code: {col.site_code}. Screenshot: {shot}"
        )

    halfway = max(1, retries // 2)
    for i in range(retries):
        try:
            await confirm_locator.click()
        except Exception:
            break  # button's likely gone already because it already submitted - go check ground truth

        try:
            await modal_heading.wait_for(state="hidden", timeout=poll_ms)
            return
        except Exception:
            pass

        if success_check is not None and i + 1 >= halfway and await success_check():
            return

    if success_check is not None and await success_check():
        return

    shot = await _screenshot(page, col, description)
    raise RuntimeError(
        f"[{col.sheet_name} col {col.col_idx}] Clicked '{description}' {retries} times, "
        f"but its modal never closed. Site code: {col.site_code}. Screenshot: {shot}"
    )


async def _find_ticket_link(page, col):
    """Find exact site and slug among Jira's rendered issue links, then page 2."""
    rows = page.locator("a.issue-link")
    try:
        await rows.first.wait_for(state="visible", timeout=15000)
    except Exception:
        pass

    async def matches():
        found = []
        site = re.compile(rf"(?:^|\[){re.escape(col.site_code)}(?:\]|\s)", re.IGNORECASE)
        for index, text in enumerate(await rows.all_inner_texts()):
            if site.search(text) and _has_exact_slug(text, col.url_title):
                found.append(rows.nth(index))
        return found

    found = await matches()
    if not found:
        next_page = page.locator('a[data-page="2"]')
        try:
            has_next = await next_page.is_visible()
        except Exception:
            has_next = False
        if has_next:
            await next_page.click()
            await page.wait_for_load_state("networkidle")
            found = await matches()

    return found


async def _fallback_slug_search(page, col):
    """
    Combined site_code+slug search sometimes fails to find a real match - e.g. a short/common
    site_code like "no" trips up Jira's text search. Fallback: search by url_title (slug) alone,
    then Ctrl+F-equivalent for the site code (bare word, or "[site_code]") across up to 2 pages.
    """
    search_box = page.locator("#quickSearchInput")
    await search_box.fill(col.url_title)
    await search_box.press("Enter")
    await page.wait_for_load_state("networkidle")

    return await _find_ticket_link(page, col)


def _has_exact_slug(text, slug):
    """The slug must not be a prefix/suffix of a different URL."""
    return bool(re.search(rf"(?<![A-Za-z0-9_-]){re.escape(slug)}(?![A-Za-z0-9_-])", text))


async def _exact_slug_rows(rows, col):
    """Narrow broad Jira text-search results to the exact URL slug."""
    exact = []
    for i in range(await rows.count()):
        row = rows.nth(i)
        if _has_exact_slug(await row.inner_text(), col.url_title):
            exact.append(row)
    return exact


async def process_column(page, col, transition_lock, status=lambda _: None):
    """
    col: TranslationColumn (sheet_name, col_idx, site_code, url_title, editor_url)
    Returns: "done" | "not_found" | "ambiguous"
    Raises on unexpected page state (steps 5/7 per spec - stop, don't guess).
    """
    await ensure_logged_in(page)
    await dismiss_jira_notice(page)
    status("searching Jira")
    tickets = page.get_by_role("link", name="tickets Assigned to Me")
    tickets_url = await tickets.get_attribute("href")
    if not tickets_url:
        raise RuntimeError("Jira ticket navigation has no URL.")
    await page.goto(urljoin(page.url, tickets_url), wait_until="domcontentloaded")
    search_box = page.get_by_role("textbox", name="Contains text")
    await search_box.fill(f"{col.site_code} {col.url_title}")
    await search_box.press("Enter")
    await page.wait_for_load_state("networkidle")

    tickets = await _find_ticket_link(page, col)

    if not tickets:
        # combined search found nothing - fall back to slug-only search + manual-style scan
        tickets = await _fallback_slug_search(page, col)

    if not tickets:
        return "not_found"
    if len(tickets) != 1:
        return "ambiguous"
    ticket = tickets[0]

    issue_url = await ticket.get_attribute("href")
    if not issue_url:
        raise RuntimeError("Jira search result has no issue URL.")
    async with transition_lock:
        await page.goto(urljoin(page.url, issue_url), wait_until="domcontentloaded")

        # A previous attempt may have completed after its browser timed out.
        if await _status_is_live(page):
            status("already live")
            return "done"

        state = await _workflow_state(page)
        if state == "NEW REQUEST":
            status("starting AEM workflow")
            # Step 6: New Request -> Start AEM Workflow -> confirm
            await _click_or_report(page, page.get_by_role("button", name="New Request"), "New Request button", col)
            await _click_or_report(
                page, page.get_by_role("menuitem").filter(has_text="Start AEM Workflow"),
                "Start AEM Workflow menu item", col,
            )
            await _submit_and_wait_close(
                page,
                page.get_by_role("button", name="Start AEM Workflow", exact=True),
                page.get_by_role("heading", name="Start AEM Workflow"),
                "Start AEM Workflow confirm button", col,
            )
        elif state != "PRODUCTION":
            raise RuntimeError(f"Unexpected Jira workflow state: {state or 'not loaded'}")

        # Step 7: PRODUCTION -> Go To Live -> confirm
        status("sending to live")
        await _click_or_report(page, _production_dropdown(page), "PRODUCTION dropdown", col)
        await _click_or_report(
            page, page.get_by_role("menuitem").filter(has_text="Go To Live"),
            "Go To Live menu item", col,
        )
        await _submit_and_wait_close(
            page,
            page.get_by_role("button", name="Go To Live", exact=True),
            page.get_by_role("heading", name="Go To Live"),
            "Go To Live confirm button", col,
            success_check=lambda: _status_is_live(page),
        )

    return "done"
