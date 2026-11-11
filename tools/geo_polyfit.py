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

Several folders of the SAME disc are fitted jointly: shared u, v and pitch, one phase constant
per run. --write-correction then requires --write-summary; pass both to `disexport` or
`image --geo`, naming the summary explicitly (`--geo latest` skips it). The correction covers
the union measured span. A stopped or partial source run carries over to the merged summary,
so `disexport --install` refuses it as it would that run.

The verdicts judge the model in use: the chosen correction if worthwhile, else constant pitch.
- run consistency: one shared fit against one fit per run (F-test). No conflict is not proof
  of agreement.
- agreement: each pair of runs' own corrections, tangentially at the worst radius of their
  common span, 2 sigma against --tolerance-mm (0.3 mm, a rough empirical default): within,
  beyond or inconclusive.
- suggest another run: on a conflict, or where the merged 2-sigma band exceeds the tolerance.
When a verdict is a conflict or inconclusive, check and refine the result with the rest of the
calibration, such as a test burn and a photo fit in DiscImageStudio.
"""
import argparse
import csv
import hashlib
import json
import math
import os
import sys

import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from discprobe.numerics import least_squares

RC_MM, RS_MM = 40.0, 15.0
CONSISTENCY_P = 0.01
TOLERANCE_MM = 0.3  # rough empirical default for --tolerance-mm, still to be refined
AGREE_Z = 2.0
WORTHWHILE_P = 0.01
WORTHWHILE_LOO_DEGREE = 3
STRAIGHTNESS_MM = 0.05
ANGLE_SPAN_MM = (24.0, 58.0)
GEO_FILES = ("targets.csv", "summary.json", "events.csv")


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
    units = np.r_[u0 * 1e-5, v0 * 1e-5, [1e-5] * order]
    cov = cov[:2 + order, :2 + order] * np.outer(units, units)  # (u, v, b...)
    ref, _ = model(pivots, u, v, bs, rc, rs)
    resid = np.degrees(prediction(sol.x) - y)
    return dict(u=u, v=v, b=list(bs), c=sol.x[2 + order:] - ref, cov=cov[:2, :2], cov_full=cov,
                chi2=chi2, dof=dof, rms_deg=float(np.sqrt(np.mean(resid ** 2))),
                resid_deg=resid, r_bits=model(n, u, v, bs, rc, rs)[1])


def merged_summary(data, runs, c):
    """geo's constant-pitch report, with joint covariance and explicit per-run provenance."""
    bit = data[0][3]["bit_nm_assumed"]
    b = bit * 1e-6
    u, v, cov = c["u"], c["v"], c["cov"]
    media = data[0][3].get("media", "dvd")
    sector_bits = 57624 if media == "cd" else 38688
    summaries = []
    for run in runs:
        with open(os.path.join(run, "summary.json"), encoding="utf-8") as fh:
            summaries.append(json.load(fh))
    n = np.concatenate([d[0] for d in data])
    lo, hi = float(n.min()), float(n.max())
    radius = lambda nn: b * np.sqrt(u * u + v * nn / math.pi)

    def gradient(nn):
        r = np.sqrt(u * u + v * nn / math.pi)
        return np.array([-2 * nn / (r * (r + u)), -nn * nn / (math.pi * r * (r + u) ** 2)])

    def sigma(nlo, nhi):
        g = gradient(nhi) - gradient(nlo)
        return math.degrees(math.sqrt(max(0.0, float(g @ cov @ g))))

    span = [25.0, 58.0] if media == "cd" else list(ANGLE_SPAN_MM)
    nlo, nhi = [max(0.0, math.pi * ((r / b) ** 2 - u * u) / v) for r in span]
    totals = {int(k) for d in data for k in
              d[3].get("dis_equivalent", {}).get("outer_radius_mm_for_total_sectors", {})}
    totals.update(int(s["setup"]["last_lba"]) + 1 for s in summaries
                  if s.get("setup", {}).get("last_lba") is not None)
    if not totals and media == "dvd":
        totals.update((2295104, 2298496))
    per_run = []
    for run, d, s, offset in zip(runs, data, summaries, c["c"]):
        entry = dict(run=run, c_deg=math.degrees(float(offset)),
                     reference_lba=d[3].get("reference_lba"), period_ms=d[3].get("period_ms"))
        if "completion_status" in d[3]:
            entry["completion_status"] = d[3]["completion_status"]
        if s.get("stopped"):
            entry["stopped"] = s["stopped"]
        if (d[3].get("state_check") or {}).get("verdict"):
            entry["state_check"] = d[3]["state_check"]["verdict"]
        per_run.append(entry)
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
    # A preset outlives the runs: keep what makes `disexport --install` refuse a source run.
    partial = next((d[3]["completion_status"] for d in data
                    if d[3].get("completion_status", "target_reached") != "target_reached"), None)
    if partial:
        fit_report["completion_status"] = partial
    # Likewise a source run whose check points moved: two runs that drifted the same way agree with
    # each other, so the merge must not wash the verdict out (the 6pro audit of 1f7f92e).
    verdicts = [(run, (d[3].get("state_check") or {}).get("verdict")) for run, d in zip(runs, data)]
    changed = [run for run, verdict in verdicts if verdict == "changed"]
    if changed:
        fit_report["state_check"] = dict(verdict="changed", runs=changed,
                                         note="a source run's check points moved; see that run")
    elif verdicts and all(verdict == "steady" for _, verdict in verdicts):
        fit_report["state_check"] = dict(verdict="steady", runs=list(runs))
    elif any(verdict for _, verdict in verdicts):
        fit_report["state_check"] = dict(verdict="inconclusive", runs=[run for run, v in verdicts if v != "steady"],
                                         note="not every source run showed steady check points")
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
    stopped = [f"{run}: {s['stopped']}" for run, s in zip(runs, summaries) if s.get("stopped")]
    return dict(fit=fit_report, source_runs=list(runs), **({"stopped": "; ".join(stopped)} if stopped else {}))


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


