"""Opt-in full-DVD CLI benchmark; no hardware or server access.

Run from the repo: python tests/bench_along_track_grid.py before|after
Requires psutil for process-tree working-set sampling. Large scratch files are
removed after each run; measurements and CLI logs live in docs/along-track-grid.
"""
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

import numpy as np
import psutil

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "along-track-grid"
SCRATCH = ROOT / "tests" / ".along-grid-bench"


def main():
    phase = sys.argv[1]
    assert phase in ("before", "after")
    OUT.mkdir(exist_ok=True)
    SCRATCH.mkdir(exist_ok=True)
    geo = SCRATCH / "summary.json"
    geo.write_text(json.dumps({"fit": {"u": 24 / .0001333, "v": .00074 / .0001333,
                                      "bit_nm_assumed": 133.3, "media": "dvd",
                                      "measured_span_mm": [24, 60]},
                               "source": "synthetic benchmark, not a measured geometry"}))
    result = dict(phase=phase, platform=platform.platform(), python=sys.version,
                  cpu_count=os.cpu_count(), total_ram_bytes=psutil.virtual_memory().total,
                  workers="auto (up to 6)", sectors=2295104, runs=[])
    for um, side in ((20, 6000), (10, 12000), (5, 24000)):
        design_path = SCRATCH / "design.npy"
        design = np.lib.format.open_memmap(design_path, mode="w+", dtype=np.uint8, shape=(side, side))
        # The same 0.2 mm checkerboard in every grid; inner/outer background.
        x = (np.arange(side) + .5) * 120 / side - 60
        for row in range(side):
            y = 60 - (row + .5) * 120 / side
            r2 = x*x + y*y
            design[row] = ((np.floor(x / .2) + np.floor(y / .2)) % 2).astype(np.uint8) * ((r2 >= 25**2) & (r2 <= 58**2))
        design.flush()
        del design
        iso = SCRATCH / "full.iso"
        cmd = [sys.executable, "-B", "-m", "discprobe", "image", "--geo", str(geo),
               "--design-npy", str(design_path), "--textures", "B9", "A5", "--cell-um", str(um),
               "--r-max", "58", "--output", str(iso)]
        env = {**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"}
        env.pop("DISCPROBE_WORKERS", None)
        available = psutil.virtual_memory().available
        start = time.perf_counter()
        peak_rss = peak_private = 0
        with (OUT / f"{phase}-{um}um.log").open("w", encoding="utf-8") as log:
            proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
            parent = psutil.Process(proc.pid)
            while proc.poll() is None:
                rss = private = 0
                try:
                    processes = [parent, *parent.children(recursive=True)]
                except psutil.Error:
                    processes = []
                for p in processes:
                    try:
                        mem = p.memory_info()
                        rss += mem.rss
                        private += getattr(mem, "private", 0)
                    except psutil.Error:
                        pass
                peak_rss = max(peak_rss, rss)
                peak_private = max(peak_private, private)
                time.sleep(.1)
        elapsed = time.perf_counter() - start
        hashes = {}
        if proc.returncode == 0:
            assert iso.stat().st_size == 2295104 * 2048
            with iso.open("rb") as f:
                for lba in (32, 500003, 2145149):
                    f.seek(lba * 2048)
                    hashes[str(lba)] = hashlib.sha256(f.read(4 * 2048)).hexdigest()
        run = dict(cell_um=um, seconds=elapsed, peak_tree_rss_bytes=peak_rss,
                   peak_tree_private_bytes=peak_private, available_ram_at_start=available,
                   returncode=proc.returncode, sector_hashes=hashes, command=cmd)
        result["runs"].append(run)
        (OUT / f"{phase}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(run), flush=True)
        for path in (iso, iso.with_suffix(".image.json"), iso.with_suffix(".preview.png"), design_path):
            path.unlink(missing_ok=True)
        if proc.returncode:
            raise RuntimeError(f"image failed; see {phase}-{um}um.log")
    geo.unlink()
    SCRATCH.rmdir()


if __name__ == "__main__":
    main()
