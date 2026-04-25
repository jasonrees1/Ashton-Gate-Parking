"""
Step 3: Tests for is_major_event().
Pure logic — no mocks, no IO.
"""

import unittest

from scraper import is_major_event


class TestIsMajorEvent(unittest.TestCase):

    # ── Events that MUST be included ───────────────────────────────────────

    def test_rugby_is_major(self):
        self.assertTrue(is_major_event("Bristol Bears vs Bath Rugby"))

    def test_football_is_major(self):
        self.assertTrue(is_major_event("Bristol City vs Stoke City Football"))

    def test_concert_is_major(self):
        self.assertTrue(is_major_event("Coldplay Live in Concert"))

    def test_festival_is_major(self):
        self.assertTrue(is_major_event("Bristol Summer Festival 2099"))

    def test_convention_is_major(self):
        self.assertTrue(is_major_event("Bristol Tattoo Convention 2099"))

    def test_international_sport_is_major(self):
        self.assertTrue(is_major_event("Red Roses vs Wales - Womens Six Nations"))

    def test_marathon_is_major(self):
        self.assertTrue(is_major_event("Bristol Half Marathon 2099"))

    def test_cycle_event_is_major(self):
        self.assertTrue(is_major_event("Break The Cycle Charity Ride"))

    def test_boxing_is_major(self):
        self.assertTrue(is_major_event("Championship Boxing Night"))

    def test_graduation_is_major(self):
        self.assertTrue(is_major_event("University of Bristol Graduation Ceremony"))

    # ── Events that MUST be excluded ───────────────────────────────────────

    def test_conference_is_minor(self):
        self.assertFalse(is_major_event("Digital Tech Conference 2099"))

    def test_seminar_is_minor(self):
        self.assertFalse(is_major_event("Business Networking Seminar"))

    def test_training_is_minor(self):
        self.assertFalse(is_major_event("Leadership Training Day"))

    def test_workshop_is_minor(self):
        self.assertFalse(is_major_event("Creative Writing Workshop"))

    def test_awards_dinner_is_minor(self):
        self.assertFalse(is_major_event("Corporate Awards Gala Dinner"))

    def test_card_market_is_minor(self):
        self.assertFalse(is_major_event("Collectors Card Market"))

    def test_apprenticeship_is_minor(self):
        self.assertFalse(is_major_event("National Apprenticeship Event"))

    # ── Minor keyword overrides major keyword ──────────────────────────────

    def test_minor_overrides_major(self):
        # "rugby" is major, "conference" is minor — minor wins
        self.assertFalse(is_major_event("Rugby Conference and Seminar Day"))

    def test_show_with_guitar_excluded(self):
        # "guitar show" is a minor-keyword phrase
        self.assertFalse(is_major_event("Bristol Guitar Show 2099"))

    # ── Unknown events ─────────────────────────────────────────────────────

    def test_unknown_event_is_not_major(self):
        self.assertFalse(is_major_event("Some Random Thing"))

    def test_empty_title_is_not_major(self):
        self.assertFalse(is_major_event(""))

    # ── Case insensitivity ─────────────────────────────────────────────────

    def test_case_insensitive_major(self):
        self.assertTrue(is_major_event("BRISTOL RUGBY MATCH"))

    def test_case_insensitive_minor(self):
        self.assertFalse(is_major_event("DIGITAL SEMINAR"))


if __name__ == "__main__":
    unittest.main()