def phi_fit(r_mm, phi, group, degree):
    """Shared powers and per-run offsets by least squares: (powers, their covariance, rss, dof), or None."""
    H = phi_design(r_mm, group, degree)
    dof = len(phi) - H.shape[1]
    if np.linalg.matrix_rank(H) < H.shape[1] or dof <= 0:
        return None
    z, *_ = np.linalg.lstsq(H, phi, rcond=None)
    rss = float(np.sum((phi - H @ z) ** 2))
    cov = np.linalg.inv(H.T @ H) * rss / dof
    return z[:degree], cov[:degree, :degree], rss, dof


def phi_coefficients(r_mm, phi, group, degree):
    found = phi_fit(r_mm, phi, group, degree) if degree >= 1 else None
    if found is None:
        raise ValueError("--phi-degree needs a positive degree supported by the pooled rungs")
    coef = np.r_[found[0], 0.0]
    grid = np.linspace(r_mm.min(), r_mm.max(), 400)
    coef[-1] -= np.polyval(coef, (grid - RC_MM) / RS_MM).mean()
    return coef


def phi_jacobian(r_mm, degree):
    """d curve / d powers of a mean-removed phi polynomial sampled at r_mm."""
    x = (r_mm - RC_MM) / RS_MM
    J = np.column_stack([x ** p for p in range(degree, 0, -1)])
    return J - J.mean(axis=0)


def pitch_curve(f, nn, th_ref, rc, rs):
    """Mean-removed correction of a pitch fit against th_ref at nn (deg), and its 1-sigma band."""
    p0 = np.r_[f["u"], f["v"], f["b"]]

    def curve(p):
        c = np.degrees(th_ref - model(nn, p[0], p[1], p[2:], rc, rs)[0])
        return c - c.mean()

    cov = f["cov_full"]
    steps = np.sqrt(np.diag(cov))
    J = np.column_stack([(curve(p0 + h) - curve(p0 - h)) / (2 * h[k])
                         for k, h in enumerate(np.diag(np.where(steps > 0, steps, 1e-9)))])
    return curve(p0), np.sqrt(np.einsum("ij,jk,ik->i", J, cov, J))


def nested_f(small, big):
    """p of the extra parameters of `big` over `small`, each (chi2, dof), residual variance estimated."""
    from discprobe.numerics import f_sf

    extra = small[1] - big[1]
    if extra <= 0 or big[1] <= 0:
        return float("nan"), float("nan"), extra
    if big[0] <= 0:
        return float("inf"), 0.0 if small[0] > 0 else 1.0, extra
    F = max(0.0, (small[0] - big[0]) / extra / (big[0] / big[1]))
    return F, float(f_sf(F, extra, big[1])), extra


