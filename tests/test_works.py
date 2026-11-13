"""Works store, CLI and HTTP contract. No real devices or recorder processes."""
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import http.client
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import zipfile

import numpy as np
from PIL import Image
import pytest

from discprobe import __main__ as cli, api, burner, guide, i18n, imagedisc, webui, works


@pytest.fixture
def store(tmp_path, monkeypatch):
    home = tmp_path / "中文 空格 数据"
    monkeypatch.setenv("DISCPROBE_HOME", str(home))
    # Any accidental hardware reachability is a test failure, including enumeration.
    def forbidden(*args, **kwargs):
        raise AssertionError("device access is forbidden in works tests")
    monkeypatch.setattr(guide, "optical_drives", forbidden)
    monkeypatch.setattr(burner, "adapter", forbidden)
    monkeypatch.setattr(cli, "_open", forbidden)
    return works.Store()


def document():
    output = io.BytesIO()
    Image.new("RGBA", (12, 8), (0, 0, 0, 255)).save(output, format="PNG")
    image = "data:image/png;base64," + base64.b64encode(output.getvalue()).decode()
    return dict(format="disc-probe design", version=2, media="dvd", cell=.01,
                geo="results/geo-中文", layers=[dict(kind="image", name="原图", picture=image,
                original=image, x=35, y=0, width=30, rot=0, opacity=1, visible=True)])


def raw_design():
    # Whitespace, UTF-8 and line endings must survive untouched.
    return (json.dumps(document(), ensure_ascii=False, indent=3) + "\r\n").encode("utf-8")


def png():
    stream = io.BytesIO()
    Image.new("RGB", (512, 512), "grey").save(stream, format="PNG")
    return stream.getvalue()


def archive_files(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def test_root_defaults_and_home_override(tmp_path, monkeypatch):
    monkeypatch.delenv("DISCPROBE_HOME", raising=False)
    monkeypatch.chdir(tmp_path)
    assert works.Store().root == tmp_path / "works"
    assert works.Store(tmp_path / "数据" / "results").root == tmp_path / "数据" / "works"
    monkeypatch.setenv("DISCPROBE_HOME", str(tmp_path / "覆盖 根"))
    assert works.Store("elsewhere/results").root == tmp_path / "覆盖 根" / "works"


def test_persistence_assets_thumbnail_history_and_trash(store):
    raw = raw_design()
    work = store.new("锦鲤 一", raw=raw, source_file="D:/中文 路径/锦鲤.discdesign")
    ident = work["id"]
    assert works.ID.fullmatch(ident)
    assert work["cell_um"] == 10 and work["photo_l"] is None
    assert works.Store().show(ident)["name"] == "锦鲤 一"
    assert store.content(ident, "design.discdesign") == raw
    files = archive_files(store.export(ident))
    asset_names = [n for n in files if n.startswith("assets/")]
    assert len(asset_names) == 1
    assert hashlib.sha256(files[asset_names[0]]).hexdigest() == asset_names[0].split("/")[1]
    image = Image.open(io.BytesIO(files["thumb.png"]))
    assert image.size == (512, 512) and image.getextrema()[0] == 0
    prefix = files["history.jsonl"]
    store.patch(ident, dict(name="新名 中文"))
    store.save(ident, raw, thumb=png())
    assert (store.root / ident / "history.jsonl").read_bytes().startswith(prefix)
    copy = store.duplicate(ident, "副本")
    assert copy["id"] != ident and copy["name"] == "副本"
    assert store.content(copy["id"], "design.discdesign") == raw
    store.patch(ident, dict(status="done", note="人工检查"))
    with pytest.raises(works.WorkError, match="reason"):
        store.patch(ident, dict(status="failed"))
    store.patch(ident, dict(status="failed", note="断线"))
    assert store.list("failed", "dvd", "name")[0]["id"] == ident
    store.delete(ident)
    assert store.purge_trash() == []
    with pytest.raises(works.WorkError) as exc:
        store.show(ident)
    assert exc.value.status == 404
    store.restore(ident)
    assert store.show(ident)["history"][-1]["type"] == "restored"
    store.delete(ident)
    path = store.root / ".trash" / ident / "work.json"
    old = json.loads(path.read_bytes())
    old["deleted_at"] = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
    path.write_bytes(works.encoded(old))
    assert store.purge_trash() == [ident]


def test_export_import_every_byte_on_clean_home(store, monkeypatch, tmp_path):
    work = store.new("迁移", raw=raw_design())
    iso = tmp_path / "中文 image.iso"
    iso.write_bytes(bytes(2048))
    store.link(work["id"], iso)
    store.link(work["id"], iso, kind="burn", drive="TEST:", speed=4, disc_code="KOI-A 2-03")
    original = store.export(work["id"])
    monkeypatch.setenv("DISCPROBE_HOME", str(tmp_path / "干净 数据"))
    other = works.Store()
    restored = other.import_bytes(original)
    assert restored["id"] == work["id"]
    assert archive_files(other.export(restored["id"])) == archive_files(original)
    with pytest.raises(works.WorkError) as exc:
        other.import_bytes(original)
    assert exc.value.status == 409


def test_concurrent_if_match_and_recovery(store, monkeypatch):
    work = store.new("并发")
    raw = raw_design()
    def save_once(i):
        try:
            works.Store().save(work["id"], raw, if_match=work["updated_at"])
            return 200
        except works.WorkError as exc:
            return exc.status
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(save_once, range(2))) == [200, 409]
    current = store.show(work["id"])
    store.save(work["id"], raw, if_match='"' + current["updated_at"] + '"')
    current = store.show(work["id"])
    with monkeypatch.context() as patch:
        patch.setattr(works, "stamp", lambda: current["updated_at"])
        updated = store.patch(work["id"], dict(note="同一时刻"))
        assert updated["updated_at"] > current["updated_at"]
    old_history = (store.root / work["id"] / "history.jsonl").read_bytes()
    real = works.atomic
    def power_loss(path, data):
        if Path(path).name == "work.json":
            raise OSError("simulated crash after content publication")
        return real(path, data)
    with monkeypatch.context() as patch:
        patch.setattr(works, "atomic", power_loss)
        with pytest.raises(OSError):
            store.save(work["id"], raw)
    recovered = works.Store().show(work["id"])
    assert recovered["history"][-1]["type"] == "saved"
    assert (store.root / work["id"] / "history.jsonl").read_bytes().startswith(old_history)
    assert not (store.root / work["id"] / ".pending.json").exists()
    assert store.content(work["id"], "design.discdesign") == raw


