"""The practice flow (disc-probe's step names and order), the drive settings and the desk page's server."""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from disclab.__main__ import ROOT
from disclab.lab import Lab
from disclab.tests.test_interface import cli, envelope, free_port

# disc-probe's own names (web/home calibrate.js, preview.js, burn.js), in its order
DP_ORDER = ["检测空白盘", "生成测量镜像", "刻录测量盘", "测转速", "测几何", "放进图片", "生成检查盘", "刻检查盘",
            "拍摄光盘", "读出沿轨常数", "生成成品", "刻录成品", "对照真值"]


@pytest.fixture()
def lab(tmp_path):
    root = tmp_path / "desk lab 测试"
    envelope(cli("box", "--json", "--lab", root, "--count", "3"))
    return Lab(root)


def status(lab):
    return envelope(cli("status", "--json", "--lab", lab.root))["outputs"]["status"]


def test_flow_has_disc_probes_steps_in_order(lab):
    st = status(lab)
    assert [s["zh"] for s in st["flow"]] == DP_ORDER
    assert st["current"] == "blank" and sum(s["current"] for s in st["flow"]) == 1
    assert all(s["why"]["zh"] and s["why"]["en"] for s in st["flow"])
    assert {d["state"] for d in st["box"]["discs"]} == {"blank"}
    # public only: the status never carries the hidden truth
    text = json.dumps(st)
    truth = lab.answers()["discs"][lab.box()["discs"][0]]
    assert "true_u" not in text and str(truth.get("u", "never")) not in text


def test_step_order_and_tray_are_checked(lab):
    value = envelope(cli("step", "timing", "--json", "--lab", lab.root), "error")
    assert "先完成" in value["errors"][-1]["message"]
    value = envelope(cli("step", "blank", "--json", "--lab", lab.root), "error")
    assert "托盘里没有盘" in value["errors"][-1]["message"]
    swap = envelope(cli("swap", "--json", "--lab", lab.root))["outputs"]
    assert swap["disc"] == lab.box()["discs"][0]
    assert swap["status"]["drives"]["X:"]["tray"] == swap["disc"]
    rows = lab.state()["steps"]["flow"]
    assert [r["status"] for r in rows] == ["error", "error"]


def test_drive_reader_and_faults(lab):
    out = envelope(cli("drive", "--json", "--lab", lab.root, "--reader", "noisy",
                       "--fault", 'read_error:{"r_mm":[40,41]}'))["outputs"]
    assert out["reader"] == "noisy" and out["faults"][0]["kind"] == "read_error"
    assert lab.answers()["faults"][0]["params"] == {"r_mm": [40, 41]}
    bad = envelope(cli("drive", "--json", "--lab", lab.root, "--fault", 'read_error:{"lba":[1,2],"r_mm":[1,2]}'), "error")
    assert "invalid fault" in bad["errors"][-1]["message"]
    assert len(lab.answers()["faults"]) == 1
    envelope(cli("drive", "--json", "--lab", lab.root, "--reader", "nope"), "error")
    out = envelope(cli("drive", "--json", "--lab", lab.root, "--clear", "all"))["outputs"]
    assert out["faults"] == [] and lab.answers()["faults"] == []
    assert status(lab)["drives"]["X:"]["reader"] == "noisy"


def test_inline_scenario_basket(tmp_path):
    root = tmp_path / "inline"
    scenario = {"version": 1, "discs": {"media": "dvd-r", "count": 2, "seed": 4, "parameters": {"ecc_um": 25},
                                        "initial_state": [{"state": "partial", "random": True, "sectors": 64,
                                                           "fraction": 0.5}, "blank"]}}
    envelope(cli("box", "--json", "--lab", root, "--scenario-json", json.dumps(scenario)))
    lab = Lab(root)
    assert (root / "scenario.json").exists()
    st = status(lab)
    assert [d["state"] for d in st["box"]["discs"]] == ["open", "blank"]
    assert all(d["ecc_um"] == 25 for d in lab.answers()["discs"].values())
    swap = envelope(cli("swap", "--json", "--lab", root))["outputs"]
    assert swap["disc"] == lab.box()["discs"][1]