def same_file(a, b):
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def check_paths(a, ap):
    """Refuse repeated inputs, which would fake agreement, and outputs that would overwrite a run."""
    seen = {}
    for run in a.runs:
        if any(same_file(run, other) for other in seen):
            ap.error(f"{run}: the same run folder is given twice")
        try:
            with open(os.path.join(run, "targets.csv"), "rb") as fh:
                digest = hashlib.sha256(fh.read()).hexdigest()
        except OSError:
            continue  # load() reports a missing run
        twin = next((other for other, d in seen.items() if d == digest), None)
        if twin is not None:
            ap.error(f"{run}: targets.csv is identical to {twin}'s; one measurement is not two runs")
        seen[run] = digest
    outputs = [(flag, path) for flag, path in (("--write-summary", a.write_summary),
                                               ("--write-correction", a.write_correction),
                                               ("--plot", a.plot)) if path]
    for flag, path in outputs:
        for run in a.runs:
            for name in GEO_FILES:
                if same_file(path, os.path.join(run, name)):
                    ap.error(f"{flag} {path} would overwrite {name} of {run}")
    for i, (flag, path) in enumerate(outputs):
        for other_flag, other in outputs[i + 1:]:
            if same_file(path, other):
                ap.error(f"{flag} and {other_flag} name the same file {path}")


def simulated(run):
    """A geo-SIM- folder, or a summary that says so, as discprobe.guide reads them."""
    if os.path.basename(os.path.normpath(run)).startswith("geo-SIM-"):
        return True
    with open(os.path.join(run, "summary.json"), encoding="utf-8") as fh:
        return json.load(fh).get("simulated") is True


