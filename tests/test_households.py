"""Unit tests for household search, Overpass retries, and the local snapshot."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

from households.address import build_address_from_tags
from households.build_local import geofabrik_pbf_url, main
from households.cache import CACHE_TTL_SECONDS, local_cache, overpass_cache
from households.config import BUILD_COMMAND
from households.errors import ExternalServiceError, LocalDataError
from households.local_store import add_households, finish_writer, open_writer, query_households
from households.models import Household
from households.overpass import elements_to_households, fetch_households
from households.source import get_households
from households.validation import validate_search_params


def _write_households(path: Path, rows):
    connection = open_writer(path)
    add_households(connection, rows)
    finish_writer(connection)


def _element(housenumber="12", street="Dorpsstraat"):
    return {
        "type": "node",
        "id": 10,
        "lat": 52.9,
        "lon": 6.65,
        "tags": {"addr:housenumber": housenumber, "addr:street": street},
    }


class FakeResponse:
    def __init__(self, status_code, payload=None, headers=None):
        self.status_code = status_code
        self._payload = {"elements": [_element()]} if payload is None else payload
        self.headers = headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Error", response=self)


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

    def test_source_defaults_from_environment(self):
        with patch.dict("os.environ", {"HOUSEHOLD_SOURCE": "local"}):
            params, errors = validate_search_params(52.9, 6.65, 500)
        self.assertFalse(errors)
        self.assertEqual(params["source"], "local")

    def test_source_blank_uses_environment(self):
        with patch.dict("os.environ", {"HOUSEHOLD_SOURCE": "overpass"}):
            params, errors = validate_search_params(52.9, 6.65, 500, "  ")
        self.assertEqual(params["source"], "overpass")

    def test_source_invalid(self):
        params, errors = validate_search_params(52.9, 6.65, 500, "database")
        self.assertIn("source", errors)

    def test_source_explicit(self):
        params, errors = validate_search_params(52.9, 6.65, 500, "Overpass")
        self.assertFalse(errors)
        self.assertEqual(params["source"], "overpass")


class TestAddress(unittest.TestCase):
    def test_parts_include_unit(self):
        text = build_address_from_tags(
            {
                "addr:housenumber": "12",
                "addr:unit": "A",
                "addr:street": "Dorpsstraat",
                "addr:city": "Grolloo",
            },
            "fallback",
        )
        self.assertEqual(text, "12 A, Dorpsstraat, Grolloo")

    def test_full_address_is_preferred(self):
        text = build_address_from_tags(
            {"addr:full": "Dorpsstraat 12, Grolloo", "addr:street": "Other"},
            "fallback",
        )
        self.assertEqual(text, "Dorpsstraat 12, Grolloo")

    def test_fallback_when_tags_are_empty(self):
        self.assertEqual(build_address_from_tags({}, "node/1"), "node/1")


class TestOverpassClient(unittest.TestCase):
    def setUp(self):
        self._original_clock = overpass_cache._clock
        overpass_cache.clear()

    def tearDown(self):
        overpass_cache._clock = self._original_clock
        overpass_cache.clear()

    def test_elements_use_way_center(self):
        households = elements_to_households(
            [
                {
                    "type": "way",
                    "id": 3,
                    "center": {"lat": 1.5, "lon": 2.5},
                    "tags": {"addr:housenumber": "4"},
                },
                {"type": "way", "id": 4, "tags": {"addr:housenumber": "5"}},
            ]
        )
        self.assertEqual(len(households), 1)
        self.assertEqual(households[0].osm_id, "way/3")
        self.assertEqual(households[0].lat, 1.5)
        self.assertEqual(households[0].lon, 2.5)

    def test_posts_query_with_user_agent(self):
        post = MagicMock(return_value=FakeResponse(200))
        with patch("households.overpass.requests.post", post), patch("households.overpass._pause"):
            households = fetch_households(52.9, 6.65, 500)
        self.assertEqual(len(households), 1)
        self.assertEqual(households[0].tags["addr:street"], "Dorpsstraat")
        args, kwargs = post.call_args
        self.assertIn("/api/interpreter", args[0])
        self.assertIn('node["addr:housenumber"]', kwargs["data"]["data"])
        self.assertIn("RadioNoiseModel", kwargs["headers"]["User-Agent"])

    def test_cache_skips_second_request_until_one_hour(self):
        self.assertEqual(CACHE_TTL_SECONDS, 3600)
        clock = {"now": 0.0}
        overpass_cache._clock = lambda: clock["now"]
        post = MagicMock(return_value=FakeResponse(200))
        with patch("households.overpass.requests.post", post), patch("households.overpass._pause"):
            fetch_households(52.9, 6.65, 500)
            clock["now"] = 3599
            fetch_households(52.9, 6.65, 500)
            self.assertEqual(post.call_count, 1)
            clock["now"] = 3600
            fetch_households(52.9, 6.65, 500)
        self.assertEqual(post.call_count, 2)

    def test_retryable_failures_then_success(self):
        failures = [
            FakeResponse(429, headers={"Retry-After": "5"}),
            FakeResponse(502),
            FakeResponse(503),
            FakeResponse(504),
            requests.Timeout("timed out"),
        ]
        for index, failure in enumerate(failures):
            overpass_cache.clear()
            post = MagicMock(side_effect=[failure, FakeResponse(200)])
            with patch("households.overpass.requests.post", post), patch(
                "households.overpass._pause"
            ) as pause:
                households = fetch_households(53.0 + index, 6.0, 400)
            self.assertEqual(post.call_count, 2)
            self.assertEqual(len(households), 1)
            if getattr(failure, "status_code", None) == 429:
                pause.assert_called_with(5.0)
            else:
                pause.assert_called_with(1.0)

    def test_all_mirrors_failing_is_not_cached(self):
        post = MagicMock(return_value=FakeResponse(429))
        with patch("households.overpass.requests.post", post), patch("households.overpass._pause"):
            with self.assertRaises(ExternalServiceError):
                fetch_households(51.0, 5.0, 300)
            self.assertEqual(post.call_count, 9)
            post.return_value = FakeResponse(200)
            households = fetch_households(51.0, 5.0, 300)
        self.assertEqual(len(households), 1)
        self.assertEqual(post.call_count, 10)

    def test_other_http_errors_try_the_next_mirror_once(self):
        post = MagicMock(return_value=FakeResponse(400))
        with patch("households.overpass.requests.post", post), patch(
            "households.overpass._pause"
        ) as pause:
            with self.assertRaises(ExternalServiceError):
                fetch_households(50.0, 4.0, 200)
        self.assertEqual(post.call_count, 3)
        self.assertEqual(pause.call_count, 2)


class TestLocalStore(unittest.TestCase):
    def setUp(self):
        local_cache.clear()

    def tearDown(self):
        local_cache.clear()

    def test_radius_keeps_points_inside_the_circle(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "households.sqlite"
            north_400m = 52.0 + (400.0 / 111_320.0)
            north_900m = 52.0 + (900.0 / 111_320.0)
            east_900m = 6.0 + (900.0 / (111_320.0 * 0.615661475))
            rows = [
                (52.0, 6.0, "node/1", json.dumps({"addr:housenumber": "1"})),
                (north_400m, 6.0, "node/2", json.dumps({"addr:housenumber": "2"})),
                (north_900m, east_900m, "node/3", json.dumps({"addr:housenumber": "3"})),
                (53.0, 6.0, "node/4", json.dumps({"addr:housenumber": "4"})),
            ]
            _write_households(path, rows)
            found = query_households(52.0, 6.0, 1000, path=path)
        osm_ids = {household.osm_id for household in found}
        self.assertEqual(osm_ids, {"node/1", "node/2"})

    def test_missing_file_names_the_build_command(self):
        missing = Path(tempfile.gettempdir()) / "missing-households.sqlite"
        with self.assertRaises(LocalDataError) as caught:
            query_households(52.0, 6.0, 500, path=missing)
        self.assertIn(BUILD_COMMAND, str(caught.exception))

    def test_snapshot_without_rtree_names_the_build_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "households.sqlite"
            connection = sqlite3.connect(path)
            connection.execute(
                """
                CREATE TABLE households (
                    lat REAL NOT NULL,
                    lon REAL NOT NULL,
                    osm_id TEXT NOT NULL,
                    tags_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "INSERT INTO households (lat, lon, osm_id, tags_json) VALUES (?, ?, ?, ?)",
                (52.0, 6.0, "node/1", json.dumps({"addr:housenumber": "1"})),
            )
            connection.commit()
            connection.close()
            with self.assertRaises(LocalDataError) as caught:
                query_households(52.0, 6.0, 1000, path=path)
        self.assertIn(BUILD_COMMAND, str(caught.exception))

    def test_repeated_query_uses_the_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "households.sqlite"
            _write_households(
                path,
                [(52.0, 6.0, "node/1", json.dumps({"addr:housenumber": "1", "addr:street": "Lane"}))],
            )
            first = query_households(52.0, 6.0, 1000, path=path)
            with patch("households.local_store.sqlite3.connect", side_effect=AssertionError("database")):
                second = query_households(52.0, 6.0, 1000, path=path)
        self.assertEqual(first[0].osm_id, "node/1")
        self.assertEqual(second[0].osm_id, "node/1")
        self.assertEqual(second[0].tags["addr:street"], "Lane")


