import argparse
import asyncio
import datetime
import json
import sys
from openpyxl.utils import column_index_from_string
from browser_owner import request as browser_request
from sheet_io import load_workbook, find_columns, find_pending_columns, write_live_url
from live_check import transform_editor_url


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--workbook", required=True, help="Excel workbook to publish")
    p.add_argument("--sheet", help="only process this sheet name (test mode)")
    p.add_argument("--col", help="only process this column letter, e.g. AR (test mode)")
    p.add_argument("--start-sheet", help="resume run starting at this sheet")
    p.add_argument("--start-col", help="resume run starting at this column letter (needs --start-sheet)")
    p.add_argument("--workers", type=int, default=10, help="parallel Jira pages (1-15, default: 10)")
    p.add_argument("--skip-country", action="append", default=[], help="country code to exclude; repeat or separate with commas")
    p.add_argument(
        "--validate-only", action="store_true",
        help="skip Jira entirely - just re-check the live URL for pending columns and write back if live",
    )
    p.add_argument("--validate-all", action="store_true", help="skip Jira and check every locale URL, including columns already marked live")
    return p.parse_args()


class LiveMonitor:
    """Emit progress for the web hub; the timestamped file remains the full log."""

    def __init__(self, workers, log_file):
        self.workers = workers
        self.log_file = log_file
        self.slots = ["idle"] * workers
        self.events = []
    def start(self): pass
    def stop(self): pass

    def ui(self, event, **values):
        print("UI " + json.dumps({"kind": "publish", "event": event, **values}), flush=True)

    def begin(self, pending, mode, skipped=()):
        self.ui("start", mode=mode, total=len(pending), locales=[col.site_code for col in pending], skipped=[col.site_code for col in skipped])

    def claim(self, col):
        slot = self.slots.index("idle")
        self.slots[slot] = f"{col.site_code}: starting"
        self.ui("worker", slot=slot + 1, site=col.site_code, status="starting")
        return slot

    def release(self, slot):
        self.slots[slot] = "idle"
        self.ui("worker", slot=slot + 1, status="idle")

    def status(self, slot, message):
        self.slots[slot] = message
        site, _, status = message.partition(": ")
        self.ui("worker", slot=slot + 1, site=site, status=status)
        self.ui("locale", site=site, status=status)

    def log(self, message):
        line = f"{datetime.datetime.now().strftime('%H:%M:%S')} {message}"
        self.log_file.write(line + "\n")
        self.events.append(line.replace("\n", " "))
        print(line, flush=True)


def make_logger(workers):
    log_path = f"run_log_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    log_file = open(log_path, "a", buffering=1)  # line-buffered, survives Ctrl+C
    monitor = LiveMonitor(workers, log_file)
    monitor.start()
    monitor.log(f"Logging this run to {log_path}")
    return monitor, log_file


def apply_start_from(pending, wb, start_sheet, start_col_letter):
    sheet_order = wb.sheetnames
    start_sheet_idx = sheet_order.index(start_sheet)  # raises if sheet name is wrong - fail loud
    start_col_idx = column_index_from_string(start_col_letter.upper())

    def keep(c):
        sheet_idx = sheet_order.index(c.sheet_name)
        if sheet_idx > start_sheet_idx:
            return True
        if sheet_idx == start_sheet_idx:
            return c.col_idx >= start_col_idx
        return False

    return [c for c in pending if keep(c)]


def skipped_countries(values):
    return {code.strip().casefold() for value in values for code in value.split(",") if code.strip()}


async def _validate_one(col, semaphore, monitor, wb, log):
    live_url = transform_editor_url(col.editor_url)
    async with semaphore:
        slot = monitor.claim(col)
        try:
            monitor.status(slot, f"{col.site_code}: checking live")
            if await asyncio.to_thread(browser_request, "live", url=live_url):
                write_live_url(wb, FILE_PATH, col.sheet_name, col.col_idx, live_url)
                monitor.status(slot, f"{col.site_code}: live")
                log(f"[{col.sheet_name}] col {col.col_idx} ({col.site_code}): live: {live_url}")
                return None
            monitor.status(slot, f"{col.site_code}: not live")
            log(f"[{col.sheet_name}] col {col.col_idx} ({col.site_code}): not yet live: {live_url}")
            return col, live_url
        finally:
            monitor.release(slot)


async def run_validate_only(pending, wb, log, workers, monitor):
    """Check locale URLs in tabs of the shared Firefox session."""
    semaphore = asyncio.Semaphore(workers)
    results = await asyncio.gather(*(_validate_one(col, semaphore, monitor, wb, log) for col in pending))
    still_not_live = [result for result in results if result]
    log("\n--- Validation Report ---")
    log(f"Still not live ({len(still_not_live)}): {[f'{c.sheet_name}/{c.site_code}' for c, _ in still_not_live]}")