def test_practice_resumes_an_existing_lab(lab):
    from disclab.practice import prepare
    before = lab.box_path.read_bytes()
    assert prepare(lab.root).root == lab.root
    assert lab.box_path.read_bytes() == before


def _get(url):
    with urlopen(url, timeout=20) as r:
        return r.status, r.read()


def _post(url, body):
    req = Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read())
    except HTTPError as e:
        return e.code, json.loads(e.read())


def test_desk_server_translates_to_commands(lab, tmp_path):
    port = free_port()
    err = tmp_path / "desk.err"
    with err.open("w", encoding="utf-8") as fh:
        child = subprocess.Popen([sys.executable, "-B", "-m", "disclab", "desk", "--lab", str(lab.root), "--port", str(port)],
                                 cwd=ROOT, stdout=subprocess.DEVNULL, stderr=fh, env=dict(os.environ, PYTHONIOENCODING="utf-8"),
                                 creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
        try:
            base = f"http://127.0.0.1:{port}"
            for _ in range(150):
                try:
                    code, page = _get(base + "/")
                    break
                except OSError:
                    time.sleep(0.1)
            else:
                pytest.fail("desk did not start: " + err.read_text(encoding="utf-8"))
            assert code == 200 and "lab.js" in page.decode()
            assert _get(base + "/lobby/lobby.json")[0] == 200
            st = json.loads(_get(base + "/api/status")[1])
            assert st["status"] == "ok" and st["outputs"]["status"]["current"] == "blank"
            code, r = _post(base + "/api/run", {"argv": ["swap"]})
            assert code == 200 and r["status"] == "ok"
            assert Lab(lab.root).state()["drives"]["X:"]["tray"] == lab.box()["discs"][0]
            # only lab commands, and the page never chooses the lab or the output format
            assert _post(base + "/api/run", {"argv": ["dp", "--", "burn"]})[0] == 400
            assert _post(base + "/api/run", {"argv": ["tray", "--lab", "elsewhere"]})[0] == 400
            for bad in ("/api/file?path=" + str(Path(ROOT) / "README.md"), "/../disclab/flow.py"):
                with pytest.raises(HTTPError):
                    _get(base + bad)
            code, r = _post(base + "/api/run", {"argv": ["step", "timing"]})
            job = r["job"]
            for _ in range(200):
                view = json.loads(_get(base + f"/api/job/{job}")[1])
                if view["state"] != "running":
                    break
                time.sleep(0.1)
            assert view["state"] == "failed" and "先完成" in view["result"]["errors"][-1]["message"]
        finally:
            child.send_signal(signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGINT)
            child.wait(timeout=15)
    assert any(r["status"] == "stopped" for r in Lab(lab.root).state()["steps"]["desk"])


def test_photos_add_up_until_the_reader_gives_L(lab, monkeypatch):
    """No L from the photos sends the flow back to 拍摄光盘; the next reading uses every photo of the disc."""
    from disclab import flow
    from disclab.lab import atomic_json
    from disclab.tests.test_interface import PRE_PHOTO, _flow_done
    disc = lab.box()["discs"][1]
    geo = lab.root / "results" / "geo-X-1"
    atomic_json(geo / "summary.json", {"fit": {}})
    _flow_done(lab, *PRE_PHOTO[:4], "geo", paths=[str(geo)])
    _flow_done(lab, *PRE_PHOTO[5:-1], "photos", disc=disc, paths=["a/IMG_1.jpg", "a/IMG_2.jpg"])
    seen = []

    def reader(lab_, *args):
        assert args[0] == "photo"
        seen.append([a for a in args if str(a).endswith(".jpg")])
        run = Path(args[args.index("--run") + 1])
        atomic_json(run / "photo.json", dict(verdict="unsure", offset_mm=None, photos=[]) if len(seen) == 1
                    else dict(verdict="ok", offset_mm=0.2, photos=[]))
    monkeypatch.setattr(flow, "_dp", reader)
    monkeypatch.setattr(flow, "_geo_folder", lambda lab_: geo)
    with pytest.raises(flow.StepError, match="Photograph the disc again"):
        flow.run_step(lab, "photo")
    assert next(s for s in flow.plan(lab) if s["current"])["key"] == "photos"
    time.sleep(0.01)
    lab.step("flow", key="photos", status="ok", disc=disc, paths=["b/IMG_3.jpg"])
    rec = flow.run_step(lab, "photo")
    assert rec["offset_mm"] == 0.2 and rec["photos"] == 3
    assert seen[1] == ["a/IMG_1.jpg", "a/IMG_2.jpg", "b/IMG_3.jpg"]
    assert next(s for s in flow.plan(lab) if s["current"])["key"] == "final"


def test_console_names_follow_disc_probes_guide():
    """The TUI names every step in the guided console's words; the ones the console has match it exactly."""
    import re
    from disclab import flow, tui
    assert set(tui.CONSOLE) == set(flow.KEYS)
    zh = (Path(ROOT) / "discprobe" / "zh.py")
    if not zh.exists():
        pytest.skip("no discprobe beside this disclab")
    text = zh.read_text(encoding="utf-8")
    for key, english in (("blank", "Blank disc (info)"), ("measure_image", "Random-data disc"),
                         ("timing", "Drive check (timing)"), ("geo", "Geometry (geo)"), ("picture", "Picture ISO (image)")):
        found = re.search(r'"%s": "([^"]+)"' % re.escape(english), text)
        assert found, english
        assert tui.CONSOLE[key][0].startswith(found.group(1)), (key, found.group(1))


def test_cd_burns_through_the_flow(tmp_path):
    """disc-probe's burn expects a DVD unless told; the flow says which disc it is."""
    root = tmp_path / "cd lab"
    envelope(cli("box", "--json", "--lab", root, "--media", "cd-r", "--count", "2"))
    envelope(cli("swap", "--json", "--lab", root))
    for key in ("blank", "measure_image", "measure_burn"):
        envelope(cli("step", key, "--quick", "--json", "--lab", root))
    st = status(Lab(root))
    assert st["current"] == "timing" and st["box"]["discs"][0]["state"] == "burned"


def _web_lab(lab):
    """What disc-probe's own page leaves in a lab after a whole DVD round, without running it."""
    from disclab.lab import atomic_json
    t0 = time.time() - 1000
    clock = iter(range(0, 1000, 10))

    def stamp(path):
        t = t0 + next(clock)
        os.utime(path, (t, t))
        return t
    lab.step("web", status="started")
    results, iso = lab.root / "results", lab.root / "iso"
    discs = lab.box()["discs"]
    atomic_json(results / "info-X-1" / "info.json", {})
    stamp(results / "info-X-1" / "info.json")
    burns = {}
    for disc, name, extra in ((discs[0], "dvd-measurement-1.iso", None), (discs[1], "check-1.iso", "check"),
                              (discs[2], "my-picture-2.iso", "final")):
        if extra == "check":
            atomic_json(iso / "my-picture-1.image.json", dict(photo_l=dict(written=False)))
            stamp(iso / "my-picture-1.image.json")
            atomic_json(iso / "check-1.image.json", dict(check_disc=True))
            stamp(iso / "check-1.image.json")
        if extra == "final":
            photo = results / "geo-X-1" / "photo.json"
            atomic_json(photo, dict(verdict="ok", offset_mm=0.18))
            stamp(photo)
            atomic_json(iso / "my-picture-2.image.json", dict(photo_l=dict(written=True, L_mm=0.18)))
            stamp(iso / "my-picture-2.image.json")
        when = t0 + next(clock)
        burns[disc] = dict(sessions=[dict(iso=str(iso / name), iso_mtime=when - 5, when=when)], closed=True)
        if extra is None:
            for kind in ("timing", "geo"):
                path = results / f"{kind}-X-1" / "summary.json"
                atomic_json(path, dict(fit=dict(measured_span_mm=[25.0, 57.0])) if kind == "geo" else {})
                stamp(path)
        if extra == "check":         # `disclab photos`, twice (a retake), between the check burn and the reading
            shots = [dict(t=t0 + next(clock), status="ok", disc=disc, paths=paths)
                     for paths in (["p/IMG_1.jpg", "p/IMG_2.jpg"], ["q/IMG_3.jpg"])]
    with lab.locked_state() as st:
        st["burns"] = burns
        st.setdefault("steps", {}).setdefault("photos", []).extend(shots)
    return discs


def test_progress_on_disc_probes_own_page_shows_in_the_lab(lab):
    """`practice` runs disc-probe's page, which keeps its own progress; status reads it back from the lab."""
    from disclab import flow
    discs = _web_lab(lab)
    rows = {s["key"]: s for s in flow.plan(lab)}
    assert all(rows[k]["done"] for k in flow.KEYS if k != "score"), [(k, v["done"]) for k, v in rows.items()]
    assert rows["score"]["current"]
    assert rows["geo"]["disc"] == discs[0] and rows["photo"]["disc"] == discs[1]
    assert rows["photos"]["detail"].startswith("这张盘共 3 张")
    assert rows["final_burn"]["disc"] == discs[2]
    st = status(lab)
    assert [d["used_for"] for d in st["box"]["discs"]] == ["measure_burn", "check_burn", "final_burn"]
    # a lab disc-probe's page never served reads only its own records
    with lab.locked_state() as raw:
        raw["steps"].pop("web")
    assert flow.web_records(lab) == [] and flow.plan(lab)[0]["current"]


def test_practice_banner_says_how(tmp_path):
    from disclab.practice import guide
    lab = Lab(tmp_path / "banner")
    dvd, cd = guide(lab, "dvd-r"), guide(lab, "cd-r")
    for text in (dvd, cd):
        assert "从电脑添加照片" in text and "Add a photo from this computer" in text
        assert f'swap --lab "{lab.root}"' in text and "--seed" in text and "status --lab" in text
    assert "--media cd" in cd and "--media cd" not in dvd


def test_plain_commands_print_for_a_person(lab):
    out = cli("drive", "--lab", lab.root, "--reader", "noisy", "--fault", 'read_error:{"r_mm":[40,41]}')
    assert "noisy" in out.stdout and "read_error" in out.stdout
    out = cli("swap", "--lab", lab.root)
    assert lab.box()["discs"][0] in out.stdout and "{" not in out.stdout
    out = cli("status", "--lab", lab.root)
    assert "<- 现在到这里" in out.stdout and "检测空白盘" in out.stdout
    assert envelope(cli("status", "--json", "--lab", lab.root))["outputs"]["status"]["current"] == "blank"


def test_status_is_not_recorded_and_old_copies_are_dropped(lab):
    """status only reads; recording its reply each time grew one lab's state.json to 95 MB (5302 copies)."""
    before = lab.state().get("steps", {}).get("status", [])
    status(lab)
    status(lab)
    assert lab.state().get("steps", {}).get("status", []) == before
    with lab.locked_state() as st:                      # a lab from before the fix
        st.setdefault("steps", {})["status"] = [dict(t=0, outputs={})] * 3
    lab.step("tray", drive="X:")                        # any later write clears them
    assert "status" not in lab.state()["steps"]


def test_desk_runs_one_status_at_a_time(lab, monkeypatch):
    import threading
    from disclab import desk as D
    calls, running, peak = [], [0], [0]

    def slow(argv, root):
        running[0] += 1
        peak[0] = max(peak[0], running[0])
        time.sleep(0.4)
        running[0] -= 1
        calls.append(time.time())
        return dict(status="ok", outputs={})
    monkeypatch.setattr(D, "run_quick", slow)
    desk = D.Desk(lab)
    first = threading.Thread(target=desk.status)
    first.start()
    time.sleep(0.05)
    late = [threading.Thread(target=desk.status) for _ in range(6)]
    for t in late:
        t.start()
    for t in [first, *late]:
        t.join()
    assert peak[0] == 1                 # never two status processes together
    assert len(calls) == 1              # the six that came while it ran share its reply
    desk.status()
    assert len(calls) == 2              # a later ask runs it again
