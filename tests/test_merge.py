"""
Step 4: Tests for merge() deduplication and sort logic.
Uses only synthetic events — no mocks, no IO.
"""

import unittest

from scraper import merge
from tests.fixtures import make_event


class TestMergeSort(unittest.TestCase):

    def test_single_list_sorted_by_start(self):
        later = make_event("Event B", days_offset=10)
        earlier = make_event("Event A", days_offset=0)
        result = merge([[later, earlier]])
        self.assertEqual(result[0].title, "Event A")
        self.assertEqual(result[1].title, "Event B")

    def test_multiple_lists_merged_and_sorted(self):
        ev1 = make_event("Rugby Match", days_offset=5)
        ev2 = make_event("Football Match", days_offset=2)
        ev3 = make_event("Concert", days_offset=8)
        result = merge([[ev1], [ev2], [ev3]])
        starts = [e.start for e in result]
        self.assertEqual(starts, sorted(starts))

    def test_empty_lists_handled(self):
        result = merge([[], []])
        self.assertEqual(result, [])

    def test_single_event_returned(self):
        ev = make_event("Solo Event")
        result = merge([[ev]])
        self.assertEqual(len(result), 1)


class TestMergeDedup(unittest.TestCase):

    def test_exact_uid_duplicate_removed(self):
        ev1 = make_event("Bristol Bears vs Saracens", uid="uid-bears-saracens")
        ev2 = make_event("Bristol Bears vs Saracens", uid="uid-bears-saracens")
        result = merge([[ev1], [ev2]])
        self.assertEqual(len(result), 1)

    def test_first_seen_wins_on_uid_dedup(self):
        ev1 = make_event("Event First", uid="shared-uid", location="Location A")
        ev2 = make_event("Event Second", uid="shared-uid", location="Location B")
        result = merge([[ev1], [ev2]])
        self.assertEqual(result[0].location, "Location A")

    def test_fuzzy_same_title_same_day_deduped(self):
        # Two events with the same title on the same day — different UIDs
        ev1 = make_event("Bristol City vs Stoke City", days_offset=0)
        ev2 = make_event("Bristol City vs Stoke City", days_offset=0)
        # Force different UIDs
        from dataclasses import replace
        ev2 = replace(ev2, uid="different-uid")
        result = merge([[ev1], [ev2]])
        self.assertEqual(len(result), 1)

    def test_same_title_different_day_both_kept(self):
        ev1 = make_event("Bristol Bears vs Bath", days_offset=0)
        ev2 = make_event("Bristol Bears vs Bath", days_offset=30)
        from dataclasses import replace
        ev2 = replace(ev2, uid="different-uid-2")
        result = merge([[ev1], [ev2]])
        self.assertEqual(len(result), 2)

    def test_different_sports_same_day_both_kept(self):
        # Rugby and football on same day must NOT be merged
        rugby = make_event("Bristol Bears vs Saracens", days_offset=0,
                           categories=["Rugby"])
        football = make_event("Bristol City vs Stoke City", days_offset=0,
                              categories=["Football"])
        result = merge([[rugby], [football]])
        self.assertEqual(len(result), 2)

    def test_different_teams_entirely_same_day_both_kept(self):
        # Teams with no overlapping words: rugby vs football on the same day
        rugby = make_event("Bristol Bears vs Bath Rugby", days_offset=0,
                           categories=["Rugby"])
        football = make_event("Bristol City vs Stoke City", days_offset=0,
                              categories=["Football"])
        result = merge([[rugby], [football]])
        self.assertEqual(len(result), 2)


class TestMergePhantomFilter(unittest.TestCase):

    def test_phantom_month_year_title_filtered(self):
        phantom = make_event("June 2099")
        real = make_event("Bristol Bears vs Bath Rugby", days_offset=1)
        result = merge([[phantom, real]])
        titles = [e.title for e in result]
        self.assertNotIn("June 2099", titles)
        self.assertIn("Bristol Bears vs Bath Rugby", titles)

    def test_phantom_with_ashton_gate_prefix_filtered(self):
        phantom = make_event("[Ashton Gate] July 2099")
        result = merge([[phantom]])
        self.assertEqual(len(result), 0)

    def test_non_phantom_title_kept(self):
        real = make_event("Bristol Tattoo Convention 2099")
        result = merge([[real]])
        self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()