def test_crash_during_history_append_and_move(store, monkeypatch):
    work = store.new("恢复事务")
    folder = store.root / work["id"]
    real = store._recover
    with monkeypatch.context() as patch:
        patch.setattr(store, "_recover", lambda _: (_ for _ in ()).throw(OSError("crash")))
        with pytest.raises(OSError):
            store.delete(work["id"])
    with (folder / "history.jsonl").open("ab") as stream:
        stream.write(b'{"partial":')
    # Recovery finishes both the append and the pending directory move exactly once.
    assert store.list() == []
    store.restore(work["id"])
    assert [h["type"] for h in store.show(work["id"])["history"]] == ["created", "deleted", "restored"]


@pytest.mark.parametrize("ident", ["../x", "..", "/tmp", "C:/x", "w-20261112-101010-aaaa/../../x", "w-20261112-101010-aaaa\\..", "w-20261112-101010-aaaa:ads", "%2e%2e"])
def test_id_path_traversal(store, ident):
    for action in (store.show, store.delete, store.restore, store.export, store.duplicate):
        with pytest.raises(works.WorkError):
            action(ident)


def test_unsafe_archives_limits_and_design_validation(store):
    for name in ("../escape", "C:/escape", "assets/../../escape", "work.json:ads"):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr(name, b"x")
        with pytest.raises(works.WorkError):
            store.import_bytes(stream.getvalue())
    for doc in ({}, {**document(), "version": 3}, {**document(), "layers": [{}] * 17}):
        with pytest.raises(works.WorkError):
            store.new("坏文档", raw=works.encoded(doc))
    with pytest.raises(works.WorkError) as exc:
        works.read_design(b" " * (works.DESIGN_LIMIT + 1))
    assert exc.value.status == 413
    with pytest.raises(works.WorkError):
        store.set_thumb(store.new("缩略图")["id"], b"not png")


