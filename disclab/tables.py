"""Offline A3 v3 tables. Rendering shipped specs needs no external source.

Rebuilding/new recipes require an A3 export and sibling discprobe with efmplus,
dvd and imagedisc. All model caches live outside repositories. The original
three-texture table is deliberately never overwritten.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile

import numpy as np

DATA = Path(__file__).resolve().parent / "data"
OUT = DATA / "textures_v3.npz"
TEXTURES = (
    "A37062", "DD5AA565C8A4A565",
    "66C47EC0E4B6D9A37595759971AD66A67EC0E27BF894EE75B4CAEB66AD",
    "CC67", "F9", "957CD4D880B2D5F2BDD2CB98FBD1D2DBD49569ECD8C5DBD2",
    "8DCDE6FBC0CDCBD5A3", "E683D7787D15C08ED5912A978345D8858D8F2A2AFB8B",
    "8D91858EC8859195D18B92", "RND",
)


def canonical(spec):
    spec = spec.strip().upper()
    if spec == "RND":
        return spec
    seq = bytes.fromhex(spec)
    if not seq or len(seq) > 64:
        raise ValueError("A texture needs 1 to 64 hex bytes, or RND")
    for period in range(1, len(seq) + 1):
        if len(seq) % period == 0 and seq == seq[:period] * (len(seq) // period):
            return seq[:period].hex().upper()
    return seq.hex().upper()


def cache_root():
    configured = os.environ.get("DISCLAB_WAVE_CACHE")
    if configured:
        return Path(configured)
    if os.name == "nt":
        return Path(tempfile.gettempdir()) / "disclab-wave"
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "disclab-wave"


def wave_model(a3=None, cache=None):
    source = a3 or os.environ.get("DISCLAB_A3_SOURCE")
    if not source or not (Path(source) / "wave_model.py").is_file():
        raise RuntimeError("This texture is not shipped. Computing a new spec needs the exported A3 source: "
                           "set DISCLAB_A3_SOURCE to its docs/texture-cards/scripts folder.")
    source = Path(source).resolve()
    sys.path.insert(0, str(source))
    W = sys.modules.get("wave_model")
    if W is None:
        # The upstream module creates build directories on import. Omit only
        # that top-level mkdir loop in memory so the export stays read-only;
        # model functions and the signed source file remain unchanged.
        path = source / "wave_model.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        loops = [n for n in tree.body if isinstance(n, ast.For)
                 and isinstance(n.target, ast.Name) and n.target.id == "p"
                 and isinstance(n.iter, ast.Tuple)
                 and [getattr(v, "id", None) for v in n.iter.elts] == ["OUT", "CACHE"]]
        if len(loops) != 1:
            raise RuntimeError("Unrecognised A3 import directory setup")
        tree.body.remove(loops[0])
        module_spec = importlib.util.spec_from_file_location("wave_model", path)
        W = importlib.util.module_from_spec(module_spec)
        sys.modules["wave_model"] = W
        try:
            exec(compile(tree, str(path), "exec"), W.__dict__)
        except BaseException:
            del sys.modules["wave_model"]
            raise
    if Path(W.__file__).resolve().parent != source:
        raise RuntimeError("A different wave_model is already imported; use a fresh process")
    # Complete upstream's read-only AST extraction with its omitted helper.
    # Read from the exact file in signature(), regardless of sys.modules.
    image_source = W.ROOT / "discprobe" / "imagedisc.py"
    tree = ast.parse(image_source.read_text(encoding="utf-8"))
    nodes = [n for n in tree.body if
             (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_COL" for t in n.targets))
             or (isinstance(n, ast.FunctionDef) and n.name in ("_hash", "texture_bytes"))]
    if len(nodes) != 3:
        raise RuntimeError("The A3 source needs imagedisc _COL, _hash and texture_bytes")
    ns = {"np": np, "dvd": W.dvd}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(image_source), "exec"), ns)
    W.texture_bytes = ns["texture_bytes"]
    for name, module in (("efmplus", W.E), ("dvd", W.dvd)):
        if W.sha(module.__file__) != W.sha(W.ROOT / "discprobe" / (name + ".py")):
            raise RuntimeError("Loaded discprobe differs from the A3 signature: " + name)
    root = Path(cache or cache_root()).resolve()
    if root.is_relative_to(DATA.parent.parent) or root.is_relative_to(W.ROOT):
        raise ValueError("Wave caches must be outside the repository and A3 export")
    W.OUT, W.CACHE = root / "operator", root / "checkpoints"
    # texture_mass makes its checkpoint name relative to HERE.parent. Keep
    # that reporting base in scratch too; SOURCE_PATHS/signature stay intact.
    W.HERE = root / "adapter"
    W.OUT.mkdir(parents=True, exist_ok=True)
    W.CACHE.mkdir(parents=True, exist_ok=True)
    return W


def operator(W):
    """Cache the large operator in scratch; never call upstream save=True."""
    sig, _ = W.signature()
    path = W.OUT / (sig + ".npy")
    meta_path = path.with_suffix(".json")
    if path.exists() and meta_path.exists():
        return np.load(path, mmap_mode="r"), json.loads(meta_path.read_text())
    op, meta = W.build_operator(save=False)
    np.save(path, op)
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    return op, meta


def compute(spec, W, op=None):
    """Cache mass/XYZ by canonical spec AND the full model signature."""
    spec = canonical(spec)
    sig, _ = W.signature()
    key = hashlib.sha256((spec + sig).encode()).hexdigest()
    root = W.OUT.parent / "spectra"
    root.mkdir(parents=True, exist_ok=True)
    path = root / (key + ".npz")
    if path.exists():
        with np.load(path, allow_pickle=False) as z:
            if str(z["spec"]) == spec and str(z["signature"]) == sig:
                return {k: z[k] for k in z.files}
    W.CACHE = W.OUT.parent / "checkpoints" / sig
    W.CACHE.mkdir(parents=True, exist_ok=True)
    mass, rec = W.texture_mass(spec)
    if op is None:
        op, _ = operator(W)
    xyz = W.xyz_from_mass(mass, op)
    densities = []
    for seed in range(W.SAMPLES):
        lv, (lo, hi), _ = W.recorded_block(spec, seed)
        densities.append(np.mean(1 - lv[lo:hi]))
    result = dict(spec=spec, signature=sig, mass=mass, xyz=np.asarray(xyz, np.float32),
                  delta=np.asarray(W.DELTA, np.float32), mark_density=float(np.mean(densities)),
                  record=json.dumps(rec))
    tmp = path.with_suffix(".tmp")
    with tmp.open("wb") as f:
        np.savez_compressed(f, **result)
    tmp.replace(path)
    return result


def build(a3, output=OUT, cache=None, specs=TEXTURES):
    output = Path(output)
    if output.resolve() == (DATA / "wave_xyz.npz").resolve():
        raise ValueError("The legacy wave_xyz.npz table must not be overwritten")
    W = wave_model(a3, cache)
    op, meta = operator(W)
    rows = []
    for spec in specs:
        row = compute(spec, W, op)
        rows.append(row)
        print(spec, "Y(LED) max", float(row["xyz"][:, 0, 1].max()), flush=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(output, textures=np.array([r["spec"] for r in rows]), delta=rows[0]["delta"],
                        xyz=np.stack([r["xyz"] for r in rows]), mass=np.stack([r["mass"] for r in rows]),
                        mark_density=np.array([r["mark_density"] for r in rows]),
                        signature=W.signature()[0], source=W.VERSION)
    provenance = W.provenance()
    anchors = {}
    for spec in ("A5", "B9"):
        densities = []
        for seed in range(W.SAMPLES):
            lv, (lo, hi), _ = W.recorded_block(spec, seed)
            densities.append(float(np.mean(1 - lv[lo:hi])))
        anchors[spec] = float(np.mean(densities))
    provenance.update(operator={k: v for k, v in meta.items() if k != "delta"},
                      texture_bytes_adapter="unchanged _COL, _hash, texture_bytes AST from signature source; upstream omits _hash",
                      legacy="wave_xyz.npz unchanged: A5/B9/RND pixel compatibility",
                      mark_density_anchors=anchors,
                      textures=[r["spec"] for r in rows])
    output.with_suffix(".json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    return output


def lookup(spec):
    spec = canonical(spec)
    if OUT.exists():
        with np.load(OUT, allow_pickle=False) as z:
            names = list(z["textures"])
            if spec in names:
                i = names.index(spec)
                return dict(delta=z["delta"], xyz=z["xyz"][i], mark_density=float(z["mark_density"][i]))
    W = wave_model()
    return compute(spec, W)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a3", required=True, type=Path)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--spec", action="append")
    args = parser.parse_args()
    print(build(args.a3, args.output, args.cache, args.spec or TEXTURES))
