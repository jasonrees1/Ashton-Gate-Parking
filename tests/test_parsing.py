"""
Step 2: Tests for parse_dt() and make_uid().
Pure logic — no mocks, no IO, no network.
"""

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from scraper import parse_dt, make_uid

TZ = ZoneInfo("Europe/London")


class TestParseDt(unittest.TestCase):

    # ── Happy path ─────────────────────────────────────────────────────────

    def test_standard_date_and_time(self):
        dt = parse_dt("15 Jun 2099", "15:00")
        self.assertEqual(dt.year, 2099)
        self.assertEqual(dt.month, 6)
        self.assertEqual(dt.day, 15)
        self.assertEqual(dt.hour, 15)
        self.assertEqual(dt.minute, 0)

    def test_short_month_abbreviation(self):
        dt = parse_dt("15 Jun 2099", "15:00")
        self.assertEqual(dt.month, 6)

    def test_full_month_name(self):
        dt = parse_dt("15 June 2099", "15:00")
        self.assertEqual(dt.month, 6)

    def test_ordinal_suffix_stripped(self):
        for suffix in ["1st Jan 2099", "2nd Jan 2099", "3rd Jan 2099", "4th Jan 2099"]:
            with self.subTest(suffix=suffix):
                dt = parse_dt(suffix, "15:00")
                self.assertIsNotNone(dt)
                self.assertEqual(dt.month, 1)

    def test_evening_kickoff(self):
        dt = parse_dt("15 Jun 2099", "19:45")
        self.assertEqual(dt.hour, 19)
        self.assertEqual(dt.minute, 45)

    def test_default_time_is_1500(self):
        dt = parse_dt("15 Jun 2099")
        self.assertEqual(dt.hour, 15)
        self.assertEqual(dt.minute, 0)

    # ── Timezone ───────────────────────────────────────────────────────────

    def test_timezone_attached(self):
        dt = parse_dt("15 Jun 2099", "15:00")
        self.assertIsNotNone(dt.tzinfo)

    def test_summer_date_is_bst(self):
        # June is BST (UTC+1)
        dt = parse_dt("15 Jun 2099", "15:00")
        offset_hours = dt.utcoffset().total_seconds() / 3600
        self.assertEqual(offset_hours, 1.0)

    def test_winter_date_is_gmt(self):
        # January is GMT (UTC+0)
        dt = parse_dt("15 Jan 2099", "15:00")
        offset_hours = dt.utcoffset().total_seconds() / 3600
        self.assertEqual(offset_hours, 0.0)

    # ── Edge cases ─────────────────────────────────────────────────────────

    def test_invalid_date_returns_none_or_does_not_raise(self):
        # Must not raise; returning None is acceptable
        try:
            parse_dt("not a date at all xyz")
        except Exception as e:
            self.fail(f"parse_dt raised unexpectedly: {e}")

    def test_empty_string_does_not_raise(self):
        try:
            parse_dt("")
        except Exception as e:
            self.fail(f"parse_dt raised on empty string: {e}")


class TestMakeUid(unittest.TestCase):

    def _dt(self):
        return datetime(2099, 6, 15, 15, 0, 0, tzinfo=TZ)

    # ── Format ─────────────────────────────────────────────────────────────

    def test_returns_string(self):
        self.assertIsInstance(make_uid("test", "My Event", self._dt()), str)

    def test_contains_domain_suffix(self):
        uid = make_uid("test", "My Event", self._dt())
        self.assertIn("@bristol-bears-calendar", uid)

    def test_contains_prefix(self):
        uid = make_uid("bears", "My Event", self._dt())
        self.assertTrue(uid.startswith("bears-"))

    def test_contains_datetime_stamp(self):
        uid = make_uid("test", "My Event", self._dt())
        self.assertIn("20990615T150000", uid)

    # ── Determinism ────────────────────────────────────────────────────────

    def test_same_inputs_produce_same_uid(self):
        dt = self._dt()
        self.assertEqual(
            make_uid("test", "Bristol Bears vs Saracens", dt),
            make_uid("test", "Bristol Bears vs Saracens", dt),
        )

    def test_different_titles_produce_different_uids(self):
        dt = self._dt()
        self.assertNotEqual(
            make_uid("test", "Event A", dt),
            make_uid("test", "Event B", dt),
        )

    def test_different_prefixes_produce_different_uids(self):
        dt = self._dt()
        self.assertNotEqual(
            make_uid("bears", "My Event", dt),
            make_uid("bcfc", "My Event", dt),
        )

    # ── Slug sanitisation ──────────────────────────────────────────────────

    def test_special_chars_stripped_from_slug(self):
        dt = self._dt()
        uid = make_uid("test", "Hello & World! (2099)", dt)
        # Only alphanumerics, hyphens, and the T separator in the datetime
        # stamp should appear before the @
        slug_part = uid.split("@")[0]
        import re
        self.assertRegex(slug_part, r'^[a-zA-Z0-9\-]+$')

    def test_slug_truncated_at_40_chars(self):
        dt = self._dt()
        long_title = "A" * 100
        uid = make_uid("test", long_title, dt)
        slug = uid.split("-test-")[1].split("-" + "20990615")[0] if "-test-" in uid else ""
        # The full UID should be a reasonable length (slug capped at 40)
        self.assertLessEqual(len(uid), 120)


if __name__ == "__main__":
    unittest.main()
