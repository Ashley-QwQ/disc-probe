"""Durable post-burn review, no hardware. Keep observations separate from reported evidence."""
import copy
import json

import pytest

from discprobe import __main__ as cli, works
from test_works import store, http_server, request, raw_design, document


def report():
    return dict(result="completed", selected_speed_x=8, actual_speed_x=8.01,
                disc_state=dict(status="completed", disc=dict(disc_status="complete", last_session_state=3)),
                verification=dict(status="completed", ok=96, differing=0, unreadable=0, untested=0))


def burned(store, tmp_path):
    work = store.new("刻后的作品", raw=raw_design())
    iso = tmp_path / "中文 成品.iso"
    iso.write_bytes(b"X" * 32768)
    store.link(work["id"], iso, kind="iso")
    store.link(work["id"], iso, kind="burn", drive="X:", speed=8, report=report())
    return work["id"], iso


@pytest.mark.parametrize("choice", works.AFTER_BURN_CHOICES)
def test_observations_survive_restart_without_changing_report(store, tmp_path, choice):
    ident, _ = burned(store, tmp_path)
    before = copy.deepcopy(store.after_burn(ident)["record"])
    result = store.after_burn(ident, choice, burn_id=before["burn_id"])
    reopened = works.Store().after_burn(ident)
    assert reopened == result
    assert reopened["record"]["observation"]["choice"] == choice
    assert reopened["record"]["report"] == before["report"]
    assert store.show(ident)["status"] == ("done" if choice == "correct" else "burned")
    assert store.show(ident)["history"][-1]["type"] == "after_burn"


def test_snapshot_keeps_iso_design_after_edit_and_new_burn(store, tmp_path):
    ident, iso = burned(store, tmp_path)
    first = store.after_burn(ident)["record"]
    original = store.burn_content(ident, "design")
    changed = document()
    changed["layers"] = []
    store.save(ident, works.encoded(changed))
    assert store.burn_content(ident, "design") == original == raw_design()
    store.link(ident, iso, kind="burn", report=report())
    second = store.after_burn(ident)["record"]
    assert first["burn_id"] != second["burn_id"]
    assert store.burn_content(ident, "design") == original  # same ISO still carries the old design
    store.after_burn(ident, "correct", burn_id=first["burn_id"])
    assert store.after_burn(ident)["record"]["observation"] is None
    assert store.show(ident)["status"] == "burned"  # an older observation cannot complete a newer burn
    with pytest.raises(works.WorkError):
        store.after_burn(ident, "invalid")
    with pytest.raises(works.WorkError):
        store.after_burn(ident, "correct", burn_id="unknown")
    raw = store.export(ident)
    store.delete(ident)
    other = works.Store(tmp_path / "other" / "results")
    other.root = tmp_path / "other" / "works"
    other.import_bytes(raw)
    assert other.burn_content(ident, "design", burn_id=first["burn_id"]) == original


def test_cli_choices_and_view(store, tmp_path, capsys):
    ident, _ = burned(store, tmp_path)
    for choice in works.AFTER_BURN_CHOICES:
        cli._main(["works", "after-burn", ident, "--choice", choice, "--json"])
        assert json.loads(capsys.readouterr().out)["record"]["observation"]["choice"] == choice
    cli._main(["works", "after-burn", ident, "--json"])
    assert json.loads(capsys.readouterr().out)["record"]["report"] == report()


def test_http_review_snapshot_auth_and_stale_burn(http_server, tmp_path):
    server = http_server
    ident, _ = burned(server.backend.works, tmp_path)
    route = "/api/works/" + ident + "/after-burn"
    status, state = request(server, "GET", route)
    assert status == 200
    bid = state["record"]["burn_id"]
    for choice in works.AFTER_BURN_CHOICES:
        status, state = request(server, "PUT", route, dict(choice=choice, burn_id=bid))
        assert status == 200 and state["record"]["observation"]["choice"] == choice
    assert request(server, "GET", route + "/design?burn=" + bid)[1] == json.loads(raw_design())
    assert request(server, "GET", route + "/thumb?burn=" + bid)[1].startswith(b"\x89PNG")
    assert request(server, "PUT", route, dict(choice="correct"))[0] == 400
    assert request(server, "PUT", route, dict(choice=None, burn_id=bid))[0] == 400
    assert request(server, "PUT", route, dict(choice="correct", burn_id="old"))[0] == 404
    assert request(server, "PUT", route, dict(choice="correct", burn_id=bid), auth=False)[0] == 403
    assert request(server, "GET", route + "/measurement")[0] == 404


