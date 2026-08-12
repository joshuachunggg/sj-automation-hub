def transform_editor_url(editor_url):
    """
    https://p6spp-ap-author.samsung.com/editor.html/content/samsung/sg/support/...
      -> samsung.com/sg/support/...
    TBD: confirm exact rule with user during testing.
    """
    marker = "/content/samsung"
    idx = editor_url.find(marker)
    if idx == -1:
        raise ValueError(f"'{marker}' not found in editor URL: {editor_url}")
    rest = editor_url[idx + len(marker):]  # e.g. "/sg/support/..."
    return "samsung.com" + rest


def check_live(browser_context, url, timeout=15000):
    """Public page, no auth. True if it loads with a 200."""
    page = browser_context.new_page()
    try:
        target = url if url.startswith("http") else f"https://{url}"
        resp = page.goto(target, timeout=timeout)
        ok = resp is not None and resp.status == 200
    except Exception:
        ok = False
    finally:
        page.close()
    return ok


async def check_live_async(browser_context, url, timeout=15000):
    page = await browser_context.new_page()
    try:
        target = url if url.startswith("http") else f"https://{url}"
        resp = await page.goto(target, timeout=timeout)
        return resp is not None and resp.status == 200
    except Exception:
        return False
    finally:
        await page.close()

