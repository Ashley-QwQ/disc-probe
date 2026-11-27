"""Read-only replay of the photo application policy on saved reader diagnostics.

No images are re-read by the reader here. JSON hashes identify the diagnostic
inputs to this replay; they are not presented as original photograph hashes.
"""
import hashlib
import itertools
import json
from pathlib import Path

from discprobe import photo
from discprobe.photo import PHOTO_L_POLICY, photo_agreement


def main():
    base = Path("C:/disc-probe-scratch/pcal-blur")
    out = Path("C:/disc-probe-scratch/photo-l")
    out.mkdir(parents=True, exist_ok=True)
    sources = []

    def load(path):
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        sources.append(dict(path=str(path), sha256=digest))
        return json.loads(raw), digest

    def reading(result, ident, digest):
        return {**result, "id": ident, "input_sha256": digest}

    original, digest = load(Path("C:/disc-probe-scratch/pcal-lottery/heldout/case_00703.json"))
    # The blur study has its own case numbered 00703 with a different truth.
    result = original.get("readers", {}).get("v1", {}).get("result")
    if result is None:
        result = original.get("result") or original.get("v1")
    if result is None:
        original, digest = load(base / "decomposition.json")
        result = original["results"]["fitted"]["result"]
        original = original["job"]
    cases = [("lottery/00703", original, reading(result, "00703", digest))]
    data, digest = load(base / "heldout/case_00929.json")
    cases.append(("blur/00929", data, reading(data["readers"]["v1"]["result"], "00929", digest)))
    simulated = []
    for ident, data, p in cases:
        simulated.append(dict(case=ident, truth_mm=data["truth"], L_mm=p["L_mm"],
                              error_mm=p["L_mm"] - data["truth"], spread_mm=p["zone_spread_mm"],
                              single=photo_agreement([p]), independent_second_pose="NOT_RUN"))
    real = []
    for path in sorted((base / "real").glob("case_*.json")):
        data, digest = load(path)
        p = reading(data["readers"]["v1"]["result"], data["condition"], digest)
        real.append(p)
    pairs = [dict(photos=[a["id"], b["id"]], decision=photo_agreement([a, b]),
                  delta_mm=abs(a["L_mm"] - b["L_mm"]),
                  limit_mm=(a["zone_spread_mm"] + b["zone_spread_mm"]) / 2)
             for a, b in itertools.combinations(real, 2) if a["status"] == b["status"] == "ok"]
    summary = dict(policy=PHOTO_L_POLICY,
                   policy_source_sha256=hashlib.sha256(Path(photo.__file__).read_bytes()).hexdigest(),
                   reader_version="v1", reader_sha256=photo.READER_SHA256,
                   mode="saved diagnostics only; reader NOT_RUN",
                   simulated=simulated, real=[{k: p.get(k) for k in
                        ("id", "status", "L_mm", "zone_spread_mm", "c_deg")} for p in real],
                   real_group=photo_agreement(real), real_pairs=pairs, sources=sources)
    target = out / "agreement-check.json"
    target.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(dict(simulated=simulated, real_count=len(real),
                          real_ok=sum(p['status'] == 'ok' for p in real), real_group=summary['real_group'],
                          accepted_pairs=[p['photos'] for p in pairs if p['decision']['written']]), indent=2))


if __name__ == "__main__":
    main()
