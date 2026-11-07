"""Refit a `geo` ladder with a track pitch that varies with radius.

`geo` assumes a constant pitch (u = r0/b, v = p/b). On some media the pitch drifts by ~1e-5
across the disc, which over ~20k turns leaves a smooth S-shaped angle residual of a degree or
two (DiscImageStudio issue #78, CD-R). This refits the measured rungs with

    p(r) = v / (1 + b1 x + b2 x^2 + b3 x^3),   x = (r - rc) / rs

(rc = 40 mm, rs = 15 mm, everything in units of the bit length b) plus a free phase constant,
and compares constant, quadratic and cubic models.

    python tools/geo_polyfit.py results/geo-H-...   [--plot out.png]

--write-correction saves the chosen polynomial as an angle-correction file for `image
--correction`, so a picture drawn with the constant-pitch u, v lands where this fit says:
a byte placed at the model angle -Theta_const(n) really sits at -Theta_poly(n).

A pitch polynomial of order 3 cannot follow a wave of period ~15 mm in radius (seen on CMC CD-R).
--phi-degree N instead fits phi(r) directly with a polynomial of degree N. The table of
leave-one-out errors printed with it shows which degree the rungs themselves support.

Several folders may be supplied for repeated measurements of the SAME disc. Their joint
fit shares u, v and pitch coefficients, with one free phase constant per run. In this
mode --write-correction requires --write-summary; pass that merged summary and correction
together to `disexport` or `image --geo`. The correction covers the union measured span.
When the correction is worthwhile, reproducibility is an F-test of one shared fit of the chosen
pitch order against one fit per run, since each run's constant-pitch model absorbs the pitch
shape differently; otherwise the runs' constant-pitch models must agree. Significance uses the
weighted nested-model F-test, and pooled phi leave-one-out fits include a separate offset for each run.
"""
import argparse
import csv
import json
import math
import os
import sys

import numpy as np
from scipy.optimize import least_squares

RC_MM, RS_MM = 40.0, 15.0
REPRO_TWIST_PP_DEG = 0.3
REPRO_DELTA_SIGMA = 2.0
REPRO_P = 0.01
WORTHWHILE_P = 0.01
WORTHWHILE_LOO_DEGREE = 3
STRAIGHTNESS_MM = 0.05
NOISE_FRACTION = 1 / 3
TWIST_SPAN_MM = (24.0, 58.0)


def model(n, u, v, bs, rc, rs):
    """Spiral angle (rad, up to a constant) and radius (bits) at channel bit n."""
    bs = list(bs) + [0.0] * (3 - len(bs))
    xu = (u - rc) / rs

    def E(x):
        # E0 = int_u^r e dr,  E1 = int_u^r r e dr  with e = b1 x + b2 x^2 + b3 x^3
        p0 = lambda t: bs[0] * t ** 2 / 2 + bs[1] * t ** 3 / 3 + bs[2] * t ** 4 / 4
        p1 = lambda t: bs[0] * t ** 3 / 3 + bs[1] * t ** 4 / 4 + bs[2] * t ** 5 / 5
        e0 = rs * (p0(x) - p0(xu))
        e1 = rs * (rc * (p0(x) - p0(xu)) + rs * (p1(x) - p1(xu)))
        return e0, e1

    r = np.sqrt(u * u + v * n / math.pi)
    for _ in range(4):  # n = (pi/v)(r^2 - u^2) + (2 pi/v) E1(r)
        _, e1 = E((r - rc) / rs)
        r = np.sqrt(u * u + v * n / math.pi - 2 * e1)
    e0, _ = E((r - rc) / rs)
    return 2 * math.pi / v * (r - u + e0), r


def load(run):
    rows = list(csv.DictReader(open(os.path.join(run, "targets.csv"))))
    summ = json.load(open(os.path.join(run, "summary.json")))["fit"]
    n = np.array([float(r["n_bits"]) for r in rows])
    y = np.radians([float(r["unwrapped_deg"]) for r in rows])
    s = np.radians([max(float(r["sigma_deg"]), 0.05) for r in rows])
    return n, y, s, summ


