"""Unit tests for simulation module: dataclasses, model, propagation, utils."""

import math
import numpy as np
import unittest

from simulation.MMN_dataclasses import NoiseSource, Receiver, EnvironmentParameters
from simulation.MMN_model import RadioNoiseModel, NearFieldError
from simulation.propagation import validate_groundwave_params, groundwave_propagation
from simulation.utils import db_to_rat, rat_to_db, latlon_to_local_meters


def _approx(a, b, rel=1e-5):
    return abs(a - b) <= max(abs(a), abs(b)) * rel


# ── Utils ────────────────────────────────────────────────────────────────────

class TestUtils(unittest.TestCase):
    def test_db_to_rat(self):
        self.assertEqual(db_to_rat(0), 1.0)
        self.assertEqual(db_to_rat(10), 10.0)
        self.assertAlmostEqual(db_to_rat(-10), 0.1)

    def test_rat_to_db(self):
        self.assertEqual(rat_to_db(1.0), 0.0)
        self.assertTrue(_approx(rat_to_db(10.0), 10.0))
        self.assertTrue(_approx(rat_to_db(0.1), -10.0))

    def test_rat_to_db_zero_returns_inf(self):
        """H1: rat_to_db(0) returns -inf; routes must handle this."""
        result = rat_to_db(0.0)
        self.assertTrue(np.isinf(result))
        self.assertLess(result, 0)

    def test_rat_to_db_negative_returns_nan(self):
        result = rat_to_db(-1.0)
        self.assertTrue(np.isnan(result))

    def test_latlon_to_local_meters_origin(self):
        x, y = latlon_to_local_meters(52.0, 6.0, 52.0, 6.0)
        self.assertAlmostEqual(x, 0.0, places=2)
        self.assertAlmostEqual(y, 0.0, places=2)

    def test_latlon_to_local_meters_north(self):
        x, y = latlon_to_local_meters(52.001, 6.0, 52.0, 6.0)
        self.assertGreater(y, 0)
        self.assertLess(abs(x), 1)

    def test_latlon_to_local_meters_euclidean_equals_geodesic(self):
        from geographiclib.geodesic import Geodesic
        lat0, lon0 = 52.0, 6.0
        lat, lon = 52.01, 6.02
        x, y = latlon_to_local_meters(lat, lon, lat0, lon0)
        euclidean = math.hypot(x, y)
        geo = Geodesic.WGS84.Inverse(lat0, lon0, lat, lon)
        geodesic = geo["s12"]
        self.assertAlmostEqual(euclidean, geodesic, delta=geodesic * 1e-5)


# ── Dataclasses ──────────────────────────────────────────────────────────────

class TestMMNDataclasses(unittest.TestCase):
    def test_receiver_distance_to(self):
        rx = Receiver(id=0, position=(0.0, 0.0))
        d = rx.distance_to((3.0, 4.0))
        self.assertEqual(d, 5.0)

    def test_far_field_condition_near(self):
        rx = Receiver(id=0, position=(0.0, 0.0))
        src = NoiseSource(id=0, lat=0, lon=0, address="x", position=(100.0, 0.0), freq=1e6)
        self.assertFalse(rx.far_field_condition(src))

    def test_far_field_condition_far(self):
        rx = Receiver(id=0, position=(0.0, 0.0))
        src = NoiseSource(id=0, lat=0, lon=0, address="x", position=(200.0, 0.0), freq=1e6)
        self.assertTrue(rx.far_field_condition(src))


# ── Validation ─────────────────────────────────────────────────────────────────