def test_checkburn_reuses_saved_report_without_opening_a_drive(http_server, tmp_path, monkeypatch):
    from discprobe import checkburn

    def fail(*args, **kwargs):
        pytest.fail('reading a saved checklist accessed the drive')

    monkeypatch.setattr(checkburn, 'check', fail)
    ident, _ = burned(http_server.backend.works, tmp_path)
    before = http_server.backend.works.after_burn(ident)
    route = f"/api/works/{ident}/after-burn/checkburn?burn={before['record']['burn_id']}"
    status, found = request(http_server, 'GET', route)
    assert status == 200 and found['source'] == 'saved_burn'
    assert found['verification'] == report()['verification']
    assert {item['id']: item['status'] for item in found['checklist']}['write'] == 'excluded'
    assert request(http_server, 'GET', route, auth=False)[0] == 403
    assert request(http_server, 'POST', route, {}, auth=False)[0] == 403
    assert request(http_server, 'POST', route, {'drive': 'Y:'})[0] == 400
    assert http_server.backend.works.after_burn(ident) == before


def test_auto_file_unsaved_burn_and_failure_reports(store, tmp_path):
    from types import SimpleNamespace
    from discprobe.works_link import burn_completed
    iso = tmp_path / "unsaved.iso"
    iso.write_bytes(b"X" * 32768)
    args = SimpleNamespace(iso=str(iso), media="dvd", drive="X:", speed=8, work=None)
    burn_completed(args, report())
    state = store.after_burn(args.work)
    assert state["record"]["preview_available"] is False
    failed = dict(report(), result="failed", reason="interrupted")
    burn_completed(args, failed)
    assert store.after_burn(args.work)["record"]["report"]["reason"] == "interrupted"
    assert store.after_burn(args.work)["record"]["preview_available"] is False


def test_legacy_record_gets_stable_identity_without_inventing_preview(store, tmp_path):
    ident, _ = burned(store, tmp_path)
    folder = store.root / ident
    data = json.loads((folder / "work.json").read_bytes())
    last = data["discs"][-1]
    for name in ("burn_id", "design_asset", "thumb_asset", "preview_available", "report"):
        last.pop(name)
    works.atomic(folder / "work.json", works.encoded(data))
    first = store.after_burn(ident)["record"]
    assert store.after_burn(ident)["record"]["burn_id"] == first["burn_id"]
    store.after_burn(ident, "distorted", burn_id=first["burn_id"])
    assert store.after_burn(ident)["record"]["observation"]["choice"] == "distorted"
    with pytest.raises(works.WorkError):
        store.burn_content(ident, "thumb")


def test_failed_cli_attempt_files_only_its_new_log_result(store, tmp_path, monkeypatch):
    from discprobe import burner
    ident, iso = burned(store, tmp_path)
    log = tmp_path / (iso.name + ".burn.jsonl")
    log.write_text(json.dumps(dict(type="burn_result", result="completed")) + "\n", encoding="utf-8")
    def interrupted(*args, **kwargs):
        with log.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(dict(type="burn_result", result="failed", reason="virtual interruption")) + "\n")
        raise burner.BurnError("virtual interruption")
    monkeypatch.setattr(burner, "burn", interrupted)
    monkeypatch.setattr(burner.disc_identity, "expected_for_write", lambda *a, **k: None)
    with pytest.raises(SystemExit):
        cli._main(["burn", "--drive", "X:", "--iso", str(iso), "--work", ident, "--yes-write"])
    assert store.after_burn(ident)["record"]["report"]["reason"] == "virtual interruption"
    count = len(store.show(ident)["discs"])
    def preflight(*args, **kwargs):
        raise burner.BurnError("nothing written")
    monkeypatch.setattr(burner, "burn", preflight)
    with pytest.raises(SystemExit):
        cli._main(["burn", "--drive", "X:", "--iso", str(iso), "--work", ident, "--yes-write"])
    assert len(store.show(ident)["discs"]) == count
