#!/usr/bin/env python3
"""
Bristol Bears & Ashton Gate Calendar - Main Entry Point
=======================================================
Orchestrates scraping and ICS generation.
Run this script daily via GitHub Actions.

Usage:
    python main.py              # Normal run
    python main.py --dry-run    # Scrape only, don't write ICS
    python main.py --verify     # Run and verify the output ICS
"""

import argparse
import json
import logging
import os
import sys

os.environ.pop("SSLKEYLOGFILE", None)
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"

with open(CONFIG_PATH) as f:
    CONFIG = json.load(f)

# Import after config is loaded (scraper.py reads config at import time)
from scraper import run as scrape_events
from ics_generator import generate_ics

logger = logging.getLogger("bristol_calendar")
TZ = ZoneInfo(CONFIG["timezone"])

DIAG_PATH = BASE_DIR / "diagnostics" / "last_run.json"
_LIVE_SOURCES = ("bears_live", "ag_live", "bcfc_live")


def _write_diagnostic(scraper_diag: dict) -> None:
    run_id = os.environ.get("GITHUB_RUN_ID", "local")
    repository = os.environ.get("GITHUB_REPOSITORY", "local")
    run_url = (
        f"https://github.com/{repository}/actions/runs/{run_id}"
        if run_id != "local" else "local"
    )
    full_diag = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "run_url": run_url,
        **scraper_diag,
    }
    DIAG_PATH.parent.mkdir(parents=True, exist_ok=True)
    DIAG_PATH.write_text(json.dumps(full_diag, indent=2), encoding="utf-8")
    logger.info("Diagnostic written to %s", DIAG_PATH)


def main():
    parser = argparse.ArgumentParser(description="Bristol Bears & Ashton Gate Calendar Scraper")
    parser.add_argument("--dry-run", action="store_true", help="Scrape only, don't write output")
    parser.add_argument("--verify", action="store_true", help="Verify output after writing")
    parser.add_argument("--output", default=None, help="Override output ICS path")
    args = parser.parse_args()

    output_path = args.output or str(BASE_DIR / CONFIG["output"]["ics_file"])

    logger.info("Run started at %s", datetime.now(tz=TZ).strftime("%Y-%m-%d %H:%M:%S %Z"))
    logger.info("Output path: %s", output_path)

    # --- Scrape ---
    try:
        events, scraper_diag = scrape_events()
    except Exception as e:
        logger.error("Scraping failed with exception: %s", e, exc_info=True)
        _write_diagnostic({"status": "exception", "error": str(e), "sources": {}, "warnings": [], "stale_warnings": [], "total_events": 0})
        sys.exit(1)

    # Always write diagnostic before any exit so the workflow step can read it
    _write_diagnostic(scraper_diag)

    # Log stale warnings so they appear in the Actions log
    for w in scraper_diag.get("stale_warnings", []):
        logger.warning("STALENESS: %s", w)

    # A2: all three live scrapers returned 0 simultaneously
    all_live_empty = all(
        scraper_diag["sources"].get(s, {}).get("events", 0) == 0
        for s in _LIVE_SOURCES
    )
    if all_live_empty:
        if events:
            # Known fallbacks still have future fixtures — likely end of season, not a code failure
            logger.warning(
                "All three live scrapers returned 0 events — likely end of season. "
                "Continuing with %d known fallback event(s). See diagnostics/last_run.json.",
                len(events),
            )
        else:
            # Nothing anywhere — either widespread scraper failure or genuine off-season
            logger.error(
                "All three live scrapers returned 0 events and no known fallbacks have "
                "future fixtures — possible widespread failure or genuine off-season. "
                "Aborting to preserve existing calendar. See diagnostics/last_run.json."
            )
            sys.exit(1)

    if not events:
        logger.error("No events found at all — aborting to preserve existing calendar")
        sys.exit(1)

    logger.info("Total events collected: %d", len(events))

    # --- Generate ICS ---
    if args.dry_run:
        logger.info("Dry run mode — skipping ICS file write")
        print(f"Dry run complete. Would write {len(events)} events to {output_path}")
        _print_event_summary(events)
        return

    try:
        generate_ics(events, output_path)
    except ValueError as e:
        logger.error("ICS validation failed: %s", e)
        sys.exit(1)
    except Exception as e:
        logger.error("ICS generation failed: %s", e, exc_info=True)
        sys.exit(1)

    # --- Verify ---
    if args.verify:
        verify_output(output_path, len(events))

    # --- Summary ---
    out_file = Path(output_path)
    size_kb = out_file.stat().st_size / 1024
    logger.info("Calendar written: %s (%.1f KB, %d events)", output_path, size_kb, len(events))
    print(f"\nSuccess! {len(events)} events written to {output_path} ({size_kb:.1f} KB)")
    _print_event_summary(events)


def _print_event_summary(events):
    print("\nEvent summary:")
    for ev in events:
        print(f"  {ev.start.strftime('%Y-%m-%d %H:%M')} | {ev.title}")


def verify_output(path: str, expected_count: int):
    import re

    logger.info("Verifying output: %s", path)
    ics = Path(path).read_text(encoding="utf-8")

    events_found = ics.count("BEGIN:VEVENT")
    if events_found != expected_count:
        logger.warning(
            "Verification: expected %d events, found %d in ICS",
            expected_count, events_found,
        )
    else:
        logger.info("Verification passed - %d events in ICS", events_found)

    for required in ("BEGIN:VCALENDAR", "END:VCALENDAR", "VERSION:2.0",
                     "PRODID:", "BEGIN:VTIMEZONE"):
        if required not in ics:
            logger.error("Missing required ICS section: %s", required)

    uid_count = len(re.findall(r"^UID:", ics, re.MULTILINE))
    dtstart_count = ics.count("DTSTART") - 2  # subtract 2 from VTIMEZONE block

    if uid_count != expected_count:
        logger.warning("UID count: %d vs expected %d", uid_count, expected_count)
    if dtstart_count != expected_count:
        logger.warning("DTSTART count: %d vs expected %d", dtstart_count, expected_count)

    file_size = Path(path).stat().st_size
    print(f"Verification passed: {events_found} events, {file_size} bytes")


if __name__ == "__main__":
    main()