def multi_run(a, ap):
    if a.write_correction and not a.write_summary:
        ap.error("multiple runs: --write-correction requires --write-summary; use both files together")
    if a.plot:
        ap.error("--plot supports one run only")
    if not a.tolerance_mm > 0:
        ap.error("--tolerance-mm must be positive")
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
    sims = [run for run in a.runs if simulated(run)]
    if sims:
        print(f"SIMULATED: {', '.join(sims)}; nothing here describes a real disc, do not burn from it")
    print("\nindividual constant-pitch runs (c relative to each run's reference):")
    for i, (run, d) in enumerate(zip(a.runs, data), 1):
        f = d[3]
        print(f"  run{i}: {run}")
        print(f"    u {f['u']:.6f} +/- {f['u_sigma']:.6f}  v {f['v']:.9f} +/- {f['v_sigma']:.3e}  "
              f"c {f['c_deg']:+.3f} deg  span {f['measured_span_mm'][0]:.3f}-"
              f"{f['measured_span_mm'][1]:.3f} mm  rms {f['residual_rms_deg']:.3f} deg")
    fits = {}
    print("\njoint pitch fits:")
    for name, order in (("constant", 0), ("quadratic", 2), ("cubic", 3)):
        f = fits[name] = joint_fit(data, order, rc, rs)
        print(f"  {name:9s} chi2/dof {f['chi2'] / f['dof']:8.2f} ({f['chi2']:.3f}/{f['dof']})  "
              f"rms {f['rms_deg']:.3f} deg  u {f['u']:.6f}  v {f['v']:.9f}  "
              f"b = {', '.join(f'{x:+.3e}' for x in f['b']) or '-'}")
    c = fits["constant"]
    summary = merged_summary(data, a.runs, c)
    if sims:
        summary["simulated"] = True
    summ = summary["fit"]
    print(f"  constant sigma: u {summ['u_sigma']:.6f}  v {summ['v_sigma']:.3e}; "
          f"union span {summ['measured_span_mm'][0]:.3f}-{summ['measured_span_mm'][1]:.3f} mm")
    r_mm, phi, group = pooled_phi(data, c, rc, rs)
    phi_shared = None
    if a.phi_degree is not None:
        coef = phi_coefficients(r_mm, phi, group, a.phi_degree)
        phi_shared = phi_fit(r_mm, phi, group, a.phi_degree)
    chosen = f"phi degree {a.phi_degree}" if a.phi_degree is not None else a.order
    probabilities = {}
    print("\nF-test vs constant (weighted chi2, residual variance estimated):")
    for name in ("quadratic", "cubic"):
        f = fits[name]
        F, probabilities[name], extra = nested_f((c["chi2"], c["dof"]), (f["chi2"], f["dof"]))
        print(f"  {name:9s} F({extra},{f['dof']}) {F:.3f}  p {probabilities[name]:.6g}"
              f"{' (chosen pitch order)' if name == chosen else ''}")
    if phi_shared is not None:
        null = (float(np.sum(phi ** 2)), len(phi) - len(data))  # phi is already centred per run
        F, probabilities[chosen], extra = nested_f(null, phi_shared[2:])
        print(f"  {chosen} on the constant-pitch residuals (unweighted): F({extra},{phi_shared[3]}) "
              f"{F:.3f}  p {probabilities[chosen]:.6g} (chosen)")
    # Do the runs measure one spiral? One shared fit against one fit per run, same model.
    separate, consistency = {}, {}
    print("\nrun consistency (one shared fit vs one fit per run, F-test):")
    for name in ("constant", a.order):
        separate[name] = [joint_fit([d], len(fits[name]["b"]), rc, rs) for d in data]
        mine = (sum(f["chi2"] for f in separate[name]), sum(f["dof"] for f in separate[name]))
        F, consistency[name], extra = nested_f((fits[name]["chi2"], fits[name]["dof"]), mine)
        print(f"  {name:9s} F({extra},{mine[1]}) {F:.3f}  p {consistency[name]:.6g}")
    if phi_shared is not None:
        own = [phi_fit(r_mm[group == k], phi[group == k], np.zeros((group == k).sum(), int), a.phi_degree)
               for k in range(len(data))]
        separate[chosen] = own
        if any(o is None for o in own):
            consistency[chosen] = None
            print(f"  {chosen}: unavailable, a run has too few rungs for its own polynomial")
        else:
            mine = (sum(o[2] for o in own), sum(o[3] for o in own))
            F, consistency[chosen], extra = nested_f(phi_shared[2:], mine)
            print(f"  {chosen} F({extra},{mine[1]}) {F:.3f}  p {consistency[chosen]:.6g}")
    best_degree = pooled_phi_table(r_mm, phi, group)
    grid_r = np.linspace(r_mm.min(), r_mm.max(), 400)
    grid_n = math.pi * ((grid_r / (bit * 1e-6)) ** 2 - c["u"] ** 2) / c["v"]
    th_const, _ = model(grid_n, c["u"], c["v"], [], rc, rs)
    if phi_shared is not None:
        curve = np.polyval(coef, (grid_r - RC_MM) / RS_MM)
    else:
        curve, _ = pitch_curve(fits[a.order], grid_n, th_const, rc, rs)
    correction_rms = float(np.sqrt(np.mean(curve ** 2)))
    tangent = grid_r * np.radians(curve)
    deviation = float(np.max(np.abs(tangent - np.polyval(np.polyfit(grid_r, tangent, 1), grid_r))))
    worthwhile = (probabilities[chosen] < WORTHWHILE_P and best_degree >= WORTHWHILE_LOO_DEGREE and
                  deviation >= STRAIGHTNESS_MM)
    used = chosen if worthwhile else "constant"  # the model a user is told to rely on
    print(f"\ncorrection: rms {correction_rms:.3f} deg  p-p {np.ptp(curve):.3f} deg  "
          f"straightness deviation {deviation:.3f} mm (max tangential departure from best line)")
    if used == chosen and phi_shared is not None:
        J = phi_jacobian(grid_r, a.phi_degree)
        band = np.sqrt(np.einsum("ij,jk,ik->i", J, phi_shared[1], J))
    else:
        _, band = pitch_curve(fits[used], grid_n, th_const, rc, rs)
    tangent_band = grid_r * np.radians(band)
    k = int(np.argmax(tangent_band))
    print(f"merged {used} uncertainty (1 sigma, rotation removed): up to {band.max():.3f} deg, "
          f"{tangent_band[k]:.3f} mm tangential at {grid_r[k]:.1f} mm")
    # Each pair of runs' own corrections, in one reference spiral, without extrapolating.
    lo = max(float(d[0].min()) for d in data)
    hi = min(float(d[0].max()) for d in data)
    states = []
    print(f"\nagreement of each run's own {used} correction (rotation removed, common measured span, "
          f"tolerance {a.tolerance_mm:g} mm, {AGREE_Z:g} sigma):")
    if lo >= hi:
        print("  unavailable: runs have no common measured span")
    elif used == chosen and phi_shared is not None and consistency[chosen] is None:
        print("  unavailable: a run has too few rungs for its own polynomial")
    else:
        nn = np.linspace(lo, hi, 400)
        shared_th, shared_rad = model(nn, c["u"], c["v"], [], rc, rs)
        rr = shared_rad * bit * 1e-6
        curves = []
        for kk in range(len(data)):
            if used == chosen and phi_shared is not None:
                J = phi_jacobian(rr, a.phi_degree)
                powers, cov = separate[chosen][kk][:2]
                curves.append((J @ powers, np.einsum("ij,jk,ik->i", J, cov, J)))
            else:
                cc, sd = pitch_curve(separate[used][kk], nn, shared_th, rc, rs)
                curves.append((cc, sd ** 2))
        for i in range(len(curves)):
            for j in range(i + 1, len(curves)):
                diff = rr * np.radians(curves[j][0] - curves[i][0])
                sd = rr * np.radians(np.sqrt(curves[i][1] + curves[j][1]))
                if np.any(np.abs(diff) - AGREE_Z * sd > a.tolerance_mm):
                    state = "beyond"
                elif np.all(np.abs(diff) + AGREE_Z * sd < a.tolerance_mm):
                    state = "within"
                else:
                    state = "inconclusive"
                states.append(state)
                k = int(np.argmax(np.abs(diff)))
                print(f"  run{j + 1}-run{i + 1}: max {np.abs(diff).max():.3f} mm at {rr[k]:.1f} mm "
                      f"(rms {np.degrees(np.sqrt(np.mean((diff / rr) ** 2))):.3f} deg), "
                      f"1 sigma up to {sd.max():.3f} mm: {state}")
    agreement = max(states, key=("within", "inconclusive", "beyond").index) if states else None
    p = consistency[used]
    print("\nverdicts (hints only):")
    if p is None:
        print(f"run consistency: unavailable ({used})")
    else:
        print(f"run consistency: {'conflict' if p < CONSISTENCY_P else 'no conflict found'} "
              f"({used}: shared vs per-run F-test p {p:.3g}, conflict below {CONSISTENCY_P:g}; "
              f"no conflict is not proof of agreement)")
    if agreement is None:
        print("agreement: unavailable")
    else:
        print(f"agreement: {agreement} {a.tolerance_mm:g} mm (worst pair; tolerance is a rough empirical "
              f"value, --tolerance-mm to change)")
    print(f"correction worthwhile: {'yes' if worthwhile else 'no'} "
          f"(p < {WORTHWHILE_P:g}, best LOO degree {best_degree} >= {WORTHWHILE_LOO_DEGREE}, "
          f"straightness >= {STRAIGHTNESS_MM:g} mm)")
    # More runs narrow the merged band, not the pairwise differences of the runs already taken.
    known = grid_r[AGREE_Z * tangent_band < a.tolerance_mm]
    moved = (summary["fit"].get("state_check") or {}).get("verdict") == "changed"
    if moved:
        print("suggest another run: yes (the check points of "
              f"{', '.join(summary['fit']['state_check']['runs'])} moved during the run: agreeing runs can share "
              "that drift, so install from new runs whose check points held)")
    elif (p is not None and p < CONSISTENCY_P) or agreement == "beyond":
        print("suggest another run: yes (the runs disagree; another one shows which is off)")
    elif len(known) == len(grid_r):
        print(f"suggest another run: no (merged {AGREE_Z:g} sigma band within {a.tolerance_mm:g} mm everywhere)")
    else:
        where = f"only {known.min():.1f}-{known.max():.1f} mm" if len(known) else "nowhere"
        print(f"suggest another run: yes (merged {AGREE_Z:g} sigma band within {a.tolerance_mm:g} mm {where} "
              f"of {grid_r[0]:.1f}-{grid_r[-1]:.1f} mm)")
    if a.write_summary:
        parent = os.path.dirname(os.path.abspath(a.write_summary))
        os.makedirs(parent, exist_ok=True)
        with open(a.write_summary, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2)
        print(f"wrote {a.write_summary}: joint constant-pitch geometry; use with its correction")
    if a.write_correction and phi_shared is not None:
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
    ap.add_argument("--tolerance-mm", type=float, default=TOLERANCE_MM,
                    help=f"several runs: tangential difference counted as agreement (default {TOLERANCE_MM:g}, "
                         "a rough empirical value)")
    a = ap.parse_args()
    check_paths(a, ap)
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
        if simulated(a.run):
            report["simulated"] = True
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
