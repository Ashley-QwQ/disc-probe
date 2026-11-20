"""Shared, device-free assessment of geometry at the radii actually used."""
import math

import numpy as np

from .calscan import _dtheta

RADIUS_TOL_MM = .002
DVD_PRESET_MM = (25.8, 54.4)
IMAGE_OUTER_MM = 56.0
IMAGE_INNER_MM = {'dvd': 24.5, 'cd': 26.0}
IMAGE_HALF_CELL_MM = .01  # drawing_span includes the edges of the default 20 um cells


def default_range(media, measured_span=None):
    """Envelope used by the default picture and preset (the CD preset fits its measured span)."""
    if media not in IMAGE_INNER_MM:
        return None
    preset = measured_span if media == 'cd' and measured_span else DVD_PRESET_MM if media == 'dvd' else None
    inner, outer = IMAGE_INNER_MM[media] - IMAGE_HALF_CELL_MM, IMAGE_OUTER_MM + IMAGE_HALF_CELL_MM
    return (min(inner, preset[0]), max(outer, preset[1])) if preset else (inner, outer)


def assess_range(fit, radius_range):
    lo, hi = map(float, radius_range)
    if not (math.isfinite(lo) and math.isfinite(hi) and 0 <= lo < hi):
        raise ValueError('radius range must be finite, positive and increasing')
    coverage = fit.get('coverage') or {}
    intervals = coverage.get('measured_intervals_mm')
    if intervals is None:
        span = fit.get('measured_span_mm')
        intervals = [span] if span else []
    # Merge intervals within the existing comparison tolerance before projecting
    # them onto the requested ring. Actual holes remain visible to every caller.
    merged = []
    valid = (pair for pair in intervals if isinstance(pair, (list, tuple)) and len(pair) == 2
             and all(isinstance(x, (int, float)) and math.isfinite(x) for x in pair) and pair[1] >= pair[0])
    for a, z in sorted(valid, key=lambda pair: pair[0]):
        if merged and a <= merged[-1][1] + RADIUS_TOL_MM:
            merged[-1][1] = max(z, merged[-1][1])
        else:
            merged.append([float(a), float(z)])
    missing = []
    cursor = lo
    intersects = False
    for a, z in merged:
        if z < cursor - RADIUS_TOL_MM or a > hi + RADIUS_TOL_MM:
            continue
        intersects = True
        if a > cursor + RADIUS_TOL_MM:
            missing.append([cursor, min(float(a), hi)])
        cursor = max(cursor, float(z))
        if cursor >= hi - RADIUS_TOL_MM:
            break
    if not intersects or cursor < hi - RADIUS_TOL_MM:
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
                covered_intervals_mm=[[max(a, lo), min(z, hi)] for a, z in merged if min(z, hi) > max(a, lo)],
                extrapolated_mm=missing, covered=bool(merged) and not missing,
                conditional_angle_sigma_deg=sigma,
                largest_unsampled_gap_mm=coverage.get('largest_unsampled_gap_mm'),
                model_bias='unknown between samples; not included in covariance')


def range_warning(fit, radius_range, *, allow_dis_nominal=False):
    if fit.get('model') == 'clv':
        return None
    assessment = assess_range(fit, radius_range)
    if not assessment['measured_intervals_mm']:
        # image has already clipped its request to the writable geometry. A
        # compatible DIS conversion supplies that geometry, but no measurements.
        if allow_dis_nominal and fit.get('model') == 'dis_import' and fit.get('image_compatible') is True:
            return None
        return 'Measured radius coverage is unknown; extrapolation cannot be checked.'
    if assessment['extrapolated_mm']:
        return (f"EXTRAPOLATION: requested radii {assessment['requested_mm']} mm extend outside measured "
                f"intervals {assessment['measured_intervals_mm']} mm; extrapolated radii "
                f"{assessment['extrapolated_mm']} mm. Local angle sigma does not validate this range.")
    sigma = assessment['conditional_angle_sigma_deg']
    if sigma is not None and sigma > .6 and not fit.get('correction_file'):
        return f'Requested-range angle sigma is {sigma:.2f} deg (conditional on the model); measure this range again.'
    return None
