"""Numerical companions to docs/AUTO_CALIBRATION_EXPLAINED.md.

Run from the repository root: python tools/check_autocalibration_math.py
No device access, disc writes, network access, or output files. These finite
checks are not mathematical proofs or a validation of real-drive accuracy.
"""

from __future__ import annotations

import math
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from discprobe.analysis import (coherence, estimate_period, phase_offsets,
                                robust_circular_mean, wrap_pi)
from discprobe.calib import SECTOR_BITS, theta
from discprobe.calscan import _dtheta


class AutocalibrationMath(unittest.TestCase):
    """Fixed seeds and ordinary float64 tolerances, not device precision claims."""

    def setUp(self):
        self.bit_mm = 133.3e-6
        self.r0_mm = 24.0
        self.pitch_mm = 0.74e-3
        self.u = self.r0_mm / self.bit_mm
        self.v = self.pitch_mm / self.bit_mm
        self.n = np.array([1e6, 1e8, 1e10, 2295104 * SECTOR_BITS])

    def test_spiral_geometry_and_stable_expression(self):
        radius = np.sqrt(self.r0_mm**2 + self.pitch_mm * self.bit_mm * self.n / math.pi)
        geometric_angle = 2 * math.pi * (radius - self.r0_mm) / self.pitch_mm
        np.testing.assert_allclose(theta(self.n, self.u, self.v), geometric_angle,
                                   rtol=2e-10, atol=2e-10)
        self.assertEqual(theta(0.0, self.u, self.v), 0.0)

    def test_analytic_parameter_derivatives(self):
        du, dv = _dtheta(self.n, self.u, self.v)
        hu, hv = self.u * 1e-5, self.v * 1e-5
        numeric_u = (theta(self.n, self.u + hu, self.v)
                     - theta(self.n, self.u - hu, self.v)) / (2 * hu)
        numeric_v = (theta(self.n, self.u, self.v + hv)
                     - theta(self.n, self.u, self.v - hv)) / (2 * hv)
        np.testing.assert_allclose(du, numeric_u, rtol=3e-7, atol=1e-12)
        np.testing.assert_allclose(dv, numeric_v, rtol=3e-7, atol=1e-9)

    def test_inverse_squared_local_rate_is_linear(self):
        step = self.n * 1e-5
        derivative = (theta(self.n + step, self.u, self.v)
                      - theta(self.n - step, self.u, self.v)) / (2 * step)
        np.testing.assert_allclose(1 / derivative**2,
                                   self.u**2 + self.v * self.n / math.pi, rtol=2e-9)

    def test_period_coherence_and_alias_example(self):
        regular = [0.0, 0.040, 0.080, 0.120]
        irregular = [0.0, 0.040, 0.100, 0.160, 0.180]
        self.assertAlmostEqual(coherence(regular, 50.0), 1.0)
        self.assertAlmostEqual(coherence(regular, 25.0), 1.0)
        self.assertAlmostEqual(coherence(irregular, 50.0), 1.0)
        self.assertAlmostEqual(coherence(irregular, 25.0), 0.2)
        # The 10-ms harmonic remains a perfect fit: coherence alone is not proof.
        self.assertAlmostEqual(coherence(irregular, 100.0), 1.0)

    def test_period_fit_phase_and_circular_mean(self):
        base_ns = 5_000_000_000
        turns = [0, 2, 5, 8, 9, 12, 16, 21, 25]
        reference = [base_ns + k * 20_000_000 for k in turns]
        fit = estimate_period(reference, t_min_s=0.015, t_max_s=0.050)
        self.assertIsNotNone(fit)
        self.assertAlmostEqual(fit.period_s, 0.020, places=10)
        target = [base_ns + k * 20_000_000 + 7_000_000 for k in [1, 3, 6, 10, 15, 22]]
        phases = phase_offsets(fit, target)
        for phase in phases:
            self.assertLess(abs(wrap_pi(phase - math.radians(126))), 1e-8)
        near_zero = robust_circular_mean([math.radians(359), math.radians(1)])
        self.assertAlmostEqual(near_zero["mean_deg"] % 360, 0.0)
        for elapsed_ms in (47, 67):
            self.assertEqual((elapsed_ms % 20) * 360 / 20, 126)

    def test_nearest_branch_requires_less_than_half_a_turn(self):
        rng = np.random.default_rng(20261107)
        truth = rng.uniform(-1e6, 1e6, 1000)
        measurement_error = rng.uniform(-10, 10, 1000)
        prediction_error = rng.uniform(-150, 150, 1000)
        unwrapped_observation = truth + measurement_error
        phase = unwrapped_observation % 360
        predicted = truth + prediction_error
        recovered = phase + 360 * np.rint((predicted - phase) / 360)
        np.testing.assert_allclose(recovered, unwrapped_observation, rtol=0, atol=2e-10)
        self.assertEqual(80 + 360 * round((797 - 80) / 360), 800)
        # Outside the condition, a wrong branch is possible, not merely hypothetical.
        self.assertEqual(80 + 360 * round((1000 - 80) / 360), 1160)

    def test_common_length_scale_is_unobservable(self):
        baseline = theta(self.n, self.u, self.v)
        for scale in (0.8, 1.2, 3.0):
            u = (scale * self.r0_mm) / (scale * self.bit_mm)
            v = (scale * self.pitch_mm) / (scale * self.bit_mm)
            np.testing.assert_allclose(theta(self.n, u, v), baseline,
                                       rtol=2e-15, atol=2e-10)

    def test_constant_along_track_shift_is_unobservable(self):
        reference = 1e10
        for shift in (-100_000.0, 121_128.0, 1_000_000.0):
            shifted_u = math.sqrt(self.u**2 + self.v * shift / math.pi)
            physical = (theta(self.n + shift, self.u, self.v)
                        - theta(reference + shift, self.u, self.v))
            alternative = (theta(self.n, shifted_u, self.v)
                           - theta(reference, shifted_u, self.v))
            np.testing.assert_allclose(physical, alternative, rtol=0, atol=3e-10)

    def test_rank_one_variance_update(self):
        rng = np.random.default_rng(20261108)
        for _ in range(25):
            a = rng.normal(size=(3, 3))
            covariance = a @ a.T + np.eye(3)
            h, g = rng.normal(size=(2, 3))
            noise_variance = 0.25
            ph = covariance @ h
            denominator = noise_variance + h @ ph
            updated = covariance - np.outer(ph, ph) / denominator
            direct = np.linalg.inv(np.linalg.inv(covariance)
                                   + np.outer(h, h) / noise_variance)
            np.testing.assert_allclose(updated, direct, rtol=2e-13, atol=2e-13)
            reduction = float(g @ covariance @ g - g @ updated @ g)
            self.assertGreaterEqual(reduction, -1e-12)
            self.assertAlmostEqual(reduction, float(g @ ph)**2 / denominator, places=11)

    def test_geometry_and_latency_can_compensate(self):
        angular_velocity = 2 * math.pi / 0.020
        geometry = theta(self.n, self.u, self.v)
        delay = np.array([0.0020, 0.0021, 0.0022, 0.0023])
        h = np.array([0.010, -0.020, 0.030, -0.010])
        observed = geometry + angular_velocity * delay
        equivalent = (geometry + h) + angular_velocity * (delay - h / angular_velocity)
        np.testing.assert_allclose(equivalent - equivalent[0], observed - observed[0],
                                   rtol=0, atol=2e-10)


if __name__ == "__main__":
    unittest.main(verbosity=2)
