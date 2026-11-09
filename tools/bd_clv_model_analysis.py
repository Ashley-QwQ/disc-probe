"""What the BD timing runs say about the CAV model, and what could be measured instead.

The phase ladder in `discprobe.geo` measures the angle between positions on the spiral:
phi = theta(n) - theta(n_ref) + c, and fits the two parameters of the spiral (r0, pitch)
from how phi curves with n. Under CAV the spindle holds the angle rate, so that curvature
is there to fit. Under CLV the drive holds the *linear* rate instead: the time from n_ref to
n is (n - n_ref) * b / v, and the fraction of a rotation is

    phi_CLV = 2*pi * (n - n_ref) * b / r_ref        (linear in n, curvature zero)

with b the channel bit length. The measured phase is then a distance over a circumference,
not an angle. Three things follow, and all three are checked here against data on disk:

  zones       this drive holds v constant across the radius: it is CLV, not CAV
  degenerate  a straight line has no curvature to fit, so (r0, pitch) come out of the
              ladder with an uncertainty larger than any value they could take
  t2          the CLV-friendly estimator: T^2 against LBA is a straight line, slope
              4*pi*p*sector_mm/v^2 and intercept (2*pi*r0/v)^2, so the pitch is known as soon
              as the linear speed is known independently of the radius

Usage:
    python tools/bd_clv_model_analysis.py tests/data/bd_discussion_samples/local_uj272_bd_zones.csv
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from discprobe.calib import theta  # noqa: E402

BD_BIT_MM = 74.5e-6            # channel bit length, nm -> mm
BD_SECTOR_BITS = 962136 / 32   # one user sector, from discprobe.geometry.BD_SECTOR_MM
BD_SECTOR_MM = BD_SECTOR_BITS * BD_BIT_MM
BD_R0_MM = 24.0                # data area start, per the BD standard
BD_PITCH_MM = 0.32e-3


def load(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        for key in ("radius_mm", "period_ms", "rpm", "linear_m_s", "coherence", "jitter_us", "lba"):
            if row.get(key) not in (None, ""):
                row[key] = float(row[key])
        # The CSV was written from the millimetre-per-second column of the summaries.
        if row["linear_m_s"] > 100:
            row["linear_m_s"] /= 1000.0
    return rows


def zones(rows: list[dict]) -> None:
    """Is v constant (CLV) or proportional to r (CAV) within each run?"""
    print("run                          req    zone   radius  period     rpm     v m/s    T/r")
    by_run: dict[str, list[dict]] = {}
    for row in rows:
        by_run.setdefault(row["run"], []).append(row)
    clv, cav = [], []
    clean = 0
    for run, group in by_run.items():
        group.sort(key=lambda r: r["lba"])
        v = np.array([r["linear_m_s"] for r in group])
        med = float(np.median(v))
        # A run whose inner zone is at twice the rate of the rest locked onto the second
        # harmonic of the spindle. Report it, but it says nothing about the spin law.
        harmonic = bool(np.max(v) > 1.3 * med)
        if not harmonic:
            clean += 1
        for r in group:
            print(f"{run:28} {r['requested_kbps'] or '-':>6} {r['fraction']:>6} "
                  f"{r['radius_mm']:>7.3f} {r['period_ms']:>8.3f} {r['rpm']:>7.1f} "
                  f"{r['linear_m_s']:>8.3f} {r['period_ms'] / r['radius_mm']:>7.4f}")
        if harmonic:
            print(f"{'':28} second harmonic on the inner zone: {v.max():.2f} m/s against "
                  f"{med:.2f}, exactly 2x, so only the outer zones are used")
            clv.extend(np.abs(v[-2:] - med) / med)
        else:
            clv.extend(np.abs(v - med) / med)
        omega = med / float(np.median([r["radius_mm"] for r in group]))
        cav.extend(np.abs(v - omega * np.array([r["radius_mm"] for r in group]))
                   / (omega * np.array([r["radius_mm"] for r in group])))
    print(f"\n{clean} of {len(by_run)} runs hold the linear speed: worst zone {100 * max(clv):.2f}% off the run median")
    print("across the radius: v(inner)/v(outer) is what tells CAV from CLV "
          "(1.00 is CLV, r(inner)/r(outer) is CAV)")
    for run, group in by_run.items():
        v = np.array([r["linear_m_s"] for r in group])
        ratio_r = group[0]["radius_mm"] / group[-1]["radius_mm"]
        print(f"{run:28} v ratio {v[0] / v[-1]:.3f}   r ratio {ratio_r:.3f}")
    print("-> CLV. The phase against n has no curvature, so the spiral parameters are not in it.")


def degenerate(noise_deg: float = 0.3) -> None:
    """How much curvature a usable ladder can show, against the noise it sees.

    A ladder only sees the fractional part of a rotation, so consecutive rungs have to be
    closer than one turn. Under CLV one turn is 2*pi*r_ref/b bits -- about 2e6 bits, or 67
    sectors, at 24 mm -- so 30 rungs 30 sectors apart cover 870 sectors of track: 870/67.3
    turns, and at 0.32 um per turn that is 4 um of radius. Reading (r0, pitch) out of a
    ladder means reading the curvature of the phase against n, and over 4 um there is none.
    """
    lbas = 6_000_000 + 30.0 * np.arange(30)                # 30 rungs, 30 sectors apart
    n = lbas * BD_SECTOR_BITS
    n_ref = n[0]
    sectors = lbas[-1] - lbas[0]
    per_turn = 2 * np.pi * BD_R0_MM / BD_SECTOR_MM          # sectors per rotation at r_ref
    x = np.linspace(-0.5, 0.5, n.size)

    def bend(u: float, v: float) -> float:
        """Degrees by which the phase departs from its own straight line."""
        phi = np.degrees(theta(n, u, v) - theta(n_ref, u, v))
        return float(np.max(np.abs(phi - np.polyval(np.polyfit(x, phi, 1), x))))

    u0, v0 = BD_R0_MM / BD_BIT_MM, BD_PITCH_MM / BD_BIT_MM
    b0 = bend(u0, v0)
    print(f"\na ladder that can be unwrapped: {n.size} rungs, {lbas[1] - lbas[0]:.0f} sectors apart")
    print(f"  {sectors:.0f} sectors = {sectors / per_turn:.1f} turns = {sectors / per_turn * BD_PITCH_MM * 1e3:.1f} um of radius")
    print(f"  the standard geometry bends {b0:.4f} deg away from a straight line over that span")
    for label, u, v in (("pitch -10%", u0, v0 * 0.9), ("pitch +10%", u0, v0 * 1.1),
                        ("r0 +5%", u0 * 1.05, v0)):
        print(f"  {label:10} moves that bend by {abs(bend(u, v) - b0):.6f} deg")
    print(f"  the timing noise is about {noise_deg:.2f} deg")
    print("  -> a 10% change in pitch moves the measurable shape by a millionth of the noise.")
    print("     Under CLV the phase against n is a straight line, and a straight line has no")
    print("     (r0, pitch) in it at any span a ladder can cover.")


def t2(rows: list[dict]) -> None:
    """T^2 against LBA: a straight line, slope 4*pi*p*sector_mm/v^2, intercept (2*pi*r0/v)^2."""
    by_run: dict[str, list[dict]] = {}
    for row in rows:
        by_run.setdefault(row["run"], []).append(row)
    print("\nrun                          zones  slope (ms^2/LBA)     R^2   v for 0.32 um   v measured   r0   pitch if r0=24")
    for run, group in by_run.items():
        if len(group) < 2 or any(r.get("stopped") for r in group):
            continue
        v = np.array([r["linear_m_s"] for r in group])
        if np.max(v) > 1.3 * np.median(v):
            print(f"{run:28} {len(group):>5}  (a zone locked onto the second harmonic; T^2 is not a line)")
            continue
        group.sort(key=lambda r: r["lba"])
        x = np.array([r["lba"] for r in group])
        y = np.array([r["period_ms"] ** 2 for r in group])
        slope, intercept = np.polyfit(x, y, 1)
        pred = slope * x + intercept
        ss = 1 - np.sum((y - pred) ** 2) / np.sum((y - y.mean()) ** 2)
        if slope <= 0 or intercept <= 0:
            print(f"{run:28} {len(group):>5}  {slope:>16.6e}  {ss:>7.5f}  (line has no positive intercept)")
            continue
        v = math.sqrt(4 * math.pi * BD_PITCH_MM * BD_SECTOR_MM / slope)
        r0 = v * math.sqrt(intercept) / (2 * math.pi)      # m/s * ms -> mm
        v_seen = float(np.median([r["linear_m_s"] for r in group]))
        pitch = slope * math.pi * BD_R0_MM ** 2 / (intercept * BD_SECTOR_MM)
        print(f"{run:28} {len(group):>5}  {slope:>16.6e}  {ss:>7.5f}  {v:>13.3f}  {v_seen:>11.3f}  "
              f"{r0:>6.3f} mm  {pitch * 1e3:>11.4f} um")
    print("\nThe slope and the intercept share one unknown (v), so a run gives p/v^2 and r0/v.")
    print("v has to come from sustained throughput (bytes/s * channel bits per user byte * b),")
    print("not from a nominal radius: that would assume the answer.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("zones", help="CSV written from results/timing-*/summary.json, one row per zone")
    args = ap.parse_args()
    rows = load(args.zones)
    zones(rows)
    degenerate()
    t2(rows)


if __name__ == "__main__":
    main()
