"""Start an isolated Disc Lab server for the post-burn browser test. All artifacts stay on D:."""
import base64
import io
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
root = Path(sys.argv[1]).resolve()
os.environ["DISCPROBE_HOME"] = str(root)

if "--serve" not in sys.argv:
    from disclab.lab import Lab
    from disclab.box import make_box
    from disclab.__main__ import lab_env
    from discprobe import works
    from PIL import Image, ImageDraw
    lab = Lab(root)
    make_box(lab, "dvd-r", 3, seed=178)
    with lab.locked_state() as state:
        state["drives"]["X:"]["tray"] = lab.box()["discs"][0]
    (root / "iso").mkdir(exist_ok=True)
    result = subprocess.run([sys.executable, "-B", "-m", "discprobe", "random", "--sectors", "4096",
        "--seed", "178", "--output", "iso/review.iso"], cwd=root, env=lab_env(lab), capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", "replace"))
    picture = Image.new("RGBA", (128,128), (255,255,255,0))
    ImageDraw.Draw(picture).rectangle((18,28,110,100), fill="black")
    stream = io.BytesIO(); picture.save(stream, format="PNG")
    image = "data:image/png;base64," + base64.b64encode(stream.getvalue()).decode()
    # This is a navigation fixture, not an image-reconstruction or physical-parity experiment.
    # The small random ISO exercises the genuine virtual burner and read-back, while this design
    # and bounded measurement fixture exercise durable review navigation.
    geo = root / "results" / "geo-X-20261115-010101"
    geo.mkdir(parents=True)
    (geo / "summary.json").write_text(json.dumps(dict(fit=dict(u=180000, v=5.5,
        measured_span_mm=[25,56], angle_sigma_measured_span_deg=.2, chi2_per_dof=1,
        coverage=dict(intervals_mm=[[25,56]])), args=dict(media="dvd"))), encoding="utf-8")
    (geo / "targets.csv").write_text("lba,residual_deg,sigma_deg\n1000,0.1,0.2\n2000,-0.1,0.2\n", encoding="utf-8")
    store = works.Store(root / "results")
    doc = dict(format="disc-probe design", version=2, media="dvd", cell=.02,
        geo="results/"+geo.name, layers=[dict(kind="image", name="检查用图", picture=image,
        original=image, x=0, y=0, width=80, rot=0, opacity=1, visible=True)])
    work = store.new("刻后流程 · Disc Lab", raw=works.encoded(doc))
    store.link(work["id"], root / "iso" / "review.iso", kind="iso")
    (root / "fixture.json").write_text(json.dumps(dict(work=work["id"])), encoding="utf-8")
    result = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()), str(root), "--serve"],
        cwd=root, env=lab_env(lab))
    raise SystemExit(result.returncode)
else:
    # sitecustomize from lab_env is active before any discprobe device module is imported.
    from discprobe.webui import Backend, Server
    backend = Backend(root)
    server = Server(backend, 0)
    ready = json.loads((root / "fixture.json").read_text(encoding="utf-8"))
    ready["port"] = server.server_port
    (root / "ready.json").write_text(json.dumps(ready), encoding="utf-8")
    try:
        server.serve_forever()
    finally:
        server.server_close(); backend.close()