def fit(n, y, s, u0, v0, order, rc, rs):
    def unpack(z):
        return u0 * (1 + z[0] * 1e-5), v0 * (1 + z[1] * 1e-5), z[2:2 + order] * 1e-5, z[-1]

    def res(z):
        u, v, bs, c = unpack(z)
        th, _ = model(n, u, v, bs, rc, rs)
        return (th + c - y) / s

    th0, _ = model(n, u0, v0, [], rc, rs)
    z0 = np.zeros(3 + order)
    z0[-1] = np.mean(y - th0)
    def jac(z):
        h = 1.0
        return np.column_stack([(res(z + h * e) - res(z - h * e)) / (2 * h)
                                for e in np.eye(len(z))])

    sol = least_squares(res, z0, jac=jac, x_scale=np.ones(len(z0)), method="lm")
    if not sol.success or not np.isfinite(sol.fun).all():
        raise ValueError("pitch fit did not converge")
    u, v, bs, c = unpack(sol.x)
    r = sol.fun
    dof = len(n) - len(z0)
    th, rad = model(n, u, v, bs, rc, rs)
    J = jac(sol.x)
    scale = np.linalg.norm(J, axis=0)
    A = J / scale
    if np.linalg.matrix_rank(A) < len(z0):
        raise ValueError("pitch fit parameters are not identifiable")
    cov = np.linalg.inv(A.T @ A) / np.outer(scale, scale)
    cov *= max(1.0, float(r @ r) / dof)
    ends = np.array([np.min(n), np.max(n)])
    def end_angle(z):
        uu, vv, bb, cc = unpack(z)
        return model(ends, uu, vv, bb, rc, rs)[0] + cc
    end_jac = np.column_stack([(end_angle(sol.x + e) - end_angle(sol.x - e)) / 2
                               for e in np.eye(len(z0))])
    g = end_jac[1] - end_jac[0]
    span_sigma = math.degrees(math.sqrt(max(0.0, float(g @ cov @ g))))
    return dict(span_sigma_deg=span_sigma, u=u, v=v, b=list(bs), chi2=float(r @ r), dof=dof,
                rms_deg=float(np.degrees(np.sqrt(np.mean((th + c - y) ** 2)))),
                resid_deg=np.degrees(th + c - y), r_bits=rad)


def write_correction(path, f, summ, run, order, rc, rs, n):
    bit_nm = summ["bit_nm_assumed"]
    grid = np.linspace(n.min(), n.max(), 400)
    th_const, r_bits = model(grid, summ["u"], summ["v"], [], rc, rs)
    th_poly, _ = model(grid, f["u"], f["v"], f["b"], rc, rs)
    phi = np.degrees(th_const - th_poly)  # picture angles run as -Theta(n)
    phi -= phi.mean()
    r = r_bits * bit_nm * 1e-6
    coef = np.polyfit((r - 40.0) / 15.0, phi, 6)  # highest power first, as load_correction expects
    err = phi - np.polyval(coef, (r - 40.0) / 15.0)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"kind": "angle-correction",
                   "meaning": "a byte placed at model angle theta appears at theta + phi(r) (degrees, "
                              "counter-clockwise in data-side view); draw with the design sampled at theta + phi(r)",
                   "radius_valid_mm": [float(r.min()), float(r.max())], "poly_in_x": coef.tolist(),
                   "x": "(r_mm - 40) / 15", "source": f"tools/geo_polyfit.py {run}", "pitch_model": order,
                   "geo_fit": {"u": summ["u"], "v": summ["v"]},
                   "peak_to_peak_deg": float(phi.max() - phi.min())}, fh, indent=2)
    print(f"wrote {path}: phi peak to peak {phi.max() - phi.min():.3f} deg, polynomial error "
          f"{np.abs(err).max():.4f} deg")


