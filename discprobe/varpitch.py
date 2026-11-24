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


def exceeds_noise(targets, chi2, radii):
    """Require excess residuals and corroboration across neighbouring radii."""
    if len(targets) < MIN_POINTS or chi2 <= TRIGGER_CHI2 or np.ptp(radii) < 5.:
        return False
    residual = np.array([t['residual_deg'] for t in targets])
    sigma = np.array([t['sigma_deg'] for t in targets])
    if (np.max(abs(residual)) >= 90
            or np.mean(residual ** 2) <= max(TRIGGER_RMS_DEG ** 2, 4 * np.mean(sigma ** 2))):
        return False

    # Keep the measured scatter of each block and guard against a spuriously
    # quiet block by using at least the typical standard error in this run.
    counts = np.sqrt([t.get('used') or 24 for t in targets])
    scatter = np.array([t.get('std_deg', s * count) for t, s, count in zip(targets, sigma, counts)])
    sem = scatter / counts
    noise = np.maximum(sigma, np.maximum(sem, np.median(sem)))
    order = np.argsort(radii)
    gap = np.diff(np.asarray(radii)[order])
    y = residual[order]
    noise = noise[order]
    z = y / noise
    neighbours = (gap >= .02) & (gap <= 8.)
    common = neighbours & (y[:-1] * y[1:] > 0)
    amplitude = (abs(y[:-1]) + abs(y[1:])) / 2
    individual = np.minimum(abs(z[:-1]), abs(z[1:]))
    combined = abs(z[:-1] + z[1:]) / np.sqrt(2)
    # Adjacent rungs must independently support a common deviation. Single
    # outlying rungs, the tight reference pair and gaps across most of the disc
    # cannot establish a bend. Quiet reads can resolve a smaller common offset.
    if np.median(scatter) < .55:
        return bool(np.any(common & (amplitude >= .55) & (individual >= .9) & (combined >= 3.5)))

    # A steep feature can leave opposite-sign residuals at its edges. Require
    # both edges and excess scatter at a third rung before asking for closer
    # turn checks. Never use a turn-sized residual as evidence for a bend.
    steep = neighbours & (np.minimum(abs(y[:-1]), abs(y[1:])) >= 4.) & (y[:-1] * y[1:] < 0)
    if np.any(steep) and np.count_nonzero(abs(y) >= np.maximum(1., 2 * noise)) >= 3:
        return True

    # Local changes between rungs reveal noise that can be missed within a
    # block. Pool the within-block and local estimates on the log scale so a
    # gradual real slope does not set the entire noise floor.
    local = neighbours & (gap <= 3.)
    scatter_ratio = abs(np.diff(y))[local] / np.hypot(noise[:-1], noise[1:])[local]
    scale = np.sqrt(max(1., np.median(scatter_ratio) / .67449)) if len(scatter_ratio) >= 4 else 1.
    # A broader coherent trend can corroborate a smaller local deviation.
    # Clip outliers before calculating this spatial correlation.
    clipped = np.clip(z, -3., 3.)
    weight = np.exp(-gap / 3) * neighbours
    product = np.sum(weight * clipped[:-1] * clipped[1:])
    power = np.sum(weight * (clipped[:-1] ** 2 + clipped[1:] ** 2) / 2)
    coherence = max(0., product / max(1., power))
    return bool(np.any(common & (amplitude + .5 * coherence >= 1.2)
                       & (individual >= 1.3 * scale) & (combined >= 3 * scale)))


def refinement_mask(points):
    """Significant changes between repeated means and departures from local lines."""
    first = np.array([p['first']['phi_deg'] for p in points])
    again = np.array([p['again']['phi_deg'] for p in points])
    mean = (first + again) / 2
    # For equal independent reads, the repeat difference has twice the
    # scatter of their mean. Use the median as a pooled estimate and keep
    # large local differences and the within-block uncertainty as floors.
    repeat = abs(first - again) / 2
    block = np.array([np.hypot(p['first']['sigma_deg'], p['again']['sigma_deg']) / 2 for p in points])
    noise = np.maximum(block, np.maximum(repeat, np.median(repeat) / .67449))
    refine = abs(np.diff(mean)) > np.maximum(1., 3 * np.hypot(noise[:-1], noise[1:]))

    gap = np.diff([p['radius_mm'] for p in points])
    left, right = gap[:-1], gap[1:]
    w = right / (left + right)
    line = w * mean[:-2] + (1 - w) * mean[2:]
    line_noise = np.hypot(w * noise[:-2], (1 - w) * noise[2:])
    corner = abs(mean[1:-1] - line) > np.maximum(8 * w * left, 3 * np.hypot(noise[1:-1], line_noise))
    for i in np.flatnonzero(corner):
        refine[max(0, i - 1):i + 3] = True
    return refine


class Bend:
    """Smooth current residual, with tangent continuation and growing reach error."""
    def __init__(self, radius, residual, sigma):
        order = np.argsort(radius)
        x, y, s = (np.asarray(a)[order] for a in (radius, residual, sigma))
        # Very close initial rungs constrain the base geometry, not spline curvature.
        keep = np.r_[True, np.diff(x) > 0.02]
        self.x, self.y, self.sigma = x[keep], y[keep], s[keep]
        degree = min(3, len(self.x) - 1)
        self.spline = UnivariateSpline(self.x, self.y, w=1 / self.sigma, k=degree, s=len(self.x))
        self.tangent = self.spline.derivative()
        # Model error dominates the small constant-pitch covariance. Cache
        # these spline terms for the subsequent candidate searches.
        self.curvature = CURVATURE_FLOOR
        if degree >= 2:
            self.curvature = max(self.curvature, float(np.max(abs(self.spline.derivative(2)(self.x)))) * 2)
        self.noise = float(np.median(self.sigma))

    def __call__(self, radius):
        x = np.asarray(radius)
        edge = np.clip(x, self.x[0], self.x[-1])
        return self.spline(edge) + self.tangent(edge) * (x - edge)

    def uncertainty(self, radius):
        d = float(np.min(abs(self.x - radius)))
        outside = max(self.x[0] - radius, radius - self.x[-1], 0.)
        return self.noise + self.curvature * (outside ** 2 + 0.15 * d ** 2) + 2 * self.noise * outside


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
