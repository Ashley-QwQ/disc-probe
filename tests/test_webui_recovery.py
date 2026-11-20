"""Drive-free checks for command construction and image job recovery."""
import json
import sys
import pytest
from discprobe import coverage, webui
from tests.iso_fixture import write_checked_iso


def test_recovery_arguments(tmp_path):
    drives = [{"id": "TEST"}]
    prefix = [sys.executable, *(["-P"] if sys.version_info >= (3, 11) else []), "-m", "discprobe"]
    for action, args in [("timing", {}), ("geo", {"speed": "keep"})]:
        argv, drive = webui.command(dict(action=action, drive="TEST", media="cd", args=args), tmp_path, drives)
        assert argv == prefix + [action, "--drive", "TEST", "--media", "cd"] + (["--speed", "keep"] if args else [])
        assert drive == "TEST"
    args = dict(geo="results/test", sectors=300000, output="presets/usable.json", r_min=28, r_max=48)
    argv, _ = webui.command(dict(action="disexport", media="cd", args=args), tmp_path, [])
    assert argv == prefix + ["disexport", "--media", "cd", "--geo", str(tmp_path / "results/test"), "--sectors", "300000", "--output", str(tmp_path / "presets/usable.json"), "--r-min", "28", "--r-max", "48"]
    for action in ("timing", "calibrate", "burn"):
        with pytest.raises(webui.APIError):
            webui.command(dict(action=action, drive="TEST", args={"speed":"keep"}), tmp_path, drives)
    for radius in (0, 59, float("nan"), "28", True):
        with pytest.raises(webui.APIError):
            webui.command(dict(action="disexport", args={**args, "r_min":radius}), tmp_path, [])
    for speed in ("KEEP", "keep --force", True, 0):
        with pytest.raises(webui.APIError):
            webui.command(dict(action="geo", drive="TEST", args={"speed":speed}), tmp_path, drives)


def test_export_radius_order(tmp_path):
    for lo, hi in [(48, 28), (28, 28)]:
        with pytest.raises(webui.APIError, match="r_min must be less"):
            webui.command(dict(action="disexport", args=dict(geo="results/test", sectors=300000,
                           r_min=lo, r_max=hi)), tmp_path, [])


def test_dis_image_nominal_range_never_overrides_measurements():
    nominal = dict(model="dis_import", image_compatible=True)
    request = (29, 52)
    assert coverage.range_warning(nominal, request, allow_dis_nominal=True) is None
    for fit in (nominal, {**nominal, "image_compatible": False}, {"model": "timing"}):
        assert coverage.range_warning(fit, request).startswith("Measured radius coverage is unknown")
    assert coverage.range_warning({"model": "timing"}, request, allow_dis_nominal=True)
    assert coverage.range_warning({**nominal, "image_compatible": False}, request, allow_dis_nominal=True)
    measured = {**nominal, "coverage": {"measured_intervals_mm": [[25, 40], [45, 55]]}}
    assert coverage.range_warning(measured, request, allow_dis_nominal=True) == coverage.range_warning(measured, request)
    assert coverage.range_warning(measured, request).startswith("EXTRAPOLATION")


def test_image_job_restores_only_a_verified_file_for_its_design(tmp_path):
    backend = webui.Backend(tmp_path, drive_provider=lambda: [])
    work = backend.works.new("Test work")["id"]
    design = backend._work_design(work)
    assert backend.image_job(work=work) == {"phase": "idle"}
    directory = tmp_path / "job"
    directory.mkdir()
    job = webui.Job("j-1", None, directory)
    job.action, job.work, job.work_design = "image", work, design
    job.events.write_text(json.dumps({"type": "progress", "fraction": 0.4}) + "\n", encoding="utf-8")
    backend.jobs[job.id] = job
    assert backend.image_job(work=work) == {
        "phase": "making", "job": job.id, "fraction": 0.4, "started_at": job.started_at,
    }
    other = backend.works.new("Another work")["id"]
    assert backend.image_job(work=other) == {"phase": "idle"}
    output = "iso/test.iso"
    image = tmp_path / output
    image.parent.mkdir()
    image.write_bytes(bytes(2048))
    job.exit, job.result = 0, {"path": output}
    assert backend.image_job(ident=job.id) == {"phase": "unverified"}
    write_checked_iso(image, bytes(2048))
    iso = backend.image_job(ident=job.id)["iso"]
    assert (iso["path"], iso["sectors"], iso["bytes"]) == (output, 1, 2048)
    backend.works.link(work, image, source_design_asset=design)
    restarted = webui.Backend(tmp_path, drive_provider=lambda: [])
    assert restarted.image_job(work=work)["iso"]["path"] == output
    image.write_bytes(bytes(4096))
    assert restarted.image_job(work=work) == {"phase": "unverified"}
    doc = json.loads(backend.works.content(work, "design.discdesign"))
    doc["cell"] = .01
    backend.works.save(work, json.dumps(doc).encode())
    assert backend.image_job(work=work) == {"phase": "idle"}


def test_image_texture_list_accepts_random_and_identifies_a_bad_entry(tmp_path):
    entry = {"action": "image", "args": {"geo": "results/test", "textures": ["A5", "RND", "Ba00"]}}
    argv, _ = webui.command(entry, tmp_path, [])
    assert argv[argv.index("--textures") + 1:][:3] == ["A5", "RND", "Ba00"]
    for bad in ("ABX", "RND --output z", 42):
        entry["args"]["textures"][1] = bad
        with pytest.raises(webui.APIError, match=r"第 2 项纹理无效.*Invalid texture at entry 2") as caught:
            webui.command(entry, tmp_path, [])
        assert caught.value.code == "invalid_texture"