def phi_table(r_mm, phi):
    """Leave-one-out error of a degree-d polynomial phi(x), for choosing d from the rungs alone."""
    x = (r_mm - RC_MM) / RS_MM
    print("\nphi(r) polynomial, fit and leave-one-out rms (deg):")
    for d in range(2, min(13, len(x) - 2)):
        H = np.vander(x, d + 1)
        hat = H @ np.linalg.pinv(H)
        e = phi - hat @ phi
        print(f"  degree {d:2d}  fit {np.sqrt(np.mean(e ** 2)):.3f}  leave-one-out "
              f"{np.sqrt(np.mean((e / (1 - np.diag(hat))) ** 2)):.3f}")


def write_phi_correction(path, r_mm, phi, degree, run, summ):
    """Angle correction fitted straight to the rungs, relative to the u, v in summary.json."""
    x = (r_mm - RC_MM) / RS_MM
    coef = np.polyfit(x, phi, degree)
    lo, hi = float(r_mm.min()), float(r_mm.max())
    curve = np.polyval(coef, (np.linspace(lo, hi, 400) - RC_MM) / RS_MM)
    coef[-1] -= curve.mean()
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"kind": "angle-correction",
                   "meaning": "a byte placed at model angle theta appears at theta + phi(r) (degrees, "
                              "counter-clockwise in data-side view); draw with the design sampled at theta + phi(r)",
                   "radius_valid_mm": [lo, hi], "poly_in_x": coef.tolist(),
                   "x": "(r_mm - 40) / 15", "source": f"tools/geo_polyfit.py {run}",
                   "pitch_model": f"phi polynomial, degree {degree}",
                   "geo_fit": {"u": summ["u"], "v": summ["v"]},
                   "peak_to_peak_deg": float(curve.max() - curve.min())}, fh, indent=2)
    print(f"wrote {path}: phi peak to peak {curve.max() - curve.min():.3f} deg, "
          f"fit rms {np.sqrt(np.mean((phi - np.polyval(np.polyfit(x, phi, degree), x)) ** 2)):.3f} deg")


def joint_fit(data, order, rc, rs):
    """Shared spiral, with centred angles to keep each run's large origin out of the solve."""
    u0, v0 = data[0][3]["u"], data[0][3]["v"]
    n = np.concatenate([d[0] for d in data])
    y = np.concatenate([d[1] for d in data])
    s = np.concatenate([d[2] for d in data])
    group = np.repeat(np.arange(len(data)), [len(d[0]) for d in data])
    pivots = np.array([d[0][0] for d in data])

    def unpack(z):
        return u0 * (1 + z[0] * 1e-5), v0 * (1 + z[1] * 1e-5), z[2:2 + order] * 1e-5

    def prediction(z):
        u, v, bs = unpack(z)
        th, _ = model(n, u, v, bs, rc, rs)
        ref, _ = model(pivots, u, v, bs, rc, rs)
        return th - ref[group] + z[2 + order:][group]

    def res(z):
        return (prediction(z) - y) / s

    def jac(z):
        # Default finite differences lose the small pitch terms in the accumulated angle.
        steps = np.eye(len(z)) * 0.05
        return np.column_stack([(res(z + step) - res(z - step)) / 0.1 for step in steps])

    z0 = np.zeros(2 + order + len(data))
    th, _ = model(n, u0, v0, [], rc, rs)
    ref, _ = model(pivots, u0, v0, [], rc, rs)
    for i in range(len(data)):
        m = group == i
        z0[2 + order + i] = np.average(y[m] - th[m] + ref[i], weights=1 / s[m] ** 2)
    sol = least_squares(res, z0, jac=jac, method="lm", x_scale="jac",
                        ftol=1e-11, xtol=1e-11, gtol=1e-11)
    if not sol.success:
        raise ValueError(f"joint order-{order} fit failed: {sol.message}")
    u, v, bs = unpack(sol.x)
    dof = len(n) - len(z0)
    chi2 = float(sol.fun @ sol.fun)
    J = jac(sol.x)
    scale = np.sqrt(np.sum(J ** 2, axis=0))
    cov = np.linalg.inv((J / scale).T @ (J / scale)) / np.outer(scale, scale)
    cov *= max(1.0, chi2 / dof)  # same uncertainty floor as geo.Ladder.fit
    cov = cov[:2, :2] * np.outer([u0 * 1e-5, v0 * 1e-5], [u0 * 1e-5, v0 * 1e-5])
    ref, _ = model(pivots, u, v, bs, rc, rs)
    resid = np.degrees(prediction(sol.x) - y)
    return dict(u=u, v=v, b=list(bs), c=sol.x[2 + order:] - ref, cov=cov,
                chi2=chi2, dof=dof, rms_deg=float(np.sqrt(np.mean(resid ** 2))),
                resid_deg=resid, r_bits=model(n, u, v, bs, rc, rs)[1])


