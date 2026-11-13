"""Build disclab/data/wave_xyz.npz: XYZ of each DVD texture against the along-track parameter delta.

Source: the A3 colour-card wave model (docs/goals/night/palette/a3card/wave_model.py, not in the repository):
real EFMPlus + ECC recorded rows, rectangular marks 0.35 um wide, lamp and pupil apertures, LED and D65 lamps.
A5 and B9 reuse that model's saved spectra; RND is computed here with the same functions.
delta = (c + l) . t, c and l unit vectors to camera and lamp, t the local track tangent.

    python -m disclab.tables       (once; about a minute; needs the a3card folder)
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np

A3 = Path("D:/disc-probe/docs/goals/night/palette/a3card")
OUT = Path(__file__).resolve().parent / "data" / "wave_xyz.npz"
TEXTURES = ("A5", "B9", "RND")


def build():
    sys.path.insert(0, str(A3))
    import wave_model as W
    from discprobe.imagedisc import texture_bytes
    W.texture_bytes = texture_bytes          # the extracted copy lacks _hash, which RND needs
    from colour_tables import observer
    op = np.load(A3 / "v3" / "operator_64.npy", mmap_mode="r")
    xyz = {}
    for spec in TEXTURES:
        key = hashlib.sha256(spec.encode()).hexdigest()[:24]
        path = A3 / "v3" / "checkpoints" / f"{key}.npz"
        if path.exists():
            with np.load(path, allow_pickle=False) as z:
                mass = np.mean(z["samples"], axis=0)
        else:
            ms = []
            for seed in range(W.SAMPLES):
                lv, (lo, hi), _ = W.recorded_block(spec, seed)
                ms.append(W.rebin_power(lv[lo:hi]))
            mass = np.mean(ms, axis=0)
        x = W.xyz_from_mass(mass, op)            # (delta, lamp, 3)
        xyz[spec] = np.asarray(x, np.float32)
        print(spec, "Y(LED) max", float(x[:, 0, 1].max()), "mean", float(x[:, 0, 1].mean()), flush=True)
    nm = np.arange(380, 781, 2.0)
    np.savez_compressed(OUT, delta=np.asarray(W.DELTA, np.float32), textures=np.array(TEXTURES),
                        xyz=np.stack([xyz[t] for t in TEXTURES]), cmf_nm=nm, cmf=observer(nm).astype(np.float32),
                        xyz_to_srgb=W.XYZ_TO_SRGB.astype(np.float32), source=W.VERSION)
    print("wrote", OUT)


if __name__ == "__main__":
    build()
