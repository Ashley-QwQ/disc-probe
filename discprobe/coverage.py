"""Shared, device-free assessment of geometry at the radii actually used."""
import math

import numpy as np

from .calscan import _dtheta


def assess_range(fit, radius_range):
    lo, hi = map(float, radius_range)
    if not (math.isfinite(lo) and math.isfinite(hi) and 0 <= lo < hi):
        raise ValueError('radius range must be finite, positive and increasing')
    coverage = fit.get('coverage') or {}
    intervals = coverage.get('measured_intervals_mm')
    if intervals is None:
        span = fit.get('measured_span_mm')
        intervals = [span] if span else []
    # Subtract the measured islands from the requested interval. A failed internal
    # region stays outside coverage even when the extreme measured radii enclose it.
    missing = []
    cursor = lo
    for a, z in sorted(intervals):
        if z < cursor - .002 or a > hi + .002:
            continue
        if a > cursor + .002:
            missing.append([cursor, min(float(a), hi)])
        cursor = max(cursor, float(z))
        if cursor >= hi - .002:
            break
    if cursor < hi - .002:
        missing.append([cursor, hi])
    sigma = None
    cov = fit.get('covariance_uv')
    if cov is not None and 'u' in fit:
        u, v = fit['u'], fit['v']
        bit = fit['bit_nm_assumed'] * 1e-6
        ns = [max(0., math.pi * ((r / bit)**2 - u*u) / v) for r in (lo, hi)]
        g = np.subtract(_dtheta(ns[1], u, v), _dtheta(ns[0], u, v))
        sigma = math.degrees(math.sqrt(max(0., float(g @ np.asarray(cov) @ g))))
    return dict(requested_mm=[lo, hi], measured_intervals_mm=intervals,
                extrapolated_mm=missing, covered=bool(intervals) and not missing,
                conditional_angle_sigma_deg=sigma,
                largest_unsampled_gap_mm=coverage.get('largest_unsampled_gap_mm'),
                model_bias='unknown between samples; not included in covariance')


def range_warning(fit, radius_range):
    if fit.get('model') == 'clv':
        return None
    assessment = assess_range(fit, radius_range)
    if not assessment['measured_intervals_mm']:
        return 'Measured radius coverage is unknown; extrapolation cannot be checked.'
    if assessment['extrapolated_mm']:
        return (f"EXTRAPOLATION: requested radii {assessment['requested_mm']} mm extend outside measured "
                f"intervals {assessment['measured_intervals_mm']} mm; extrapolated radii "
                f"{assessment['extrapolated_mm']} mm. Local angle sigma does not validate this range.")
    sigma = assessment['conditional_angle_sigma_deg']
    if sigma is not None and sigma > .6 and not fit.get('correction_file'):
        return f'Requested-range angle sigma is {sigma:.2f} deg (conditional on the model); measure this range again.'
    return None