def merged_summary(data, runs, c):
    """geo's constant-pitch report, with joint covariance and explicit per-run provenance."""
    bit = data[0][3]["bit_nm_assumed"]
    b = bit * 1e-6
    u, v, cov = c["u"], c["v"], c["cov"]
    media = data[0][3].get("media", "dvd")
    sector_bits = 57624 if media == "cd" else 38688
    summaries = [json.load(open(os.path.join(run, "summary.json"))) for run in runs]
    n = np.concatenate([d[0] for d in data])
    lo, hi = float(n.min()), float(n.max())
    radius = lambda nn: b * np.sqrt(u * u + v * nn / math.pi)

    def gradient(nn):
        r = np.sqrt(u * u + v * nn / math.pi)
        return np.array([-2 * nn / (r * (r + u)), -nn * nn / (math.pi * r * (r + u) ** 2)])

    def sigma(nlo, nhi):
        g = gradient(nhi) - gradient(nlo)
        return math.degrees(math.sqrt(max(0.0, float(g @ cov @ g))))

    span = [25.0, 58.0] if media == "cd" else list(TWIST_SPAN_MM)
    nlo, nhi = [max(0.0, math.pi * ((r / b) ** 2 - u * u) / v) for r in span]
    totals = {int(k) for d in data for k in
              d[3].get("dis_equivalent", {}).get("outer_radius_mm_for_total_sectors", {})}
    totals.update(int(s["setup"]["last_lba"]) + 1 for s in summaries
                  if s.get("setup", {}).get("last_lba") is not None)
    if not totals and media == "dvd":
        totals.update((2295104, 2298496))
    per_run = [dict(run=run, c_deg=math.degrees(float(offset)),
                    reference_lba=d[3].get("reference_lba"), period_ms=d[3].get("period_ms"))
               for run, d, offset in zip(runs, data, c["c"])]
    fit_report = dict(u=u, v=v, coarse_u=u, coarse_v=v,
                      u_sigma=math.sqrt(cov[0, 0]), v_sigma=math.sqrt(cov[1, 1]),
                      r0_mm_at_bit=u * b, pitch_um_at_bit=v * bit * 1e-3,
                      bit_nm_assumed=bit, measured_span_mm=[round(radius(lo), 3), round(radius(hi), 3)],
                      angle_span_mm=span, angle_sigma_deg=sigma(nlo, nhi),
                      angle_sigma_measured_span_deg=sigma(lo, hi),
                      chi2_per_dof=c["chi2"] / c["dof"], residual_rms_deg=c["rms_deg"],
                      c_deg=None, reference_lba=None, period_ms=None, per_run=per_run,
                      note="joint constant-pitch fit of the same disc; phase origins are per run",
                      dis_equivalent=dict(bit_nm=bit, inner_radius_mm=u * b,
                                          outer_radius_mm_for_total_sectors={
                                              str(total): float(radius(total * sector_bits))
                                              for total in sorted(totals)}))
    if any("media" in d[3] for d in data):
        fit_report["media"] = media
    if media == "cd":
        for key in ("sector_bits", "read_tail_frames", "read_completion_model_measured"):
            if key in data[0][3]:
                fit_report[key] = data[0][3][key]
        fit_report["dis_equivalent"]["note"] = (
            "CD forward CIRC reference origin, hardware origin unmeasured; not a DVD preset")
    else:
        fit_report["dis_equivalent"]["note"] = (
            "DiscImageStudio builds its spiral from inner radius, outer radius and track length "
            "(total sectors x 38688 x bit); use the outer radius for your disc's sector count")
    return dict(fit=fit_report, source_runs=list(runs))