class TestSourceSelection(unittest.TestCase):
    def test_auto_uses_local_file_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "households.sqlite"
            _write_households(
                path,
                [(52.0, 6.0, "node/1", json.dumps({"addr:housenumber": "1", "addr:street": "Lane"}))],
            )
            with patch("households.config.local_database_path", return_value=path), patch(
                "households.source.fetch_households"
            ) as fetch:
                households, resolved = get_households(52.0, 6.0, 1000, source="auto")
        fetch.assert_not_called()
        self.assertEqual(resolved, "local")
        self.assertEqual(households[0].tags["addr:street"], "Lane")

    def test_auto_uses_overpass_when_file_is_missing(self):
        missing = Path(tempfile.gettempdir()) / "absent-households.sqlite"
        sentinel = [Household(lat=52.0, lon=6.0, tags={"addr:housenumber": "9"}, osm_id="node/9")]
        with patch("households.config.local_database_path", return_value=missing), patch(
            "households.source.fetch_households", return_value=sentinel
        ) as fetch:
            households, resolved = get_households(52.0, 6.0, 1000, source="auto")
        fetch.assert_called_once()
        self.assertEqual(resolved, "overpass")
        self.assertEqual(households, sentinel)

    def test_overpass_is_used_even_when_a_local_file_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "households.sqlite"
            _write_households(path, [(52.0, 6.0, "node/1", json.dumps({"addr:housenumber": "1"}))])
            sentinel = [Household(lat=1.0, lon=2.0, tags={}, osm_id="node/8")]
            with patch("households.config.local_database_path", return_value=path), patch(
                "households.source.fetch_households", return_value=sentinel
            ) as fetch:
                households, resolved = get_households(52.0, 6.0, 1000, source="overpass")
        fetch.assert_called_once()
        self.assertEqual(resolved, "overpass")
        self.assertEqual(households, sentinel)

    def test_local_without_a_file_raises(self):
        missing = Path(tempfile.gettempdir()) / "absent-households.sqlite"
        with patch("households.config.local_database_path", return_value=missing):
            with self.assertRaises(LocalDataError) as caught:
                get_households(52.0, 6.0, 500, source="local")
        self.assertIn(BUILD_COMMAND, str(caught.exception))