async def run_publish(pending, wb, log, workers, monitor):
    not_found, ambiguous, errored = [], [], []
    semaphore = asyncio.Semaphore(workers)
    results = await asyncio.gather(*(_publish_in_shared_firefox(col, semaphore, monitor, wb) for col in pending))
    still_not_live = []
    for col, result, error, live_check in results:
        prefix = f"[{col.sheet_name}] col {col.col_idx}: {col.url_title} ({col.site_code})"
        if error:
            log(f"{prefix}\n  [ERROR] {error}")
            errored.append((col, error))
        elif result == "not_found":
            log(f"{prefix}\n  not found")
            not_found.append(col)
        elif result == "ambiguous":
            log(f"{prefix}\n  ambiguous")
            ambiguous.append(col)
        elif live_check and not live_check[2]:
            still_not_live.append(live_check[:2])

    log("\n--- Report ---")
    log(f"Not found ({len(not_found)}): {[c.url_title for c in not_found]}")
    log(f"Ambiguous ({len(ambiguous)}): {[c.url_title for c in ambiguous]}")
    log(f"Still not live ({len(still_not_live)}): {[f'{c.sheet_name}/{c.site_code}' for c, _ in still_not_live]}")
    log(f"Errored ({len(errored)}):")
    for c, err in errored:
        log(f"  {c.url_title} ({c.site_code}): {err}")
    not_confirmed = [*not_found, *ambiguous, *(c for c, _ in still_not_live), *(c for c, _ in errored)]
    log(f"Not confirmed live ({len(not_confirmed)}): {[f'{c.sheet_name}/{c.site_code}' for c in not_confirmed]}")


async def _publish_in_shared_firefox(col, semaphore, monitor, wb):
    async with semaphore:
        slot = monitor.claim(col)
        try:
            monitor.status(slot, f"{col.site_code}: opening Jira")
            result = await asyncio.to_thread(browser_request, "publish", siteCode=col.site_code, slug=col.url_title)
            monitor.status(slot, f"{col.site_code}: {result}")
            live_check = await _check_live(col, monitor, wb, slot) if result == "done" else None
            return col, result, None, live_check
        except Exception as error:
            monitor.status(slot, f"{col.site_code}: error")
            monitor.log(f"[{col.site_code}] [ERROR] {error}")
            return col, None, str(error), None
        finally:
            monitor.release(slot)


async def _wait_for_live_in_shared_firefox(col, semaphore, monitor, wb):
    async with semaphore:
        slot = monitor.claim(col)
        try: return await _check_live(col, monitor, wb, slot)
        finally: monitor.release(slot)


async def _check_live(col, monitor, wb, slot):
    live_url = transform_editor_url(col.editor_url)
    for attempt in range(4):
        monitor.status(slot, f"{col.site_code}: checking live ({attempt + 1}/4)")
        if await asyncio.to_thread(browser_request, "live", url=live_url):
            write_live_url(wb, FILE_PATH, col.sheet_name, col.col_idx, live_url)
            monitor.status(slot, f"{col.site_code}: live")
            monitor.log(f"[{col.sheet_name}] col {col.col_idx} ({col.site_code}): verified live: {live_url}")
            return col, live_url, True
        if attempt < 3: await asyncio.sleep(15)
    monitor.status(slot, f"{col.site_code}: not live")
    return col, live_url, False


def main():
    args = parse_args()
    global FILE_PATH
    FILE_PATH = args.workbook
    if not 1 <= args.workers <= 15:
        raise SystemExit("--workers must be between 1 and 15")
    monitor, log_file = make_logger(args.workers)
    log = monitor.log
    try:
        wb = load_workbook(FILE_PATH)
        pending = find_columns(wb, pending_only=not args.validate_all)
        if args.sheet:
            pending = [c for c in pending if c.sheet_name == args.sheet]
        if args.col:
            col_idx = column_index_from_string(args.col.upper())
            pending = [c for c in pending if c.col_idx == col_idx]
        if args.start_sheet:
            pending = apply_start_from(pending, wb, args.start_sheet, args.start_col)
        skipped = skipped_countries(args.skip_country)
        skipped_columns = [c for c in pending if c.site_code.casefold() in skipped]
        if skipped:
            pending = [c for c in pending if c.site_code.casefold() not in skipped]
            log(f"Skipping country code(s): {', '.join(sorted(skipped))}")
        log(f"{len(pending)} pending column(s) found across {len(wb.sheetnames)} sheet(s)")
        monitor.begin(pending, "validate-all" if args.validate_all else "validate", skipped_columns)
        if args.validate_only or args.validate_all:
            asyncio.run(run_validate_only(pending, wb, log, args.workers, monitor))
        else:
            asyncio.run(run_publish(pending, wb, log, args.workers, monitor))
    finally:
        monitor.stop()
        log_file.close()


if __name__ == "__main__":
    main()
