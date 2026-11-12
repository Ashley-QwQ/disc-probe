"""Radius-dependent angle residuals. No device access; degrees throughout.

The extrapolation envelope is an assumption, not a proof for arbitrary media.
Independent repeated probes choose smoothing; unsampled gaps remain explicit.
"""
from __future__ import annotations

import numpy as np
from scipy.interpolate import UnivariateSpline

MIN_POINTS = 7
TRIGGER_CHI2 = 4.0
TRIGGER_RMS_DEG = 0.35
CURVATURE_FLOOR = 60.0  # deg/mm^2, conservative against the I218 inner bend
PROBE_GAP_MM = 0.35
MIN_PROBE_GAP_MM = 0.025


def exceeds_noise(targets, chi2):
    if len(targets) < MIN_POINTS:
        return False
    rms = np.sqrt(np.mean([t['residual_deg'] ** 2 for t in targets]))
    noise = np.sqrt(np.mean([t['sigma_deg'] ** 2 for t in targets]))
    return chi2 > TRIGGER_CHI2 and rms > max(TRIGGER_RMS_DEG, 2 * noise)


class Bend:
    """Smooth current residual, with tangent continuation and growing reach error."""
    def __init__(self, radius, residual, sigma):
        order = np.argsort(radius)
        x, y, s = (np.asarray(a)[order] for a in (radius, residual, sigma))
        # Very close initial rungs constrain the base geometry, not spline curvature.
        keep = np.r_[True, np.diff(x) > 0.02]
        self.x, self.y, self.sigma = x[keep], y[keep], s[keep]
        self.spline = UnivariateSpline(self.x, self.y, w=1 / self.sigma,
                                       k=min(3, len(self.x) - 1), s=len(self.x))

    def __call__(self, radius):
        x = np.asarray(radius)
        edge = np.clip(x, self.x[0], self.x[-1])
        return self.spline(edge) + self.spline.derivative()(edge) * (x - edge)

    def uncertainty(self, radius):
        d = float(np.min(abs(self.x - radius)))
        outside = max(self.x[0] - radius, radius - self.x[-1], 0.)
        # Include model error rather than using the tiny constant-pitch covariance.
        curve = max(CURVATURE_FLOOR, float(np.max(abs(self.spline.derivative(2)(self.x)))) * 2)
        noise = float(np.median(self.sigma))
        return noise + curve * (outside ** 2 + 0.15 * d ** 2) + 2 * noise * outside


def repeated_spline(radius, first, again, sigma):
    """Two-way repeat CV: fit A, predict B and vice versa, then fit their mean.

    The repeats are not extra independent radii. Scores include repeat read noise;
    report those scores separately from training residuals and coverage.
    """
    order = np.argsort(radius)
    x, a, b, sig = (np.asarray(v)[order] for v in (radius, first, again, sigma))
    scores = []
    for factor in (0., .03, .1, 0.25, 0.5, 1., 2., 4., 8., 16.):
        sa = UnivariateSpline(x, a, w=1 / sig, s=factor * len(x))
        sb = UnivariateSpline(x, b, w=1 / sig, s=factor * len(x))
        score = float(np.mean(np.r_[(sa(x) - b) ** 2, (sb(x) - a) ** 2]))
        scores.append((score, factor))
    score, factor = min(scores)
    mean = (a + b) / 2
    spline = UnivariateSpline(x, mean, w=np.sqrt(2) / sig, s=factor * len(x))
    residual = mean - spline(x)
    t, c, k = spline._eval_args
    return dict(t=t.tolist(), c=c.tolist(), k=int(k)), {
        'smoothing_factor': factor, 'repeat_cv_rms_deg': float(np.sqrt(score)),
        'repeat_difference_rms_deg': float(np.sqrt(np.mean((a - b) ** 2))),
        'residual_rms_deg': float(np.sqrt(np.mean(residual ** 2))),
        'residual_max_deg': float(np.max(abs(residual))),
        'cv_scores': [{'factor': f, 'rms_deg': float(np.sqrt(e))} for e, f in scores],
    }
