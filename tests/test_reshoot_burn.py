"""DVD check-disc reshoots, durable selection and the unchanged photo gate."""
import hashlib
import json
from pathlib import Path
from unittest.mock import Mock

from PIL import Image
import pytest

from discprobe import pcal, photo, photo_burns, webui
from discprobe.__main__ import main


@pytest.fixture
def check(tmp_path):
    run = tmp_path / "results" / "geo-X-20261123-160000"
    run.mkdir(parents=True)
    (run / "summary.json").write_text(json.dumps(dict(fit=dict(media="dvd", bit_nm_assumed=133.3),
        identity=dict(drive="sample drive", device_id="X:"))), encoding="utf-8")
    image = tmp_path / "iso" / "check.iso"
    image.parent.mkdir()
    image.with_suffix(".image.json").write_text(json.dumps(dict(check_disc=True,
        geometry_from=str(run / "summary.json"))), encoding="utf-8")
    return tmp_path, run, image


def write_burn(image, stamp, *, legacy=False, **changes):
    log = Path(str(image) + ".burn.jsonl")
    row = dict(type="burn_result", result="completed", media="dvd", image=str(image), log_path=str(log),
               time=stamp, drive="X:")
    if not legacy:
        row.update(burner="X:", path="Disc Lab", mode="DVD data", disc_id=f"T{stamp}")
    row.update(changes)
    with log.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row) + "\n")
    return row


def test_completed_burns_for_exact_check_and_run(check):
    root, run, image = check
    write_burn(image, 101, result="failed")
    write_burn(image, 102, result="cancelled")
    assert photo_burns.listing(root, run) == dict(burns=[], unavailable=[])
    with pytest.raises(ValueError, match="No completed"):
        photo_burns.select(root, run, "absent")
    write_burn(image, 103)
    assert [r["disc_id"] for r in photo_burns.listing(root, run)["burns"]] == ["T103"]
    write_burn(image, 105)
    write_burn(image, 104)
    wrong = image.with_name("picture.iso")
    wrong.with_suffix(".image.json").write_text(json.dumps(dict(geometry_from=str(run / "summary.json"))))
    write_burn(wrong, 106)
    spec = image.with_suffix(".image.json")
    write_burn(image, 107, check_spec_sha256="1" * 64)
    write_burn(image, 108, check_spec_sha256=hashlib.sha256(spec.read_bytes()).hexdigest())
    with Path(str(image) + ".burn.jsonl").open("ab") as stream:
        stream.write(b'{"truncated":"\xff')
    assert [r["disc_id"] for r in photo_burns.listing(root, run)["burns"]] == ["T108", "T105", "T104", "T103"]


def test_old_web_record_requires_exact_path_and_event_time(check):
    root, run, image = check
    saved = write_burn(image, 103, legacy=True)
    job = root / ".webui-jobs" / "j-test"
    job.mkdir(parents=True)
    report = job / "burn.json"
    row = dict(saved, burner="X:", burn_path="IMAPI", burn_mode="DVD data")
    for changes in ({"time": 103.01}, {"log_path": saved["log_path"] + "-other"}):
        report.write_text(json.dumps(dict(row, **changes)), encoding="utf-8")
        assert photo_burns.listing(root, run)["unavailable"] == ["legacy_burn"]
        with pytest.raises(ValueError, match="before 1.0.0"):
            photo_burns.select(root, run, "absent")
    report.write_text(json.dumps(row), encoding="utf-8")
    [record] = photo_burns.listing(root, run)["burns"]
    assert record["disc_id"] is None
    with pytest.raises(ValueError, match="number written on the disc"):
        photo_burns.select(root, run, record["id"])
    recovered = photo_burns.select(root, run, record["id"], disc_id="label")
    assert recovered["burn_record"]["source"] == "webui-job"
    assert recovered["burn_path"] == "IMAPI"
    write_burn(image, 104, path="unknown")
    assert photo_burns.listing(root, run)["unavailable"] == ["unknown_burn"]


def test_pick_second_after_restart_and_apply_written_number(check, monkeypatch, capsys):
    root, run, image = check
    write_burn(image, 103)
    write_burn(image, 104)
    before = webui.Backend(root, drive_provider=lambda: [])
    selected = before.photo_burn_listing(run.name)["burns"][0]
    before.close()
    after = webui.Backend(root, drive_provider=lambda: [])
    try:
        assert after.photo_burn_listing(run.name)["burns"][0] == selected
        names = []
        for i in range(2):
            path = root / f"pose{i}.png"
            Image.new("RGB", (10, 10), (i, 100, 100)).save(path)
            names.append(str(path))
        reader = Mock(side_effect=[dict(status="ok", L_mm=1.0, zone_spread_mm=.2, c_deg=angle)
                                   for angle in (0, 30)])
        monkeypatch.setattr(pcal, "read_photo", reader)
        monkeypatch.setattr(pcal, "combine", lambda rows: dict(status="ok"))
        monkeypatch.chdir(root)
        main(["photo", "--run", str(run), "--media", "dvd", "--list-burns"])
        listing = capsys.readouterr().out
        assert listing.index("T104") < listing.index("T103")
        assert "Next:" in listing
        main(["photo", "--run", str(run), "--media", "dvd", "--photos", *names,
              "--burn-record", selected["id"], "--disc-id", "on-disc"])
        assert "Next: generate the picture" in capsys.readouterr().out
        decision = photo.photo_l(run)
        assert decision["written"]
        provenance = decision["provenance"]
        assert provenance["disc_id"] == "on-disc"
        assert provenance["burn_path"] == dict(burner="X:", path="Disc Lab", mode="DVD data")
        assert provenance["burn_record"] == dict(id=selected["id"], time=104, source="iso-burn-log",
            log_path=str(image) + ".burn.jsonl", recorded_disc_id="T104", disc_id_overridden=True)
        assert photo.photo_l(run, frozen=decision) == decision
    finally:
        after.close()


def test_uploads_follow_selected_burn_and_phone_link(check):
    root, run, image = check
    write_burn(image, 103)
    write_burn(image, 104)
    later, earlier = [r["id"] for r in photo_burns.listing(root, run)["burns"]]
    store = photo.PhotoStore(root / "results")
    later_phone, earlier_phone = (store.token(run.name, selected) for selected in (later, earlier))
    assert later_phone != earlier_phone
    a = store.upload(run.name, b"one", "image/png", "a.png", token=later_phone)
    b = store.upload(run.name, b"two", "image/png", "b.png", token=earlier_phone)
    fresh = photo.PhotoStore(root / "results")
    assert fresh.listing(run.name, later)["photos"][0]["id"] == a["id"]
    assert fresh.listing(run.name, earlier)["photos"][0]["id"] == b["id"]
    assert fresh.listing(run.name)["photos"] == []
    with pytest.raises(ValueError, match="another burn"):
        fresh.argv(dict(run=run.name, media="dvd", photos=[a["id"]], burn_record=earlier))
