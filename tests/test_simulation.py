"""Unit tests for simulation module: dataclasses, model, propagation, utils."""

import math
import numpy as np
import unittest

from simulation.dataclasses import NoiseSource, Receiver, EnvironmentParameters
from simulation.model import RadioNoiseModel, NearFieldError
from simulation.propagation import (
    PROPAGATION_REGISTRY,
)
from simulation.propagation.groundwave import (
    validate_groundwave_env_params,
    groundwave_propagation,
)
from simulation.propagation.line_of_sight import (
    validate_los_env_params,
    line_of_sight_propagation,
)
from simulation.validation import validate_source_params, validate_receiver_params
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
        """rat_to_db(0) returns -inf; routes must handle this."""
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

    def test_environment_parameters_defaults(self):
        env = EnvironmentParameters()
        self.assertEqual(env.N_s, 0.0)
        self.assertEqual(env.epsilon, 1.0)
        self.assertEqual(env.sigma, 0.0)


# ── Validation (source / receiver) ───────────────────────────────────────────

class TestValidateSourceParams(unittest.TestCase):
    def test_valid_params(self):
        raw = {"freq": 1000000, "eirp": 1.0, "source_height": 1.5}
        params, errors = validate_source_params(raw)
        self.assertIsNone(errors)
        self.assertIsNotNone(params)
        self.assertEqual(params["freq"], 1000000)
        self.assertEqual(params["source_height"], 1.5)

    def test_missing_freq(self):
        raw = {"eirp": 1.0, "source_height": 1.5}
        params, errors = validate_source_params(raw)
        self.assertIsNotNone(errors)
        self.assertIn("freq", errors)

    def test_zero_freq_rejected(self):
        raw = {"freq": 0, "eirp": 1.0, "source_height": 1.5}
        params, errors = validate_source_params(raw)
        self.assertIsNotNone(errors)
        self.assertIn("freq", errors)

    def test_height_out_of_range(self):
        raw = {"freq": 1e6, "eirp": 1.0, "source_height": 100}
        params, errors = validate_source_params(raw)
        self.assertIsNotNone(errors)
        self.assertIn("source_height", errors)


class TestValidateReceiverParams(unittest.TestCase):
    def test_valid(self):
        params, errors = validate_receiver_params({"receiver_height": 2.0})
        self.assertIsNone(errors)
        self.assertEqual(params["receiver_height"], 2.0)

    def test_missing(self):
        params, errors = validate_receiver_params({})
        self.assertIsNotNone(errors)
        self.assertIn("receiver_height", errors)


# ── Validation (groundwave env params) ───────────────────────────────────────

class TestValidateGroundwaveEnvParams(unittest.TestCase):
    def test_valid_params(self):
        raw = {"n_s": 300, "epsilon": 20, "sigma": 0.03, "freq": 1000000}
        params, errors = validate_groundwave_env_params(raw)
        self.assertIsNone(errors)
        self.assertIsNotNone(params)
        self.assertEqual(params["n_s"], 300)

    def test_freq_out_of_range_low(self):
        raw = {"n_s": 300, "epsilon": 20, "sigma": 0.03, "freq": 1000}
        params, errors = validate_groundwave_env_params(raw)
        self.assertIsNotNone(errors)
        self.assertIn("freq", errors)

    def test_sigma_zero_rejected(self):
        raw = {"n_s": 300, "epsilon": 20, "sigma": 0, "freq": 1000000}
        params, errors = validate_groundwave_env_params(raw)
        self.assertIsNotNone(errors)
        self.assertIn("sigma", errors)

    def test_n_s_out_of_range(self):
        raw = {"n_s": 100, "epsilon": 20, "sigma": 0.03, "freq": 1000000}
        params, errors = validate_groundwave_env_params(raw)
        self.assertIsNotNone(errors)
        self.assertIn("n_s", errors)


class TestValidateLosEnvParams(unittest.TestCase):
    def test_always_valid(self):
        params, errors = validate_los_env_params({})
        self.assertIsNone(errors)
        self.assertEqual(params, {})


# ── Propagation Registry ──────────────────────────────────────────────────────

class TestPropagationRegistry(unittest.TestCase):
    def test_registry_contains_expected_models(self):
        self.assertIn("groundwave", PROPAGATION_REGISTRY)
        self.assertIn("line_of_sight", PROPAGATION_REGISTRY)

    def test_registry_entries_have_required_keys(self):
        for key, entry in PROPAGATION_REGISTRY.items():
            self.assertIn("label", entry, f"{key} missing 'label'")
            self.assertIn("function", entry, f"{key} missing 'function'")
            self.assertIn("validate_env", entry, f"{key} missing 'validate_env'")
            self.assertIn("env_fields", entry, f"{key} missing 'env_fields'")


