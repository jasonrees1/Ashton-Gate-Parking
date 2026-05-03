"""
Tests for A2 safety-check logic in main.py.

A2 should abort (exit 1) only when ALL live scrapers return 0 AND there are
no known-fallback events — i.e. the calendar would be genuinely empty.
It must NOT abort when live scrapers are empty but known fallbacks still have
future fixtures (end-of-season scenario).
"""

import copy
import sys
import unittest
from unittest.mock import patch

from tests.fixtures import make_event

# Diagnostic skeleton where every source reports 0 events
_ALL_ZERO_SOURCES = {
    "bears_live": {"events": 0, "http_status": 200},
    "ag_live":    {"events": 0, "http_status": 200},
    "bcfc_live":  {"events": 0},
    "bears_known": {"events": 0},
    "ag_known":    {"events": 0},
    "bcfc_known":  {"events": 0},
}


def _make_diag(sources=None, status="failed", total=0):
    return {
        "sources": sources if sources is not None else copy.deepcopy(_ALL_ZERO_SOURCES),
        "warnings": [],
        "stale_warnings": [],
        "status": status,
        "total_events": total,
    }


def _run_main_dry(events, diag):
    """Invoke main() in --dry-run mode with scrape_events and _write_diagnostic mocked."""
    with patch.object(sys, "argv", ["main.py", "--dry-run"]), \
         patch("main.scrape_events", return_value=(events, diag)), \
         patch("main._write_diagnostic"):
        import main as m
        m.main()


class TestA2AllEmptyAborts(unittest.TestCase):
    """When every source (live + known) returns 0 events, main must exit with code 1."""

    def test_exits_with_code_1(self):
        with self.assertRaises(SystemExit) as ctx:
            _run_main_dry([], _make_diag())
        self.assertEqual(ctx.exception.code, 1)


class TestA2LiveEmptyFallbacksPresent(unittest.TestCase):
    """When live scrapers are all empty but known fallbacks have future events,
    main must NOT abort — it should continue and publish the fallback events."""

    def test_does_not_exit(self):
        sources = copy.deepcopy(_ALL_ZERO_SOURCES)
        sources["bears_known"]["events"] = 2
        events = [
            make_event("Bristol Bears vs Saracens"),
            make_event("Bristol Bears vs Bath Rugby", days_offset=20),
        ]
        # assertRaises would catch a SystemExit; if none is raised the test passes
        _run_main_dry(events, _make_diag(sources=sources, status="degraded", total=2))


class TestA2LiveSourceActive(unittest.TestCase):
    """When at least one live scraper returns events, A2 must not fire at all."""

    def test_does_not_exit_when_bcfc_live_active(self):
        sources = copy.deepcopy(_ALL_ZERO_SOURCES)
        sources["bcfc_live"]["events"] = 1
        events = [make_event("Bristol City vs Stoke City")]
        _run_main_dry(events, _make_diag(sources=sources, status="degraded", total=1))

    def test_does_not_exit_when_all_live_active(self):
        sources = {k: {"events": 1} for k in _ALL_ZERO_SOURCES}
        events = [
            make_event("Bristol Bears vs Saracens"),
            make_event("Bristol City vs Stoke City", days_offset=7),
            make_event("Bristol Tattoo Convention", days_offset=14),
        ]
        _run_main_dry(events, _make_diag(sources=sources, status="ok", total=3))


if __name__ == "__main__":
    unittest.main()
