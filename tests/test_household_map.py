"""Unit tests for household_map validation (no Overpass calls)."""

import unittest

from app.household_map import validate_search_params


class TestValidateSearchParams(unittest.TestCase):
    def test_valid_params(self):
        params, errors = validate_search_params(52.9, 6.65, 500)
        self.assertFalse(errors)
        self.assertEqual(params["lat"], 52.9)
        self.assertEqual(params["lon"], 6.65)
        self.assertEqual(params["radius"], 500)

    def test_lat_out_of_range(self):
        params, errors = validate_search_params(100, 6.65, 500)
        self.assertIn("lat", errors)

    def test_radius_min(self):
        params, errors = validate_search_params(52.9, 6.65, 0)
        self.assertIn("radius", errors)

    def test_radius_max_accepted(self):
        """Backend accepts up to 100000; HTML has max=10000."""
        params, errors = validate_search_params(52.9, 6.65, 100000)
        self.assertFalse(errors)
        self.assertEqual(params["radius"], 100000)

    def test_radius_over_max_rejected(self):
        params, errors = validate_search_params(52.9, 6.65, 100001)
        self.assertIn("radius", errors)