class TestValidateGroundwaveParams(unittest.TestCase):
    def test_valid_params(self):
        raw = {"freq": 1000000, "eirp": 1.0, "height": 1.5, "n_s": 300, "epsilon": 20, "sigma": 0.03}
        params, errors = validate_groundwave_params(raw)
        self.assertIsNone(errors)
        self.assertIsNotNone(params)
        self.assertEqual(params["freq"], 1000000)

    def test_missing_freq(self):
        raw = {"eirp": 1.0, "height": 1.5, "n_s": 300, "epsilon": 20, "sigma": 0.03}
        params, errors = validate_groundwave_params(raw)
        self.assertIsNotNone(errors)
        self.assertIn("freq", errors)

    def test_freq_out_of_range_low(self):
        raw = {"freq": 1000, "eirp": 1.0, "height": 1.5, "n_s": 300, "epsilon": 20, "sigma": 0.03}
        params, errors = validate_groundwave_params(raw)
        self.assertIsNotNone(errors)
        self.assertIn("freq", errors)

    def test_sigma_zero_rejected(self):
        raw = {"freq": 1000000, "eirp": 1.0, "height": 1.5, "n_s": 300, "epsilon": 20, "sigma": 0}
        params, errors = validate_groundwave_params(raw)
        self.assertIsNotNone(errors)
        self.assertIn("sigma", errors)


# ── MMN Model (mock propagation) ──────────────────────────────────────────────

def _mock_propagation(source, receiver, env):
    return -50.0


class TestRadioNoiseModel(unittest.TestCase):
    def test_single_source(self):
        src = NoiseSource(id=0, lat=52, lon=6, address="x", position=(500.0, 0.0), EIRP=1.0, freq=1e6)
        rx = Receiver(id=0, position=(0.0, 0.0))
        env = EnvironmentParameters(N_s=300, epsilon=20, sigma=0.03)
        model = RadioNoiseModel(
            noise_sources=[src],
            receivers=[rx],
            environment_params=env,
            propagation_function=_mock_propagation,
        )
        model.compute_total_power()
        self.assertTrue(np.isfinite(rx.received_power))
        self.assertTrue(_approx(rx.received_power, -49.0, rel=0.1))

    def test_near_field_raises(self):
        src = NoiseSource(id=0, lat=52, lon=6, address="x", position=(10.0, 0.0), freq=1e6)
        rx = Receiver(id=0, position=(0.0, 0.0))
        env = EnvironmentParameters(N_s=300, epsilon=20, sigma=0.03)
        model = RadioNoiseModel(
            noise_sources=[src],
            receivers=[rx],
            environment_params=env,
            propagation_function=_mock_propagation,
        )
        with self.assertRaises(NearFieldError):
            model.compute_total_power()

    def test_all_contributions_very_negative(self):
        """Very negative contributions yield finite but very negative received_power (not -inf in practice)."""
        def _very_negative_prop(source, receiver, env):
            return -1000.0

        src = NoiseSource(id=0, lat=52, lon=6, address="x", position=(500.0, 0.0), EIRP=-50, freq=1e6)
        rx = Receiver(id=0, position=(0.0, 0.0))
        env = EnvironmentParameters(N_s=300, epsilon=20, sigma=0.03)
        model = RadioNoiseModel(
            noise_sources=[src],
            receivers=[rx],
            environment_params=env,
            propagation_function=_very_negative_prop,
        )
        model.compute_total_power()
        # contribution = -50 + (-1000) = -1050 dB; total_power_rat = 10^(-105) > 0 (tiny)
        # received_power = rat_to_db(tiny) = very negative but finite
        self.assertTrue(np.isfinite(rx.received_power))
        self.assertLess(rx.received_power, -500)

    def test_zero_sources_yields_inf(self):
        """Zero sources: total_power stays 0, rat_to_db(0) = -inf. Routes must handle."""
        rx = Receiver(id=0, position=(0.0, 0.0))
        env = EnvironmentParameters(N_s=300, epsilon=20, sigma=0.03)
        model = RadioNoiseModel(
            noise_sources=[],
            receivers=[rx],
            environment_params=env,
            propagation_function=_mock_propagation,
        )
        model.compute_total_power()
        self.assertTrue(np.isinf(rx.received_power))
        self.assertLess(rx.received_power, 0)


if __name__ == "__main__":
    unittest.main()
