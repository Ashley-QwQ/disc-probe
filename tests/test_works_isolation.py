"""Tests and Disc Lab runs must never file work records in the checkout's own works library.

Works default to ./works beside ./results. A checkout that also serves someone's web page
(D:/dp-dev/integ on 11-21) showed 38 "测试 image" burn records from test runs and the
measurement/random/assay works of Disc Lab flows, which the person could not delete.
"""
import json
import os
from pathlib import Path
from unittest.mock import patch

from discprobe import burner, works
from tests.iso_fixture import write_checked_iso

ROOT = Path(__file__).resolve().parents[1]


def repo_records_for(iso):
    target = str(Path(iso).resolve())
    found = []
    for path in (ROOT / "works").glob("*/work.json"):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if any(d.get("iso_path") == target for d in doc.get("discs", [])):
            found.append(path.parent.name)
    return found


def test_each_test_has_its_own_works_library(tmp_path):
    home = Path(os.environ["DISCPROBE_HOME"]).resolve()
    assert tmp_path.resolve() in home.parents
    assert works.Store().root == home / "works"
    assert works.Store().root != (ROOT / "works").resolve()


def test_cli_burn_record_goes_to_the_test_library_not_the_checkout(tmp_path, monkeypatch):
    # The path that left the records: burn CLI with the write mocked, from the repo root.
    from discprobe import __main__
    monkeypatch.chdir(ROOT)
    (tmp_path / "iso").mkdir()
    iso = write_checked_iso(tmp_path / "iso" / "测试 image.iso", bytes(4096))
    with patch.object(burner, "burn", return_value={"result": "completed", "selected_speed_x": 4}), \
            patch.object(burner.disc_identity, "expected_for_write"):
        __main__._main(["burn", "--drive", "H:", "--iso", str(iso), "--speed", "4", "--yes-write", "--no-verify"])
    made = works.Store().list()
    assert [w["name"] for w in made] == ["测试 image"]
    assert works.Store().root.parent == Path(os.environ["DISCPROBE_HOME"]).resolve()
    assert repo_records_for(iso) == []


def test_lab_burns_keep_their_work_records_in_the_lab(tmp_path, monkeypatch):
    from disclab.__main__ import lab_env
    from disclab.lab import Lab
    monkeypatch.delenv("DISCPROBE_HOME", raising=False)
    lab = Lab(tmp_path / "lab")
    assert lab_env(lab)["DISCPROBE_HOME"] == str(lab.root)
    # An explicit choice still wins, as the tests that pass DISCPROBE_HOME themselves expect.
    chosen = str(tmp_path / "chosen")
    assert lab_env(lab, dict(os.environ, DISCPROBE_HOME=chosen))["DISCPROBE_HOME"] == chosen