def pooled_phi(data, c, rc, rs):
    n = np.concatenate([d[0] for d in data])
    y = np.concatenate([d[1] for d in data])
    group = np.repeat(np.arange(len(data)), [len(d[0]) for d in data])
    th, rad = model(n, c["u"], c["v"], [], rc, rs)
    phi = np.degrees(th - y)
    for i in range(len(data)):
        phi[group == i] -= phi[group == i].mean()
    return rad * data[0][3]["bit_nm_assumed"] * 1e-6, phi, group


def phi_design(r_mm, group, degree):
    # Shared powers, separate intercepts: offsets must also be refitted in every LOO fold.
    x = (r_mm - RC_MM) / RS_MM
    return np.column_stack([x ** p for p in range(degree, 0, -1)] +
                           [(group == i).astype(float) for i in range(group.max() + 1)])


def pooled_phi_table(r_mm, phi, group):
    print("\npooled phi(r), per-run offsets fitted; fit and leave-one-out rms (deg):")
    scores = {}
    for degree in range(2, min(13, len(phi) - group.max() - 2)):
        H = phi_design(r_mm, group, degree)
        hat = H @ np.linalg.pinv(H)
        e = phi - hat @ phi
        den = 1 - np.diag(hat)
        loo = float(np.sqrt(np.mean((e / den) ** 2))) if np.all(den > 1e-10) else float("inf")
        scores[degree] = loo
        print(f"  degree {degree:2d}  fit {np.sqrt(np.mean(e ** 2)):.3f}  leave-one-out {loo:.3f}")
    return min(scores, key=scores.get)


def phi_coefficients(r_mm, phi, group, degree):
    H = phi_design(r_mm, group, degree)
    if degree < 1 or np.linalg.matrix_rank(H) < H.shape[1] or len(phi) <= H.shape[1]:
        raise ValueError("--phi-degree needs a positive degree supported by the pooled rungs")
    coef = np.r_[np.linalg.lstsq(H, phi, rcond=None)[0][:degree], 0.0]
    grid = np.linspace(r_mm.min(), r_mm.max(), 400)
    coef[-1] -= np.polyval(coef, (grid - RC_MM) / RS_MM).mean()
    return coef