def test_cross_process_writes(store):
    ident = store.new("跨进程")["id"]
    script = "from discprobe.works import Store; import sys; s=Store(); [s.patch(sys.argv[1],dict(note=str(i))) for i in range(8)]"
    children = [subprocess.Popen([sys.executable, "-c", script, ident], stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(2)]
    for child in children:
        out, err = child.communicate(timeout=40)
        assert child.returncode == 0, err.decode(errors="replace")
    assert len(store.show(ident)["history"]) == 17


def test_archive_integrity_links_and_expansion_limits(store, monkeypatch):
    work = store.new("归档校验", raw=raw_design())
    files = archive_files(store.export(work["id"]))
    asset = next(name for name in files if name.startswith("assets/"))
    def pack(changes=None, symlink=False):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, raw in {**files, **(changes or {})}.items():
                if symlink and name == asset:
                    entry = zipfile.ZipInfo(name)
                    entry.create_system = 3
                    entry.external_attr = 0o120777 << 16
                    archive.writestr(entry, raw)
                else:
                    archive.writestr(name, raw)
        return output.getvalue()
    for raw in (pack({asset: b"changed asset"}), pack({"history.jsonl": b"not JSON\n"}), pack(symlink=True)):
        with pytest.raises(works.WorkError):
            store.import_bytes(raw)
    with monkeypatch.context() as patch:
        patch.setattr(works, "ARCHIVE_LIMIT", 4096)
        compressed = pack({"history.jsonl": b" " * 32768})
        assert len(compressed) < 4096
        with pytest.raises(works.WorkError) as exc:
            store.import_bytes(compressed)
        assert exc.value.status == 413
    assert store.content(work["id"], "design.discdesign") == raw_design()


def test_cli_all_commands_and_languages(store, tmp_path, capsys, monkeypatch):
    design = tmp_path / "中文 设计.discdesign"
    design.write_bytes(raw_design())
    thumb = tmp_path / "缩略 图.png"
    thumb.write_bytes(png())
    def run(*argv):
        cli._main(["works", *argv, "--json"])
        return json.loads(capsys.readouterr().out)
    work = run("new", "中文 名称", "--from", str(design))
    ident = work["id"]
    assert run("show", ident)["name"] == "中文 名称"
    assert run("save", ident, str(design), "--thumb", str(thumb))["id"] == ident
    assert run("rename", ident, "改名")["name"] == "改名"
    assert run("duplicate", ident, "复制")["name"] == "复制"
    assert run("duplicate", ident)["name"] == "改名"
    assert run("mark", ident, "done", "--note", "检查过")["status"] == "done"
    assert run("mark", ident, "failed", "--note", "缺角")["status"] == "failed"
    assert run("list", "--status", "failed", "--media", "dvd", "--sort", "name")[0]["id"] == ident
    assert run("delete", ident)["deleted_at"]
    assert run("restore", ident)["id"] == ident
    output = tmp_path / "导出 包.zip"
    assert run("export", ident, str(output))["path"] == str(output)
    assert run("import", str(design))["source_file"] == str(design)
    monkeypatch.setenv("DISCPROBE_HOME", str(tmp_path / "命令行迁移"))
    assert run("import", str(output))["id"] == ident
    again = tmp_path / "再次导出.zip"
    run("export", ident, str(again))
    assert archive_files(output.read_bytes()) == archive_files(again.read_bytes())
    with pytest.raises(SystemExit):
        run("show", "../outside")
    assert "error" in json.loads(capsys.readouterr().err)
    before = i18n.active()
    try:
        for language in ("en", "zh"):
            i18n.use(language)
            cli._main(["works", "show", ident])
            detail = capsys.readouterr().out
            assert ("作品名称" if language == "zh" else "Work name") in detail
            parser, sub, _ = cli._build_parser()
            wp = sub.choices["works"]
            text = wp.format_help()
            assert ("往期" in text) == (language == "zh")
            actions = [a for a in wp._actions if hasattr(a, "choices") and isinstance(a.choices, dict)]
            for action in actions:
                for child in action.choices.values():
                    assert child.format_help()
                    if language == "zh":
                        assert all(any("\u4e00" <= c <= "\u9fff" for c in a.help) for a in child._actions if a.help)
    finally:
        i18n.use(before)


@pytest.fixture
def http_server(store, tmp_path):
    backend = webui.Backend(tmp_path, drive_provider=lambda: [])
    server = webui.Server(backend, 0)
    # Require the existing token without opening a LAN listening socket.
    server.token = "works-test-token"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
    backend.close()
    thread.join()


def request(server, method, path, data=None, content_type="application/json", auth=True, headers=None):
    if isinstance(data, dict):
        data = json.dumps(data, ensure_ascii=False).encode("utf-8")
    hdr = {"Content-Type": content_type, **(headers or {})}
    if auth:
        hdr["X-Discprobe-Token"] = server.token
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=15)
    try:
        connection.request(method, path, data, hdr)
        response = connection.getresponse()
        raw = response.read()
        payload = json.loads(raw) if response.getheader("Content-Type", "").startswith("application/json") else raw
        return response.status, payload
    finally:
        connection.close()