class TestBuildCommand(unittest.TestCase):
    def test_geofabrik_region_url(self):
        self.assertEqual(
            geofabrik_pbf_url("europe/netherlands"),
            "https://download.geofabrik.de/europe/netherlands-latest.osm.pbf",
        )
        self.assertEqual(
            geofabrik_pbf_url("/europe/netherlands-latest.osm.pbf"),
            "https://download.geofabrik.de/europe/netherlands-latest.osm.pbf",
        )

    def test_geofabrik_region_rejects_parent_paths(self):
        with self.assertRaises(ValueError):
            geofabrik_pbf_url("../secret")

    def test_missing_pbf_returns_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = main(["--pbf", str(Path(tmp) / "missing.osm.pbf")])
        self.assertEqual(code, 1)

    def test_direct_script_run_reports_missing_pbf(self):
        repo_root = Path(__file__).resolve().parents[1]
        script = repo_root / "households" / "build_local.py"
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.osm.pbf"
            completed = subprocess.run(
                [sys.executable, str(script), "--pbf", str(missing)],
                capture_output=True,
                text=True,
                cwd=repo_root,
            )
        self.assertEqual(completed.returncode, 1)
        self.assertIn("PBF file was not found", completed.stderr)
        self.assertNotIn("ImportError", completed.stderr)
        self.assertNotIn("attempted relative import", completed.stderr)


if __name__ == "__main__":
    unittest.main()
