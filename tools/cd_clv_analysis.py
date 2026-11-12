"""Offline arithmetic for issue 251; no device commands or external data."""
import json
import math

from discprobe import clv
from discprobe.geometry import CD_SECTOR_MM


def main():
    rows = [(17987, 18.21136, 46.38), (179875, 29.36623, 990.28), (341763, 37.35033, 1862.54)]
    samples = [clv.Sample(lba=lba, period_ms=t) for lba, t, _ in rows]
    fits = {}
    for pitch in (1.4865, 1.5, 1.6):
        fit = clv.fit_t2(samples, sector_mm=CD_SECTOR_MM, pitch_um=pitch, drop_outliers=False)
        fits[str(pitch)] = fit.as_dict()
    zones = []
    for lba, t, jitter_us in rows:
        radius = math.sqrt(25 ** 2 + 1.5e-3 * CD_SECTOR_MM * lba / math.pi)
        deg = jitter_us / (t * 1000) * 360
        zones.append(dict(lba=lba, period_ms=t, jitter_us=jitter_us,
                          jitter_deg=deg, relative_completion_jitter=jitter_us / (t * 1000),
                          nominal_radius_mm=radius, nominal_arc_jitter_mm=math.radians(deg) * radius))
    # Only a scale sensitivity, not a measurement of this disc's unknown anchor.
    base = fits["1.4865"]
    p, r0, lba = 1.4865e-3, base["r0_mm"], rows[-1][0]
    radius = math.sqrt(r0 * r0 + p * CD_SECTOR_MM * lba / math.pi)
    turns = (radius - r0) / p
    scale = math.sqrt(1.01)
    anchor_twist_deg = (turns / scale - turns) * 360
    result = dict(source="Issue 251 screenshot supplied with the task; no new hardware measurement",
                  sector_mm=CD_SECTOR_MM, zones=zones, pitch_anchored_fits=fits,
                  pitch_anchor_plus_one_percent=dict(radius_scale=scale,
                      accumulated_angle_change_deg=anchor_twist_deg),
                  caution="Completion jitter is not the uncertainty of a fitted spindle period. Three rounded periods cannot validate a CD angle map or an absolute along-track constant.")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