def test_all_http_routes(http_server):
    server = http_server
    status, work = request(server, "POST", "/api/works", dict(name="网页 中文", media="dvd"))
    assert status == 200
    ident, route = work["id"], "/api/works/" + work["id"]
    assert work["thumb_url"] == route + "/thumb"
    assert request(server, "GET", "/api/works?sort=name&status=draft&media=dvd")[1][0]["id"] == ident
    assert request(server, "GET", route)[1]["history"][-1]["type"] == "created"
    initial = request(server, "GET", route + "/design")[1]
    assert initial["format"] == "disc-probe design"
    raw = raw_design()
    status, saved = request(server, "PUT", route + "/design", raw, headers={"If-Match": work["updated_at"]})
    assert status == 200 and saved["updated_at"] != work["updated_at"]
    assert request(server, "PUT", route + "/design", raw, headers={"If-Match": work["updated_at"]})[0] == 409
    assert request(server, "PUT", route + "/thumb", png(), "image/png")[0] == 200
    assert request(server, "GET", route + "/thumb")[1] == png()
    assert request(server, "PATCH", route, dict(name="改名", status="done", note="成品"))[1]["name"] == "改名"
    copied = request(server, "POST", route + "/duplicate", dict(name="副本"))[1]
    assert copied["id"] != ident
    assert request(server, "POST", route + "/duplicate")[0] == 200
    assert request(server, "DELETE", route)[0] == 200
    assert request(server, "GET", route)[0] == 404
    assert request(server, "POST", route + "/restore", {})[0] == 200
    exported = request(server, "GET", route + "/export")[1]
    assert archive_files(exported)["design.discdesign"] == raw
    imported = request(server, "POST", "/api/works/import", raw)[1]
    assert imported["id"] != ident
    other = works.Store(server.backend.root / "clean" / "results")
    # Explicit root isolates an import of the zip while retaining the server token.
    other.root = server.backend.root / "clean" / "works"
    server.backend.works = other
    status, imported = request(server, "POST", "/api/works/import", exported, "application/zip")
    assert status == 200 and imported["id"] == ident
    assert archive_files(other.export(ident)) == archive_files(exported)
    assert request(server, "POST", "/api/works", dict(name="从设计", **{"from": document()}))[0] == 200


def test_http_auth_traversal_limits_and_conflict(http_server):
    server = http_server
    ident = server.backend.works.new("校验")["id"]
    route = "/api/works/" + ident
    for method, suffix, body in (("GET", "", None), ("GET", "/design", None), ("GET", "/thumb", None),
                                 ("GET", "/export", None), ("PUT", "/design", raw_design()),
                                 ("PUT", "/thumb", png()), ("PATCH", "", {}), ("DELETE", "", None),
                                 ("POST", "/duplicate", {}), ("POST", "/restore", {})):
        assert request(server, method, route + suffix, body, auth=False)[0] == 403
    for method, body in (("GET", None), ("POST", {})):
        assert request(server, method, "/api/works", body, auth=False)[0] == 403
    assert request(server, "POST", "/api/works/import", b"{}", auth=False)[0] == 403
    for path in ("/api/works/%2e%2e/design", "/api/works/" + ident + "%2f..%2f..%2fwork.json", "/api/works/C:%5cx/design"):
        assert request(server, "GET", path)[0] in (400, 404)
    assert request(server, "PATCH", route, dict(id="../x"))[0] == 400
    assert request(server, "PUT", route + "/design", raw_design(), "text/plain")[0] == 415
    assert request(server, "PUT", route + "/design", works.encoded({**document(), "layers": [{}] * 17}))[0] == 400
    assert request(server, "PUT", route + "/thumb", b"bad", "image/png")[0] == 400
    assert request(server, "POST", "/api/works", dict(name="bad", **{"from": "../outside.discdesign"}))[0] == 400
    assert request(server, "POST", "/api/works/import", b"not zip", "text/plain")[0] == 415
    assert request(server, "GET", route + "/unknown")[0] == 404
    # Announce a too-large upload without sending it; rejection must not allocate it.
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    connection.putrequest("PUT", route + "/design")
    connection.putheader("X-Discprobe-Token", server.token)
    connection.putheader("Content-Type", "application/json")
    connection.putheader("Content-Length", str(works.DESIGN_LIMIT + 1))
    connection.endheaders()
    assert connection.getresponse().status == 413
    connection.close()
    current = server.backend.works.show(ident)
    def save(_):
        return request(server, "PUT", route + "/design", raw_design(), headers={"If-Match": current["updated_at"]})[0]
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(save, range(2))) == [200, 409]


