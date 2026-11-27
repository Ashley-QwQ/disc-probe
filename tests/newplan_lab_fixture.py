"""Run one isolated Disc Lab scenario against the unmodified WebUI HTTP API."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from disclab.__main__ import BOOT
from disclab.lab import Lab
from disclab.scenario import load_scenario, make_scenario_box
from discprobe import webui_catalog
from discprobe.starter import record_drive_identity
from tests.test_webui_catalog import write_geo


root, case = Path(sys.argv[1]).resolve(), sys.argv[2]
lab = Lab(root)
root.mkdir(parents=True)
scenario_path = root / "scenario.json"
media = "dvd-rw" if case == "rw" else "dvd-r"
initial = {"state": "open" if case == "written" else "burned", "random": True, "sectors": 4096}
scenario_path.write_text(json.dumps({
    "discs": {"media": media, "count": 1, "seed": 178,
              "mid": "DLABRW01" if case == "rw" else "RITEKF1",
              "initial_state": initial if case in ("rom", "written", "rw") else "blank"},
    # second: two drives, the first empty and the blank in the second (the page has to find it)
    "drives": ["X:", "Y:"] if case == "second" else ["X:"],
}), encoding="utf-8")
box = make_scenario_box(lab, load_scenario(scenario_path))
with lab.locked_state() as state:
    drive = state["drives"]["X:"]
    drive.update(tray=None if case in ("empty", "tray-open", "second") else box["discs"][0],
                 open=case == "tray-open")
    if case == "second":
        state["drives"]["Y:"].update(tray=box["discs"][0], open=False)

# Two saved batches, so automatic drive selection and the history fallback give different answers.
if case in ('blank', 'second'):
    who = dict(disc='RITEKF1', drive='DISCLAB GH70N-LIKE', firmware='LAB1')
    fit = dict(media='dvd', u=180518., v=5.591, bit_nm_assumed=133.3, chi2_per_dof=1,
               measured_span_mm=[24.49,57.1], angle_sigma_measured_span_deg=.1)
    geo = write_geo(root, fit=fit, identity=who)
    record_drive_identity(geo, who, 'Y:' if case == 'second' else 'X:')
else:
    write_geo(root, identity=dict(disc="RITEKF1", drive="Disc Lab"))
write_geo(root, "20261108-101500", identity=dict(disc="HIST/R02/01", drive="Disc Lab"))
catalogue = webui_catalog.catalogue(root, root / "results")["dvd"]
for row in catalogue:
    history = row["mid"] == "HIST/R02/01"
    webui_catalog.save_entry(root, root / "results",
                             dict(id=row["id"], name="History DVD+R" if history else "RITEKF1 DVD-R"))
    if history:
        (root / "history.json").write_text(json.dumps(row["id"]), encoding="utf-8")

if case == "rom":
    # Some real drives report finalized DVD-R as profile 0x10. The lab normally keeps profile 0x11.
    # Change only its current profile in the isolated child and the child spawned by /api/disc.
    boot = root / "boot"
    boot.mkdir()
    (boot / "sitecustomize.py").write_text(
        f"from runpy import run_path\nrun_path({str(BOOT / 'sitecustomize.py')!r})\n"
        "from disclab.box import MEDIA\nMEDIA['dvd-r']['profile'] = 0x10\n",
        encoding="utf-8",
    )