# ── MMN Model (mock propagation) ──────────────────────────────────────────────

def _mock_propagation(source, receiver, env):
    return -50.0


class TestRadioNoiseModel(unittest.TestCase):
    def _make_env(self):
        return EnvironmentParameters(N_s=300, epsilon=20, sigma=0.03)

    def test_single_source_single_model(self):
        src = NoiseSource(id=0, lat=52, lon=6, address="x", position=(500.0, 0.0), EIRP=1.0, freq=1e6)
        rx = Receiver(id=0, position=(0.0, 0.0))
        env = self._make_env()
        model = RadioNoiseModel(
            noise_sources=[src],
            receivers=[rx],
            propagation_models=[(_mock_propagation, env)],
        )
        model.compute_total_power()
        self.assertTrue(np.isfinite(rx.received_power))
        # EIRP=1.0 dBW + prop=-50.0 dB = -49.0 dBW
        self.assertAlmostEqual(rx.received_power, -49.0, delta=0.01)

    def test_two_models_incoherent_sum(self):
        """Two identical models should add power linearly (result = 3 dB above single model)."""
        src = NoiseSource(id=0, lat=52, lon=6, address="x", position=(500.0, 0.0), EIRP=1.0, freq=1e6)
        rx = Receiver(id=0, position=(0.0, 0.0))
        env = self._make_env()
        model_single = RadioNoiseModel(
            noise_sources=[src],
            receivers=[rx],
            propagation_models=[(_mock_propagation, env)],
        )
        model_single.compute_total_power()
        single_power = rx.received_power

        rx2 = Receiver(id=0, position=(0.0, 0.0))
        model_double = RadioNoiseModel(
            noise_sources=[src],
            receivers=[rx2],
            propagation_models=[(_mock_propagation, env), (_mock_propagation, env)],
        )
        model_double.compute_total_power()
        self.assertAlmostEqual(rx2.received_power, single_power + 10 * np.log10(2), delta=0.01)

    def test_near_field_raises(self):
        src = NoiseSource(id=0, lat=52, lon=6, address="x", position=(10.0, 0.0), freq=1e6)
        rx = Receiver(id=0, position=(0.0, 0.0))
        env = self._make_env()
        model = RadioNoiseModel(
            noise_sources=[src],
            receivers=[rx],
            propagation_models=[(_mock_propagation, env)],
        )
        with self.assertRaises(NearFieldError):
            model.compute_total_power()

    def test_zero_sources_yields_inf(self):
        """Zero sources: total_power stays 0, rat_to_db(0) = -inf. Routes must handle."""
        rx = Receiver(id=0, position=(0.0, 0.0))
        env = self._make_env()
        model = RadioNoiseModel(
            noise_sources=[],
            receivers=[rx],
            propagation_models=[(_mock_propagation, env)],
        )
        model.compute_total_power()
        self.assertTrue(np.isinf(rx.received_power))
        self.assertLess(rx.received_power, 0)

    def test_very_negative_contributions_finite(self):
        """Very negative contributions yield finite but very negative received_power."""
        def _very_negative_prop(source, receiver, env):
            return -1000.0

        src = NoiseSource(id=0, lat=52, lon=6, address="x", position=(500.0, 0.0), EIRP=-50, freq=1e6)
        rx = Receiver(id=0, position=(0.0, 0.0))
        env = self._make_env()
        model = RadioNoiseModel(
            noise_sources=[src],
            receivers=[rx],
            propagation_models=[(_very_negative_prop, env)],
        )
        model.compute_total_power()
        self.assertTrue(np.isfinite(rx.received_power))
        self.assertLess(rx.received_power, -500)

    def test_multiple_sources_sum(self):
        """N identical sources at same position sum as 10*log10(N) dB above one source."""
        env = self._make_env()
        n = 4
        sources = [
            NoiseSource(id=i, lat=52, lon=6, address="x", position=(500.0, 0.0), EIRP=1.0, freq=1e6)
            for i in range(n)
        ]
        rx_single = Receiver(id=0, position=(0.0, 0.0))
        rx_multi = Receiver(id=0, position=(0.0, 0.0))

        model_single = RadioNoiseModel(
            noise_sources=sources[:1],
            receivers=[rx_single],
            propagation_models=[(_mock_propagation, env)],
        )
        model_single.compute_total_power()

        model_multi = RadioNoiseModel(
            noise_sources=sources,
            receivers=[rx_multi],
            propagation_models=[(_mock_propagation, env)],
        )
        model_multi.compute_total_power()

        expected = rx_single.received_power + 10 * np.log10(n)
        self.assertAlmostEqual(rx_multi.received_power, expected, delta=0.01)


if __name__ == "__main__":
    unittest.main()