def test_image_work_cli_completion(store, tmp_path, monkeypatch, capsys):
    ident = store.new("出图")["id"]
    iso = tmp_path / "中文 ISO.iso"
    fit = dict(u=180000, v=5.5, bit_nm_assumed=133.3)
    monkeypatch.setattr(cli, "_geo_fit", lambda *a: fit)
    for name in ("_require_fit_media", "_refuse_audio_fit", "_warn_other_run", "_image_ready"):
        monkeypatch.setattr(cli, name, lambda *a: None)
    monkeypatch.setattr(imagedisc, "grid_design", lambda **kw: np.zeros((32, 32), bool))
    monkeypatch.setattr(imagedisc, "drawing_span", lambda _: None)
    monkeypatch.setattr(imagedisc, "cell_mm", lambda _: .02)
    monkeypatch.setattr(imagedisc, "sectors_to_radius", lambda *a: 64)
    monkeypatch.setattr(imagedisc, "preview", lambda *a: None)
    monkeypatch.setattr(imagedisc, "verify_iso", lambda *a, **kw: [])
    def write(path, *a, **kw):
        Path(path).write_bytes(b"ISO mock bytes")
        return str(path) + ".json"
    monkeypatch.setattr(imagedisc, "write_iso", write)
    cli._main(["image", "--geo", "fit.json", "--output", str(iso), "--work", ident, "--disc-code", "KOI-A 2-03"])
    capsys.readouterr()
    work = store.show(ident)
    assert work["status"] == "iso_ready" and work["history"][-1]["type"] == "iso"
    assert work["discs"][-1]["iso_sha256"] == hashlib.sha256(iso.read_bytes()).hexdigest()
    assert work["discs"][-1]["disc_code"] == "KOI-A 2-03"
    monkeypatch.setattr(imagedisc, "verify_iso", lambda *a, **kw: ["bad sector"])
    cli._main(["image", "--geo", "fit.json", "--output", str(iso), "--work", ident])
    assert len(store.show(ident)["discs"]) == 1


def test_burn_work_success_failure_and_web_argv(store, tmp_path, monkeypatch):
    ident = store.new("刻录关联")["id"]
    iso = tmp_path / "mock.iso"
    iso.write_bytes(bytes(2048))
    monkeypatch.setattr(burner, "burn", lambda *a, **kw: dict(result="completed", selected_speed_x=4,
                        actual_speed_x=4.1, verification=dict(status="skipped")))
    cli._main(["burn", "--drive", "TEST:", "--iso", str(iso), "--work", ident, "--disc-code", "锦鲤 1"])
    work = store.show(ident)
    assert work["status"] == "burned" and work["discs"][-1]["speed"] == 4
    assert work["discs"][-1]["drive"] == "TEST:" and work["discs"][-1]["disc_code"] == "锦鲤 1"
    def fail(*a, **kw):
        raise burner.BurnError("mock failure")
    monkeypatch.setattr(burner, "burn", fail)
    with pytest.raises(SystemExit):
        cli._main(["burn", "--drive", "TEST:", "--iso", str(iso), "--work", ident])
    assert len(store.show(ident)["discs"]) == 1
    payload = dict(action="burn", drive="TEST:", work=ident, args=dict(iso="iso/mock.iso", disc_code="锦鲤 1"))
    argv, drive = webui.command(payload, tmp_path.resolve(), [dict(id="TEST:")])
    assert argv[argv.index("--work") + 1] == ident and argv[argv.index("--disc-code") + 1] == "锦鲤 1"
    with pytest.raises(webui.APIError):
        webui.command({**payload, "work": "../escape"}, tmp_path.resolve(), [dict(id="TEST:")])
    assert "works" in api.version_payload()["capabilities"]