def multi_run(a, ap):
    from scipy.stats import f as fdist

    if a.write_correction and not a.write_summary:
        ap.error("multiple runs: --write-correction requires --write-summary; use both files together")
    if a.plot:
        ap.error("--plot supports one run only")
    data = [load(run) for run in a.runs]
    bit = data[0][3]["bit_nm_assumed"]
    media = data[0][3].get("media", "dvd")
    for run, d in zip(a.runs[1:], data[1:]):
        if d[3]["bit_nm_assumed"] != bit or d[3].get("media", "dvd") != media:
            ap.error(f"{run}: bit_nm_assumed/media mismatch; all runs must measure the SAME disc")
    if any(len(d[0]) <= 6 for d in data):
        ap.error("each run needs more than six rungs for constant/quadratic/cubic comparison")
    rc, rs = RC_MM / (bit * 1e-6), RS_MM / (bit * 1e-6)
    print(f"joint analysis: {len(data)} runs of the SAME disc, shared u, v, pitch; per-run phase offsets")
    print("\nindividual constant-pitch runs (c relative to each run's reference):")
    for i, (run, d) in enumerate(zip(a.runs, data), 1):
        f = d[3]
        print(f"  run{i}: {run}")
        print(f"    u {f['u']:.6f} +/- {f['u_sigma']:.6f}  v {f['v']:.9f} +/- {f['v_sigma']:.3e}  "
              f"c {f['c_deg']:+.3f} deg  span {f['measured_span_mm'][0]:.3f}-"
              f"{f['measured_span_mm'][1]:.3f} mm  rms {f['residual_rms_deg']:.3f} deg")
    constants_agree = True
    print("\npairwise constant models (rotation removed, 24-58 mm):")
    for i in range(len(data)):
        fi = data[i][3]
        r = np.linspace(*TWIST_SPAN_MM, 400)
        n = math.pi * ((r / (bit * 1e-6)) ** 2 - fi["u"] ** 2) / fi["v"]
        thi, _ = model(n, fi["u"], fi["v"], [], rc, rs)
        for j in range(i + 1, len(data)):
            fj = data[j][3]
            du = (fj["u"] - fi["u"]) / math.hypot(fi["u_sigma"], fj["u_sigma"])
            dv = (fj["v"] - fi["v"]) / math.hypot(fi["v_sigma"], fj["v_sigma"])
            thj, _ = model(n, fj["u"], fj["v"], [], rc, rs)
            twist = np.degrees(thj - thi)
            twist -= twist.mean()
            print(f"  run{j + 1}-run{i + 1}: du {fj['u'] - fi['u']:+.6f} ({du:+.2f} sigma)  "
                  f"dv {fj['v'] - fi['v']:+.3e} ({dv:+.2f} sigma)  "
                  f"twist p-p {np.ptp(twist):.3f} deg  rms {np.sqrt(np.mean(twist ** 2)):.3f} deg")
            constants_agree &= (np.ptp(twist) <= REPRO_TWIST_PP_DEG and
                                max(abs(du), abs(dv)) <= REPRO_DELTA_SIGMA)
    fits = {}
    print("\njoint pitch fits:")
    for name, order in (("constant", 0), ("quadratic", 2), ("cubic", 3)):
        f = fits[name] = joint_fit(data, order, rc, rs)
        print(f"  {name:9s} chi2/dof {f['chi2'] / f['dof']:8.2f} ({f['chi2']:.3f}/{f['dof']})  "
              f"rms {f['rms_deg']:.3f} deg  u {f['u']:.6f}  v {f['v']:.9f}  "
              f"b = {', '.join(f'{x:+.3e}' for x in f['b']) or '-'}")
    c = fits["constant"]
    summary = merged_summary(data, a.runs, c)
    summ = summary["fit"]
    print(f"  constant sigma: u {summ['u_sigma']:.6f}  v {summ['v_sigma']:.3e}; "
          f"union span {summ['measured_span_mm'][0]:.3f}-{summ['measured_span_mm'][1]:.3f} mm")
    probabilities = {}
    print("\nF-test vs constant (weighted chi2, residual variance estimated):")
    for name in ("quadratic", "cubic"):
        f = fits[name]
        extra = c["dof"] - f["dof"]
        F = max(0.0, (c["chi2"] - f["chi2"]) / extra / (f["chi2"] / f["dof"]))
        probabilities[name] = float(fdist.sf(F, extra, f["dof"]))
        print(f"  {name:9s} F({extra},{f['dof']}) {F:.3f}  p {probabilities[name]:.6g}"
              f"{' (chosen pitch order)' if name == a.order else ''}")
    # Do the runs measure one spiral? One shared fit against one fit per run, same pitch order.
    orders = {"constant": 0, "quadratic": 2, "cubic": 3}
    separate, consistency = {}, {}
    print("\nrun consistency (one shared fit vs one fit per run, F-test):")
    for name in ("constant", a.order):
        separate[name] = [joint_fit([d], orders[name], rc, rs) for d in data]
        chi2 = sum(f["chi2"] for f in separate[name])
        dof = sum(f["dof"] for f in separate[name])
        extra = fits[name]["dof"] - dof
        F = max(0.0, (fits[name]["chi2"] - chi2) / extra / (chi2 / dof))
        consistency[name] = float(fdist.sf(F, extra, dof))
        print(f"  {name:9s} F({extra},{dof}) {F:.3f}  p {consistency[name]:.6g}")
    r_mm, phi, group = pooled_phi(data, c, rc, rs)
    best_degree = pooled_phi_table(r_mm, phi, group)
    grid_r = np.linspace(r_mm.min(), r_mm.max(), 400)
    grid_n = math.pi * ((grid_r / (bit * 1e-6)) ** 2 - c["u"] ** 2) / c["v"]
    th_const, _ = model(grid_n, c["u"], c["v"], [], rc, rs)
    coef = None
    if a.phi_degree is not None:
        coef = phi_coefficients(r_mm, phi, group, a.phi_degree)
        curve = np.polyval(coef, (grid_r - RC_MM) / RS_MM)
        chosen_p = probabilities[a.order]
        print(f"\nphi degree {a.phi_degree}: significance and reproducibility verdicts use the {a.order} pitch fits above")
    else:
        f = fits[a.order]
        curve = np.degrees(th_const - model(grid_n, f["u"], f["v"], f["b"], rc, rs)[0])
        curve -= curve.mean()
        chosen_p = probabilities[a.order]
    # Compare independent corrections in the same constant model, without extrapolating.
    lo = max(float(d[0].min()) for d in data)
    hi = min(float(d[0].max()) for d in data)
    differences = []
    print("\nindependent correction differences (rotation removed, common measured span):")
    if lo < hi:
        nn = np.linspace(lo, hi, 400)
        shared_th, shared_rad = model(nn, c["u"], c["v"], [], rc, rs)
        curves = []
        for k, d in enumerate(data):
            if a.phi_degree is not None:
                rr, pp, gg = pooled_phi([d], c, rc, rs)
                cc = phi_coefficients(rr, pp, gg, a.phi_degree)
                cc_curve = np.polyval(cc, (shared_rad * bit * 1e-6 - RC_MM) / RS_MM)
            else:
                local = separate[a.order][k]
                cc_curve = np.degrees(shared_th - model(nn, local["u"], local["v"], local["b"], rc, rs)[0])
            curves.append(cc_curve - cc_curve.mean())
        for i in range(len(curves)):
            for j in range(i + 1, len(curves)):
                diff = float(np.sqrt(np.mean((curves[j] - curves[i]) ** 2)))
                differences.append(diff)
                print(f"  run{j + 1}-run{i + 1}: rms {diff:.3f} deg")
    else:
        print("  unavailable: runs have no common measured span")
    correction_rms = float(np.sqrt(np.mean(curve ** 2)))
    tangent = grid_r * np.radians(curve)
    deviation = float(np.max(np.abs(tangent - np.polyval(np.polyfit(grid_r, tangent, 1), grid_r))))
    # a pairwise difference carries two runs' noise: per run rms(diff)/sqrt(2), pooled per-run/sqrt(N)
    noise = (float(np.sqrt(np.mean(np.square(differences)) / 2) / math.sqrt(len(data)))
             if differences else None)
    worthwhile = (chosen_p < WORTHWHILE_P and best_degree >= WORTHWHILE_LOO_DEGREE and
                  deviation >= STRAIGHTNESS_MM)
    print(f"\ncorrection: rms {correction_rms:.3f} deg  p-p {np.ptp(curve):.3f} deg  "
          f"straightness deviation {deviation:.3f} mm (max tangential departure from best line)")
    if worthwhile:
        # The correction is used, so the runs must agree on the shaped spiral.
        reproducible = consistency[a.order] >= REPRO_P
        rule = f"runs share one {a.order} pitch fit: F-test p {consistency[a.order]:.3g} >= {REPRO_P:g}"
    else:
        reproducible = constants_agree
        rule = f"twist p-p <= {REPRO_TWIST_PP_DEG:g} deg, |du| and |dv| <= {REPRO_DELTA_SIGMA:g} sigma"
    print(f"reproducible: {'yes' if reproducible else 'no'} ({rule})")
    print(f"correction worthwhile: {'yes' if worthwhile else 'no'} "
          f"(p < {WORTHWHILE_P:g}, best LOO degree {best_degree} >= {WORTHWHILE_LOO_DEGREE}, "
          f"straightness >= {STRAIGHTNESS_MM:g} mm)")
    if noise is None:
        print("suggest another run: unknown (no overlapping span for a noise estimate)")
    else:
        print(f"suggest another run: {'yes' if noise > NOISE_FRACTION * correction_rms else 'no'} "
              f"(pooled noise {noise:.3f} deg vs correction rms / 3 = {NOISE_FRACTION * correction_rms:.3f} deg)")
    if a.write_summary:
        parent = os.path.dirname(os.path.abspath(a.write_summary))
        os.makedirs(parent, exist_ok=True)
        with open(a.write_summary, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2)
        print(f"wrote {a.write_summary}: joint constant-pitch geometry; use with its correction")
    if a.write_correction and coef is not None:
        # Existing writer supplies the file convention; synthetic samples retain the shared polynomial.
        write_phi_correction(a.write_correction, grid_r, curve, a.phi_degree, " ".join(a.runs), summ)
    elif a.write_correction:
        write_correction(a.write_correction, fits[a.order], summ, " ".join(a.runs), a.order, rc, rs,
                         np.concatenate([d[0] for d in data]))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("runs", nargs="+", help="geo results folders (targets.csv, summary.json); SAME disc")
    ap.add_argument("--plot", help="write a residual plot here")
    ap.add_argument("--write-correction", help="write an angle-correction file for `image --correction`")
    ap.add_argument("--order", choices=("quadratic", "cubic"), default="quadratic",
                    help="which fit --write-correction uses")
    ap.add_argument("--phi-degree", type=int,
                    help="--write-correction fits phi(r) directly with this polynomial degree")
    ap.add_argument("--write-summary", help="write the joint constant-pitch summary for disexport/image --geo")
    a = ap.parse_args()
    if len(a.runs) > 1:
        try:
            return multi_run(a, ap)
        except (ValueError, np.linalg.LinAlgError) as e:
            ap.error(str(e))
    a.run = a.runs[0]
    n, y, s, summ = load(a.run)
    bit_nm = summ["bit_nm_assumed"]
    if a.write_summary:
        report = json.load(open(os.path.join(a.run, "summary.json")))
        report["source_runs"] = a.runs
        os.makedirs(os.path.dirname(os.path.abspath(a.write_summary)), exist_ok=True)
        with open(a.write_summary, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
    mm = lambda bits: bits * bit_nm * 1e-6
    rc, rs = RC_MM / (bit_nm * 1e-6), RS_MM / (bit_nm * 1e-6)
    fits = {}
    for name, order in (("constant", 0), ("quadratic", 2), ("cubic", 3)):
        if len(n) <= 3 + order:
            continue
        f = fits[name] = fit(n, y, s, summ["u"], summ["v"], order, rc, rs)
        print(f"{name:9s} chi2/dof {f['chi2'] / f['dof']:8.2f}  rms {f['rms_deg']:.3f} deg  "
              f"r0 {mm(f['u']):.5f} mm  pitch(40 mm) {mm(f['v']) * 1e3:.6f} um  "
              f"b = {', '.join(f'{x:+.3e}' for x in f['b']) or '-'}")
    c = fits["constant"]
    order = np.argsort(c["r_bits"])
    print("\nconstant-pitch residual vs radius:")
    for i in order:
        print(f"  {mm(c['r_bits'][i]):7.3f} mm  {c['resid_deg'][i]:+7.3f} deg  (+/- {np.degrees(s[i]):.3f})")
    th, rad = model(n, summ["u"], summ["v"], [], rc, rs)
    phi = np.degrees(th - y)
    phi -= phi.mean()
    phi_table(mm(rad), phi)
    if a.write_correction and a.phi_degree:
        write_phi_correction(a.write_correction, mm(rad), phi, a.phi_degree, a.run, summ)
    elif a.write_correction:
        write_correction(a.write_correction, fits[a.order], summ, a.run, a.order, rc, rs, n)
    if a.plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(7, 3.5))
        for name, f in fits.items():
            o = np.argsort(f["r_bits"])
            ax.errorbar(mm(f["r_bits"][o]), f["resid_deg"][o], yerr=np.degrees(s[o]), fmt="o-", ms=3,
                        capsize=2, label=f"{name} (rms {f['rms_deg']:.2f} deg)")
        ax.axhline(0, color="k", lw=0.5)
        ax.set_xlabel("radius (mm)")
        ax.set_ylabel("model - measured (deg)")
        ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(a.plot, dpi=130)
        print(f"\nplot: {a.plot}")


if __name__ == "__main__":
    sys.exit(main())
