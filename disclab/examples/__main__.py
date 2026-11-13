"""Run box -> loop geo -> score in a new lab folder, without any real device."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def main(argv=None):
    from disclab.compat import require_discprobe
    require_discprobe()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lab", type=Path, help="new folder; must not already exist")
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("dvd-r-3.json"))
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    start = time.perf_counter()
    if args.lab is None:
        lab = Path(tempfile.mkdtemp(prefix="disc-lab-example-")).resolve()
    else:
        lab = args.lab.resolve()
        lab.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[2]

    def run(*command):
        subprocess.run([sys.executable, "-B", "-m", "disclab", *map(str, command)],
                       cwd=root, env=dict(os.environ, PYTHONIOENCODING="utf-8"), check=True)

    run("box", "--lab", lab, "--media", config["media"], "--count", config["count"],
        "--seed", config["seed"], "--batch", config.get("batch", 1),
        "--stampers", config.get("stampers", 1), "--reader", config.get("reader", "gh70n"),
        "--drives", *config.get("drives", ["X:"]), "--uv-noise", *config.get("uv_noise", [0, 0]))
    # The whole disc burned and read with the defaults, as a real measurement: a part-filled disc
    # measures only an inner band, and its whole-disc placement is then an extrapolation.
    quick = [x for k in ("iso_sectors", "reps", "max_targets") if k in config
             for x in ("--" + k.replace("_", "-"), config[k])]
    run("loop", "geo", "--lab", lab, "--drive", config.get("drives", ["X:"])[0], *quick)
    score_file = lab / "scores" / "geo-wide.json"
    rows = json.loads(score_file.read_text(encoding="utf-8"))
    run("score", "--lab", lab, "--disc", rows[0]["disc"], "--geo", rows[0]["geo"])
    print(f"Scores: {score_file}", flush=True)
    print("disc | timing RMS deg | placement L mm | residual after L deg | geo exit", flush=True)
    for row in rows:
        print(f"{row['disc']} | {row['vs_timing_measured_span']['rms_deg']:.6f} | "
              f"{row['placement_on_target']['L_mm']:+.6f} | "
              f"{row['placement_on_target']['residual_after_L_rms_deg']:.6f} | {row['exit']}", flush=True)
    print(f"Wall time: {time.perf_counter() - start:.2f} s", flush=True)


if __name__ == "__main__":
    main()