def test_http_workspace_source_and_stable_id(http_server):
    source = http_server.backend.root / "本地 文件.discdesign"
    source.write_bytes(raw_design())
    status, work = request(http_server, "POST", "/api/works", dict(name="本地导入", **{"from": source.name}))
    assert status == 200 and work["source_file"] == str(source)
    route = "/api/works/" + work["id"]
    assert request(http_server, "PATCH", route, dict(name="本地改名"))[1]["id"] == work["id"]
    assert request(http_server, "GET", "/api/works?sort=bad")[0] == 400


def test_shape_and_raster_preview(store):
    raw = works.encoded(dict(format="disc-probe design", version=2, media="cd", cell=.005,
        layers=[dict(kind="image", shape=dict(type="ellipse"), width=40, height=30, x=35)]))
    work = store.new("矢量缩略图", raw=raw)
    assert work["media"] == "cd" and work["cell_um"] == 5
    thumb = np.array(Image.open(io.BytesIO(store.content(work["id"], "thumb.png"))))
    assert thumb.min() == 0 and thumb.max() == 255
    doc = document()
    layer = doc["layers"][0]
    layer.pop("picture")
    layer["raster"] = dict(width=2, height=2, rgba=base64.b64encode(bytes([0, 0, 0, 255]) * 4).decode())
    assert store.new("栅格", raw=works.encoded(doc))["id"]
    doc["geo"] = "results\\中文 空格"
    work = store.new("Windows 路径", raw=works.encoded(doc))
    assert work["geo_run"] == "results/中文 空格"
    assert store.content(work["id"], "design.discdesign") == works.encoded(doc)
    doc["geo"] = "Z:/另一台电脑/geo"
    assert store.new("外来路径", raw=works.encoded(doc))["geo_run"] is None
    # FileReader uses this MIME type when a selected file has no known type.
    doc["layers"][0]["original"] = "data:application/octet-stream;base64," + base64.b64encode(b"original bytes").decode()
    work = store.new("无 MIME 原文件", raw=works.encoded(doc))
    original_name = "assets/" + hashlib.sha256(b"original bytes").hexdigest()
    assert archive_files(store.export(work["id"]))[original_name] == b"original bytes"


def test_junction_cannot_escape(store, tmp_path):
    work = store.new("链接路径")
    outside = tmp_path / "库外证据"
    outside.mkdir()
    evidence = outside / "keep.txt"
    evidence.write_text("original", encoding="utf-8")
    target = store.root / work["id"] / "assets"
    target.rmdir()
    if os.name == "nt":
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(target), str(outside)], capture_output=True)
        assert result.returncode == 0, result.stderr.decode(errors="replace")
    else:
        target.symlink_to(outside, target_is_directory=True)
    try:
        with pytest.raises(works.WorkError, match="unsafe"):
            store.export(work["id"])
        assert evidence.read_text(encoding="utf-8") == "original"
    finally:
        if os.name == "nt":
            target.rmdir()  # remove only the junction itself
        else:
            target.unlink()


def test_web_job_passes_work_and_home_without_recorder(store, tmp_path, monkeypatch):
    ident = store.new("网页任务")["id"]
    (tmp_path / "iso").mkdir()
    (tmp_path / "iso" / "mock.iso").write_bytes(bytes(2048))
    captured = {}
    class FakeChild:
        def __init__(self, argv, *, env, cwd, stdout):
            captured.update(argv=argv, env=env)
        def wait(self):
            return 0
        def poll(self):
            return 0
        def close(self):
            pass
    backend = webui.Backend(tmp_path, runner=FakeChild,
        drive_provider=lambda: [dict(id="TEST:", disc=dict(blank=True))])
    # The completion hook itself is covered by the CLI test; no burner child runs here.
    monkeypatch.setattr(backend, "_watch", lambda job: job.finished.set())
    job = backend.start(dict(action="burn", drive="TEST:", work=ident,
        args=dict(iso="iso/mock.iso"), burn_token=backend.burn_token()["token"]))
    assert job["job"] in backend.jobs
    assert captured["argv"][captured["argv"].index("--work") + 1] == ident
    assert captured["env"]["DISCPROBE_HOME"] == str(store.root.parent)
    # Prevent backend.close from treating the already finished fake job as live.
    backend.jobs[job["job"]].exit = 0
    backend.close()
