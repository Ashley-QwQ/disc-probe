"""Build discprobe/simulate_a3v3.npz: A3 v3 texture light (LED lamp) for the editor's lamp view.

Rows: the 260 singles of the Disc Neo colour card (sheet 1, its XYZ table as rendered), plus textures the card
does not hold, computed with the same wave model and operator: B9 (the editor's default background) and the
check disc's textures. The A3 export is only read; its checkpoints go to --scratch.

    python tools/build_simulate_a3v3.py --a3 docs/goals/night/palette/a3card --scratch D:/somewhere
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

EXTRA = ("B9", "A37062", "DD5AA565C8A4A565", "66C47EC0E4B6D9A37595759971AD66A67EC0E27BF894EE75B4CAEB66AD", "CC67",
         "F9", "957CD4D880B2D5F2BDD2CB98FBD1D2DBD49569ECD8C5DBD2", "8DCDE6FBC0CDCBD5A3",
         "E683D7787D15C08ED5912A978345D8858D8F2A2AFB8B", "8D91858EC8859195D18B92")
DELTA = np.round(np.arange(.10, .95 + 1e-9, .0025), 4)


def canonical(spec):
    seq = bytes.fromhex(spec)
    for p in range(1, len(seq) + 1):
        if len(seq) % p == 0 and seq == seq[:p] * (len(seq) // p):
            return seq[:p].hex().upper()
    return seq.hex().upper()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a3", required=True, type=Path)
    ap.add_argument("--scratch", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1] / "discprobe" / "simulate_a3v3.npz")
    a = ap.parse_args()
    sys.path.insert(0, str(a.a3.resolve()))
    import wave_model as M
    M.HERE = a.scratch
    M.CACHE = a.scratch / "checkpoints"
    M.CACHE.mkdir(parents=True, exist_ok=True)
    card = np.load(a.a3 / "v3" / "sheet_1_singles_XYZ.npz")
    manifest = json.loads((a.a3 / "v3" / "sheet_1_singles_led_manifest.json").read_text(encoding="utf-8"))
    spec_of = {r["id"]: canonical(r["spec"]) for r in manifest["rows"]}
    sig = M.signature()[0]
    if str(card["signature"]) != sig:
        raise SystemExit("card table and wave model signatures differ")
    rows = {}
    for i, ident in enumerate(card["ids"]):
        rows.setdefault(spec_of[str(ident)], card["XYZ"][i, :, 0, :])     # LED
    op = np.load(a.a3 / "v3" / "operator_64.npy", mmap_mode="r")
    for spec in EXTRA:
        spec = canonical(spec)
        if spec not in rows:
            mass, _ = M.texture_mass(spec)
            rows[spec] = M.xyz_from_mass(mass, op)[:, 0, :]
            print("computed", spec, flush=True)
    specs = sorted(rows)
    xyz = np.stack([np.stack([np.interp(DELTA, M.DELTA, rows[s][:, k]) for k in range(3)], -1) for s in specs])
    from colour_tables import TABLE, XYZ_TO_SRGB
    np.savez_compressed(a.out, specs=np.array(specs), delta=DELTA.astype(np.float32), xyz=xyz.astype(np.float32),
                        cmf_nm=TABLE[:, 0].astype(np.float32), cmf=TABLE[:, 1:4].astype(np.float32),
                        xyz_to_srgb=np.asarray(XYZ_TO_SRGB, np.float32), signature=sig, source=M.VERSION,
                        lamp="LED")
    print(a.out, len(specs), "textures", a.out.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
