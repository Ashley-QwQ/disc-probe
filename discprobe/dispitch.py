"""DIS arc-length geometry and bounded DP angle conversion (no hardware access)."""
import math

import numpy as np
from scipy.integrate import quad, solve_ivp
from scipy.optimize import brentq

ANGLE_LIMIT_DEG = .01
RADIUS_LIMIT_MM = .005
MAX_DEGREE = 16
SAMPLES = 20001


def sector_map(preset, media, bit, bits):
    """DIS accumulated clockwise angle magnitude and radius at full-area positions.

    Solve the exact ds/dr = hypot(1, r*g/q), dtheta/dr = g/q,
    g=2*pi/p0, used by DvdTrackGeometry. Constant CD uses its area rule.
    This integrates the documented model, not the C# implementation's byte output.
    """
    ri, ro = preset['innerRadiusMm'], preset['outerRadiusMm']
    total = preset.get('sectors', preset.get('totalSectors'))
    length = total * bits * bit * 1e-6
    coeff = [preset.get(k, 0) for k in ('pitchLinear', 'pitchQuadratic', 'pitchCubic')]
    t = np.linspace(0, 1, SAMPLES)
    if media == 'cd' and not any(coeff):
        r = np.sqrt(ri*ri + (ro*ro-ri*ri)*t)
        return r, 2*length*(r-ri)/(ro*ro-ri*ri)
    if length <= ro-ri:
        raise ValueError('DIS track length must exceed radial span')

    def q(r):
        x = (r-ri)/(ro-ri)
        return 1 + x*(coeff[0] + x*(coeff[1] + x*coeff[2]))

    thin = quad(lambda r: r/q(r), ri, ro, epsabs=1e-10, epsrel=3e-13)[0]
    upper = length/thin
    g = brentq(lambda g: quad(lambda r: math.hypot(1, r*g/q(r)), ri, ro,
                             epsabs=1e-9, epsrel=3e-13)[0]/length-1,
               0, upper, xtol=1e-12, rtol=1e-14)

    def derivative(_, y):
        rate = g/q(y[0])
        dr = length/math.hypot(1, y[0]*rate)
        return dr, dr*rate

    solution = solve_ivp(derivative, (0, 1), (ri, 0), method='DOP853',
                         rtol=3e-13, atol=(1e-12, 1e-10), t_eval=t)
    if not solution.success or not np.isfinite(solution.y).all():
        raise ValueError('DIS geometry integration failed')
    return solution.y


def convert(preset, media, fit, bit, bits):
    """Fit in the sampler's signed data-side coordinates; never wrap angles."""
    from .disexport import target_angle
    from .imagedisc import Correction
    total = preset.get('sectors', preset.get('totalSectors'))
    n = np.linspace(0, total*bits, SAMPLES)
    r_dis, theta_dis = sector_map(preset, media, bit, bits)
    r_dp = bit*1e-6*np.sqrt(fit['u']**2 + fit['v']*n/math.pi)
    # _sample starts with -theta_DP and ADDS phi: phi = -theta_DIS + theta_DP.
    phi = np.degrees(target_angle(n, fit['u'], fit['v'], bit)-theta_dis)
    varying = any(preset.get(k, 0) for k in ('pitchLinear', 'pitchQuadratic', 'pitchCubic'))
    comparison = dict(samples=SAMPLES, max_radius_error_mm=float(np.max(np.abs(r_dis-r_dp))),
                      baseline_max_angle_error_deg=float(np.max(np.abs(phi))),
                      polynomial_degree=None, fit_range_mm=[float(r_dp[0]), float(r_dp[-1])])
    correction = None
    error = float(np.max(np.abs(phi)))
    if varying:
        x = (r_dp-40)/15
        for degree in range(MAX_DEGREE+1):
            # Chebyshev solve avoids ill conditioning; serialize in the existing power basis.
            poly = np.polynomial.Chebyshev.fit(x, phi, degree).convert(kind=np.polynomial.Polynomial)
            coef = poly.coef[::-1]
            error = float(np.max(np.abs(phi-Correction(coef, r_dp[0], r_dp[-1])(r_dp))))
            correction = dict(poly_in_x=coef.tolist(), radius_valid_mm=comparison['fit_range_mm'],
                              degree=degree, geo_fit=dict(u=fit['u'], v=fit['v']),
                              source='DIS model conversion; unverified by DP measurement')
            comparison['polynomial_degree'] = degree
            if error <= ANGLE_LIMIT_DEG:
                break
    comparison['max_angle_error_deg'] = error
    return comparison, correction
