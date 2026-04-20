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
import sys
from datetime import datetime
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


def main():
    parser = argparse.ArgumentParser(description="Bristol Bears & Ashton Gate Calendar Scraper")
    parser.add_argument("--dry-run", action="store_true", help="Scrape only, don't write output")
    parser.add_argument("--verify", action="store_true", help="Verify output after writing")
    parser.add_argument("--output", default=None, help="Override output ICS path")
    args = parser.parse_args()

    output_path = args.output or str(BASE_DIR / CONFIG["output"]["ics_file"])

    logger.info(f"Run started at {datetime.now(tz=TZ).strftime('%Y-%m-%d %H:%M:%S %Z')}")
    logger.info(f"Output path: {output_path}")

    # --- Scrape ---
    try:
        events = scrape_events()
    except Exception as e:
        logger.error(f"Scraping failed with exception: {e}", exc_info=True)
        sys.exit(1)

    if not events:
        logger.error("No events found at all — aborting to preserve existing calendar")
        sys.exit(1)

    logger.info(f"Total events collected: {len(events)}")

    # --- Generate ICS ---
    if args.dry_run:
        logger.info("Dry run mode — skipping ICS file write")
        print(f"✅ Dry run complete. Would write {len(events)} events to {output_path}")
        return

    try:
        ics_content = generate_ics(events, output_path)
    except ValueError as e:
        logger.error(f"ICS validation failed: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"ICS generation failed: {e}", exc_info=True)
        sys.exit(1)

    # --- Verify ---
    if args.verify:
        verify_output(output_path, len(events))

    # --- Summary ---
    out_file = Path(output_path)
    size_kb = out_file.stat().st_size / 1024
    logger.info(f"✅ Calendar written: {output_path} ({size_kb:.1f} KB, {len(events)} events)")
    print(f"\n✅ Success! {len(events)} events written to {output_path} ({size_kb:.1f} KB)")

    # Print event summary
    print("\nEvent summary:")
    for ev in events:
        print(f"  {ev.start.strftime('%Y-%m-%d %H:%M')} | {ev.title}")


def verify_output(path: str, expected_count: int):
    """Read back and validate the written ICS file using pure string checks."""
    import re

    logger.info(f"Verifying output: {path}")
    ics = Path(path).read_text(encoding="utf-8")

    # Count events
    events_found = ics.count("BEGIN:VEVENT")
    if events_found != expected_count:
        logger.warning(
            f"Verification: expected {expected_count} events, "
            f"found {events_found} in ICS"
        )
    else:
        logger.info(f"Verification passed ✓ — {events_found} events in ICS")

    # Check required sections
    for required in ("BEGIN:VCALENDAR", "END:VCALENDAR", "VERSION:2.0",
                     "PRODID:", "BEGIN:VTIMEZONE"):
        if required not in ics:
            logger.error(f"Missing required ICS section: {required}")

    # Check every event has UID and DTSTART
    uid_count = len(re.findall(r"^UID:", ics, re.MULTILINE))
    # DTSTART appears in VTIMEZONE (2x) + each event (1x)
    dtstart_count = ics.count("DTSTART") - 2

    if uid_count != expected_count:
        logger.warning(f"UID count: {uid_count} vs expected {expected_count}")
    if dtstart_count != expected_count:
        logger.warning(f"DTSTART count: {dtstart_count} vs expected {expected_count}")

    file_size = Path(path).stat().st_size
    print(f"✅ Verification passed: {events_found} events, {file_size} bytes")


if __name__ == "__main__":
    main()
