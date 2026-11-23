"""Isolated Disc Lab processes used by the reshoot browser test."""
from pathlib import Path
import hashlib
from itertools import combinations
import json
import os
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from disclab.lab import Lab, atomic_json


def target():
    import numpy as np
    from PIL import Image
    from discprobe import checkdisc, gratingcard

    labels = checkdisc.build_design()
    textures = list(checkdisc.TEXTURES)
    gratingcard.add_arrow(labels, textures, (26, 57.2))
    assert (labels[:1000, 2750:3250] == len(textures) - 1).any()
    preview = (labels == len(textures) - 1).astype(np.uint8) * 255
    return labels, textures, Image.fromarray(preview).resize((600, 600), Image.Resampling.BOX)


def verify(lab, design=None):
    from discprobe import image_output, imagedisc

    iso = lab.root / "iso" / "check.iso"
    spec = json.loads(iso.with_suffix(".image.json").read_text(encoding="utf-8"))
    labels, textures, _ = design if design is not None else target()
    problems = image_output.verify_generated(str(iso), imagedisc.verify_iso, labels,
        spec["u"], spec["v"], spec["bit_nm"], iso.stat().st_size // 2048, textures=textures, samples=300)
    assert not problems, problems
    print("Verified 300 check-disc samples", flush=True)


def prepare(lab, source=None):
    from PIL import Image, ImageDraw
    from disclab.box import make_box
    from discprobe import imagedisc
    from discprobe.guide import MIN_RUNGS

    make_box(lab, "dvd-r", 2, seed=178)
    tray(lab, 0)
    disc = lab.box()["discs"][0]
    answers = lab.answers()
    truth = answers["discs"][disc]
    # Stable synthetic discs and camera poses keep this a workflow regression.
    # The optical reader still gets real rendered photos and runs its own gates.
    answers["writers"]["imapi"]["jitter_bits"] = 0
    for sample in answers["discs"].values():
        sample.update(b_nm=truth["b_nm"], ecc_um=0, dish_mm=0, saddle_mm=0,
                      contrast_gain=1, flaw=None, varpitch_deg=[0] * len(sample["varpitch_deg"]))
    atomic_json(lab.answers_path, answers)
    run = lab.root / "results" / "geo-X-20261123-160000"
    run.mkdir(parents=True)
    fit = dict(media="dvd", u=truth["u"], v=truth["v"], bit_nm_assumed=truth["b_nm"],
               measured_span_mm=[24, 58.2], angle_sigma_measured_span_deg=.03, chi2_per_dof=1,
               coverage=dict(measured_intervals_mm=[[24, 58.2]]))
    summary = run / "summary.json"
    summary.write_text(json.dumps(dict(fit=fit, identity=dict(disc=lab.box()["mid"],
        drive="DISCLAB GH70N-LIKE", device_id="X:"), setup=dict(last_lba=truth["capacity"] - 1),
        args=dict(drive="X:", media="dvd"))), encoding="utf-8")
    (run / "targets.csv").write_text("lba,residual_deg,sigma_deg\n" +
        "".join(f"{10000 + i * 50000},0.01,0.03\n" for i in range(MIN_RUNGS)), encoding="utf-8")

    iso = lab.root / "iso" / "check.iso"
    if source:
        source = Path(source)
        iso.parent.mkdir()
        os.link(source / "check.iso", iso)
        spec = json.loads((source / "check.image.json").read_text(encoding="utf-8"))
        spec["geometry_from"] = str(summary)
        iso.with_suffix(".image.json").write_text(json.dumps(spec), encoding="utf-8")
        shutil.copyfile(source / "check.iso.verification.json", str(iso) + ".verification.json")
        shutil.copyfile(source / "check-arrow.png", lab.root / "check-arrow.png")
    else:
        labels, textures, preview = target()
        preview.save(lab.root / "check-arrow.png")
        imagedisc.write_iso(str(iso), labels, fit["u"], fit["v"], fit["bit_nm_assumed"],
                            min(2295104, truth["capacity"]), textures=textures,
                            meta=dict(check_disc=True, geometry_from=str(summary), experimental=True))
        verify(lab, (labels, textures, preview))
    with iso.open("rb") as stream:
        print("Check ISO SHA-256:", hashlib.file_digest(stream, "sha256").hexdigest(), flush=True)
    picture = Image.new("RGBA", (128, 128))
    ImageDraw.Draw(picture).rectangle((119, 54, 126, 73), fill="black")
    picture.save(lab.root / "picture.png")
    (lab.root / "fixture.json").write_text(json.dumps(dict(run=run.name, iso="iso/check.iso")), encoding="utf-8")


def tray(lab, index):
    with lab.locked_state() as state:
        state["drives"]["X:"]["tray"] = lab.box()["discs"][index]


def shoot(lab, index):
    from disclab.photos import shoot as render
    from discprobe import photo

    disc = lab.box()["discs"][index]
    # Select suitable simulated camera angles, leaving the actual read and
    # agreement decision to the normal web photo job after upload.
    trial = lab.root / "camera-probe"
    trial.mkdir()
    accepted = []
    for batch, (distance, tilt) in enumerate(((215, 20), (185, 16), (205, 24), (230, 19))):
        def pose(i, _):
            return dict(width=1600, height=1200, dist_mm=distance, tilt_deg=tilt,
                        az_deg=i * 60 + index * 13 + batch * 19, roll_deg=i * 27 + batch * 35,
                        f35_mm=26, blur_px=.5, motion_px=0, noise=.5, veil=.04, shift_frac=0,
                        fingers=0, k1=0, refraction=False)
        paths = render(lab, disc, 6, lab.root / "camera", seed=index + 173 + batch * 2, style="flash", fixed=pose)
        for path in paths:
            photo.analyze(trial, "dvd", [(path.name, path)])
            shot, = json.loads((trial / "photo.json").read_text(encoding="utf-8"))["photos"]
            if shot["status"] != "ok":
                continue
            accepted.append((path, shot))
            for pair in combinations(accepted, 2):
                if photo.photo_agreement([row[1] for row in pair])["written"]:
                    chosen = [str(row[0]) for row in pair]
                    (lab.root / "camera.json").write_text(json.dumps(chosen), encoding="utf-8")
                    return
    raise ValueError("The simulated camera angles did not yield two agreeing photos")


def serve(lab, port):
    from discprobe.webui import Backend, Server
    # The test process and its children must use the real API against the Lab only.
    assert os.environ.get("DISCPROBE_DISCLAB") == str(lab.root)
    backend = Backend(lab.root)
    server = Server(backend, port)
    (lab.root / "ready.json").write_text(json.dumps(dict(port=server.server_port)), encoding="utf-8")
    try:
        server.serve_forever()
    finally:
        server.server_close()
        backend.close()


def clean(directory, parent):
    path, base = Path(directory).resolve(strict=True), Path(parent).resolve(strict=True)
    if path == base or not path.is_relative_to(base):
        raise ValueError("refusing to remove a directory outside the reshoot test root")
    for attempt in range(20):
        try:
            shutil.rmtree(path)
            return
        except OSError:
            if attempt == 19:
                raise
            time.sleep(.25)


if __name__ == "__main__":
    action, directory, *args = sys.argv[1:]
    if action == "clean":
        clean(directory, *args)
        raise SystemExit
    lab = Lab(directory)
    if action == "serve" and not os.environ.get("DISCPROBE_DISCLAB"):
        import subprocess
        from disclab.__main__ import lab_env
        raise SystemExit(subprocess.call([sys.executable, "-B", __file__, action, directory, *args],
                                         cwd=lab.root, env=lab_env(lab)))
    if action == "prepare":
        prepare(lab, *args)
    else:
        {"tray": tray, "shoot": shoot, "serve": serve, "verify": verify}[action](lab, *map(int, args))
