"""Drive-free backend tests. The only children are tiny Python scripts below."""
import contextlib
import http.client
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from discprobe import guide, ui, webui

ROOT = Path(__file__).resolve().parents[1]


def eventually(check, timeout=8):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = check()
        if value:
            return value
        time.sleep(0.02)
    raise AssertionError("timed out")


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        # Never enumerate or open real drives, even indirectly through guide rendering.
        for name, value in (("optical_drives", ["H:", "I:"]),
                            ("missing_packages", []), ("picture_iso", None)):
            replacement = patch.object(guide, name, return_value=value)
            replacement.start()
            self.addCleanup(replacement.stop)

    def result(self, kind, summary, stamp="20261107-101500"):
        folder = self.root / "results" / f"{kind}-H-{stamp}"
        folder.mkdir(parents=True)
        (folder / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
        if kind == "geo":
            (folder / "targets.csv").write_text("lba,n_bits\n" + "100,1000\n" * 12, encoding="utf-8")
        return folder

    def test_workflow_shared_current_and_verdicts(self):
        def check(expected):
            state = guide.guide_state("dvd", str(self.root / "results"))
            self.assertEqual(state["current"], expected)
            row = next(s for s in state["steps"] if s["id"] == expected)
            for notes in (False, True):
                lines = guide.guide_lines("dvd", str(self.root / "results"), notes=notes)
                if notes:
                    marked = [line for line in lines if "you are here" in line]
                    self.assertEqual(len(marked), 1)
                    self.assertIn(row["label"], marked[0])
            self.assertEqual([s["id"] for s in state["steps"]],
                             ["packages", "drive", "random_disc", "timing", "geo", "photo_l", "picture_iso", "burn"])
            json.dumps(state)
            return state
        check("random_disc")
        self.result("timing", {"period": {"rotation": {"mode": "CAV"}, "zones": [{"jitter_deg": 0.5}]}})
        state = check("geo")
        self.assertEqual(state["steps"][3]["verdict"], "good")
        self.result("geo", {"fit": {"u": 180000, "v": 5.5, "chi2_per_dof": 1,
                                   "measured_span_mm": [25, 56], "angle_sigma_measured_span_deg": .1}})
        state = check("picture_iso")
        self.assertEqual(state["steps"][4]["verdict"], "good")
        # A later stopped attempt must not displace a completed calibration.
        self.result("geo", {"stopped": "tray open"}, stamp="20261108-101500")
        self.assertEqual(check("picture_iso")["steps"][4]["verdict"], "good")

    def test_partial_and_simulated_results(self):
        self.result("geo", {"stopped": "interrupted"})
        state = guide.guide_state("dvd", str(self.root / "results"))
        self.assertEqual(state["steps"][4]["verdict"], "stopped_early")
        self.result("timing", {"simulated": True, "period": {"rotation": {"mode": "CAV"}}})
        self.assertEqual(guide.guide_state("dvd", str(self.root / "results"))["current"], "random_disc")
        self.assertTrue(guide.guide_state("cd", str(self.root / "results"))["steps"][5]["needed"])

    def test_event_opt_in_and_terminal_bytes(self):
        # Frozen bytes captured from the original module, before this change.
        # Keep the baseline independent of future commits and a local git checkout.
        meter = "\r[==========>.........]   50%  reading  0:00  about 0:10 left  Ctrl+C to stop"
        wipe = "\r" + " " * 76 + "\r"
        warning = ("Careful: burning a DVD+R, DVD-R or CD-R cannot be undone; only RW discs can be erased. "
                   "Check the image and the disc first.\n")
        expected = (meter + wipe + "hello\n" + meter + wipe + warning).encode("utf-8")
        def output(module, event_file=None):
            stream = io.StringIO()
            term = module.Term(stream, env={"TERM": "dumb"})
            term.interactive = True
            env = dict(os.environ)
            env.pop("DISCPROBE_EVENTS", None)
            if event_file:
                env["DISCPROBE_EVENTS"] = str(event_file)
            with patch.dict(os.environ, env, clear=True), patch.object(module.time, "monotonic", return_value=10), patch.object(module.shutil, "get_terminal_size", return_value=os.terminal_size((80, 24))):
                p = module.Progress(lambda: (.5, "reading", 10), term)
                p.tick(force=True)
                p.log("hello")
                p.close()
                module.burn_warning(term, pause=lambda _: None)
            return stream.getvalue().encode("utf-8")
        self.assertEqual(output(ui), expected)
        events = self.root / "events"
        self.assertEqual(output(ui, events), expected)
        rows = [json.loads(x) for x in events.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([e["type"] for e in rows], ["progress", "log", "progress", "log"])
        self.assertEqual(rows[-1]["level"], "warning")

    def test_job_log_comes_from_the_command_line_output(self):
        folder = self.root / "job"
        folder.mkdir()
        job = webui.Job("j-1", "H:", folder)
        job.events.write_text(json.dumps(dict(type="log", text="careful", level="warning")) + "\n", encoding="utf-8")
        job.output.write_bytes(b"Zone 0.05: T = 10.1 ms\r\nsame\nsame\ncareful\npartial")
        job.read()
        logs = [e for e in job.history if e["type"] == "log"]
        self.assertEqual([e["text"] for e in logs], ["Zone 0.05: T = 10.1 ms", "same", "same", "careful"])
        self.assertEqual(logs[-1]["level"], "warning")
        self.assertEqual(len({json.dumps(e) for e in logs}), 4)     # repeated lines stay distinct
        with job.output.open("ab") as f:
            f.write(b" line\n")
        job.read()
        self.assertEqual(job.history[-1]["text"], "partial line")
        # colour stays for the terminal page (ansi), other escapes go, and the plain words stay plain
        with job.output.open("ab") as f:
            f.write(b"\x1b]9;4;1;40\x07\x1b[?25l\x1b[32mISO ready!\x1b[0m\n")
        job.read()
        self.assertEqual(job.history[-1]["text"], "ISO ready!")
        self.assertEqual(job.history[-1]["ansi"], "\x1b[32mISO ready!\x1b[0m")

    def test_force_color_paints_without_a_terminal(self):
        plain = ui.Term(io.StringIO(), env={})
        forced = ui.Term(io.StringIO(), env={"FORCE_COLOR": "3"})
        self.assertFalse(plain.color)
        self.assertTrue(forced.color and forced.truecolor)
        self.assertFalse(forced.animate or forced.interactive)        # colour only: nothing redrawn in place
        self.assertTrue(forced.reader and not plain.reader)           # the lines meant for people are printed
        self.assertFalse(ui.Term(io.StringIO(), env={"FORCE_COLOR": "3", "NO_COLOR": "1"}).color)
        self.assertEqual(forced.style("ok", "green"), "\x1b[32mok\x1b[0m")

    def test_ask_answer_and_timeout(self):
        events = self.root / "events"
        env = {"DISCPROBE_EVENTS": str(events), "DISCPROBE_ASK_TIMEOUT": "2"}
        with patch.dict(os.environ, env), patch.object(ui, "term", side_effect=AssertionError("no terminal input")):
            replies = []
            thread = threading.Thread(target=lambda: replies.append(ui.ask("Move tray?", False, kind="tray")))
            thread.start()
            def question():
                if not events.exists():
                    return None
                try:
                    return json.loads(events.read_text(encoding="utf-8").splitlines()[0])
                except (IndexError, ValueError):
                    return None
            event = eventually(question)
            Path(str(events) + ".answers").write_text(json.dumps(dict(id=event["id"], yes=True)) + "\n", encoding="utf-8")
            thread.join(3)
            self.assertEqual(replies, [True])
            self.assertEqual(event["kind"], "tray")
            with patch.dict(os.environ, {"DISCPROBE_ASK_TIMEOUT": "0"}):
                self.assertFalse(ui.ask("Timeout?", False))
        self.assertEqual(json.loads(events.read_text(encoding="utf-8").splitlines()[-1])["timeout"], True)

    def test_geo_location_and_throttle(self):
        from types import SimpleNamespace
        dev = SimpleNamespace(event_lba=1000, pauses=10)
        ladder = SimpleNamespace(reps=24, targets=[], T=None, max_targets=22,
                                 prior=SimpleNamespace(bit_nm=133.3), u=180000, v=5.5,
                                 cov=None, _n_end=lambda lba: lba * 38688)
        status = ui.geo_status(ladder, dev)
        self.assertEqual(status.location(), {"lba": 1000})
        ladder.targets.append({})
        self.assertNotIn("radius_mm", status.location())
        ladder.cov = object()  # A fit now exists; targets alone can still be priors.
        self.assertGreater(status.location()["radius_mm"], 0)
        events = self.root / "events"
        with patch.dict(os.environ, {"DISCPROBE_EVENTS": str(events)}), patch.object(ui.time, "monotonic", return_value=10):
            p = ui.Progress(status, ui.Term(io.StringIO(), env={"TERM": "dumb"}))
            for _ in range(50):
                p.tick(force=True)
            self.assertEqual(len(events.read_text().splitlines()), 1)
            p.close()
        self.assertIn("radius_mm", json.loads(events.read_text().splitlines()[0]))

    def backend(self, script=None):
        def runner(argv, **kwargs):
            self.argv = argv
            code = script or '''import json, os, time
p = os.environ['DISCPROBE_EVENTS']
with open(p, 'a') as f:
 f.write(json.dumps(dict(type='progress', fraction=.25, stage='fake', eta_s=1))+'\\n')
 f.write(json.dumps(dict(type='ask', id='q1', question='Continue?', default=False, kind='tray'))+'\\n')
 f.flush()
time.sleep(60)
'''
            return webui.Child([sys.executable, "-c", code], **kwargs)
        b = webui.Backend(self.root, runner=runner, drive_provider=lambda: [dict(id=d, disc={"blank": True}) for d in ("H:", "I:")])
        self.addCleanup(b.close)
        return b

    def test_validation(self):
        b = self.backend()
        invalid = [dict(action="erase"), dict(action="geo", drive="X:"),
                   dict(action="geo", drive="H:", args={"speed": "1; erase"}),
                   dict(action="geo", drive="H:", args={"reps": True}),
                   dict(action="geo", drive="H:", args={"force": True}),
                   dict(action="random", args={"output": "../outside.iso"}),
                   dict(action="image", args={"geo": "latest", "output": "--help"}),
                   dict(action="image", media="bd", args={"geo": "latest"}),
                   dict(action="random", args={"sectors": float("nan")}),
                   dict(action="disexport", args={"geo": "latest"})]
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(webui.APIError):
                b.start(payload)
        self.assertEqual(b.jobs, {})
        for action, args in [("info", {}), ("geo", {"speed": "4x"}), ("timing", {}),
                             ("random", {"sectors": 100}), ("image", {"geo": "latest"}),
                             ("disexport", {"geo": "latest", "sectors": 1000}), ("cdprobe", {"sectors": 1000})]:
            payload = dict(action=action, drive="H:", media="cd", args=args)
            argv, drive = webui.command(payload, b.root, b.drive_provider())
            self.assertEqual(argv[0], sys.executable)
            self.assertEqual(argv[argv.index("-m"):argv.index("-m") + 3], ["-m", "discprobe", action])
            self.assertEqual(drive, "H:")

    def test_jobs_busy_answers_replay_and_cancel(self):
        b = self.backend()
        first = b.start(dict(action="geo", drive="H:"))["job"]
        with self.assertRaisesRegex(webui.APIError, "drive busy"):
            b.start(dict(action="timing", drive="H:"))
        second = b.start(dict(action="info", drive="I:"))["job"]
        def replay():
            events = b.events({}, reconnect=True)
            return events if len([e for e in events if e["type"] == "ask"]) == 2 else None
        events = eventually(replay)
        self.assertEqual(len([e for e in events if e["type"] == "progress"]), 2)
        b.answer(first, dict(id="q1", yes=True))
        self.assertEqual(json.loads(b.jobs[first].answers.read_text())["yes"], True)
        with self.assertRaises(webui.APIError):
            b.answer(first, dict(id="q1", yes=True))
        self.assertEqual(len([e for e in b.events({}, reconnect=True) if e["type"] == "ask"]), 1)
        b.cancel(first)
        eventually(lambda: b.jobs[first].exit is not None)
        self.assertIsNone(b.jobs[second].exit)
        self.assertTrue(any(e["type"] == "done" for e in b.events({})))

    def test_burn_fails_closed_tokens_expire_and_consume(self):
        b = self.backend()
        with self.assertRaisesRegex(webui.APIError, "burn token"):
            b.start(dict(action="burn", drive="H:"))
        token = b.burn_token()["token"]
        with self.assertRaisesRegex(webui.APIError, "not implemented"):
            b.start(dict(action="burn", drive="H:", burn_token=token))
        with self.assertRaisesRegex(webui.APIError, "burn token"):
            b.start(dict(action="burn", drive="H:", burn_token=token))
        token = b.burn_token()["token"]
        b.tokens[token] = time.monotonic() - 1
        with self.assertRaises(webui.APIError):
            b.start(dict(action="burn", drive="H:", burn_token=token))
        self.assertEqual(b.jobs, {})

    def test_real_fake_child_done(self):
        b = self.backend("print('fake child only')")
        ident = b.start(dict(action="info", drive="H:"))["job"]
        eventually(lambda: b.jobs[ident].exit is not None)
        self.assertEqual(b.jobs[ident].exit, 0)
        self.assertIn("fake child only", (b.jobs[ident].folder / "output.log").read_text())

    def test_cancel_owns_descendants(self):
        marker = self.root / "grandchild.pid"
        code = ("import subprocess, sys, time; from pathlib import Path; "
                "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
                f"Path({str(marker)!r}).write_text(str(p.pid)); time.sleep(60)")
        b = self.backend(code)
        ident = b.start(dict(action="info", drive="H:"))["job"]
        eventually(lambda: marker.exists() and marker.stat().st_size)
        pid = int(marker.read_text())
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel.OpenProcess.restype = wintypes.HANDLE
            kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            handle = kernel.OpenProcess(0x1000, False, pid)
            self.assertTrue(handle)
            self.addCleanup(lambda: kernel.CloseHandle(handle))
            def running():
                code = wintypes.DWORD()
                self.assertTrue(kernel.GetExitCodeProcess(handle, ctypes.byref(code)))
                return code.value == 259
        else:
            def running():
                try:
                    stat = Path(f"/proc/{pid}/stat")
                    if stat.exists() and stat.read_text().split()[2] == "Z":
                        return False
                    os.kill(pid, 0)
                    return True
                except ProcessLookupError:
                    return False
        self.assertTrue(running())
        b.cancel(ident)
        eventually(lambda: not running())

    def test_external_results_emit_state(self):
        b = self.backend()
        cursors = {}
        self.assertEqual(b.events(cursors), [])
        self.result("timing", {"stopped": "interrupted"})
        self.assertEqual(b.events(cursors), [dict(type="state")])
        self.assertEqual(b.events(cursors), [])

    def http_server(self, lan=False):
        b = self.backend()
        server = webui.Server(b, 0, lan=lan)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def cleanup():
            server.shutdown()
            server.server_close()
            thread.join()
        self.addCleanup(cleanup)
        return server

    def request(self, server, method, path, payload=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        hdr = {"Content-Type": "application/json", **(headers or {})}
        c.request(method, path, json.dumps(payload) if payload is not None else None, hdr)
        response = c.getresponse()
        body = response.read()
        c.close()
        return response.status, body

    def test_http_endpoints_and_origin(self):
        server = self.http_server()
        self.assertEqual(self.request(server, "GET", "/")[0], 404)
        self.assertEqual(self.request(server, "GET", "/../guide.py")[0], 404)
        self.assertEqual(self.request(server, "GET", "/%2e%2e/guide.py")[0], 404)
        code, body = self.request(server, "GET", "/api/state")
        self.assertEqual(code, 200)
        self.assertEqual(len(json.loads(body)["drives"]), 2)
        self.assertEqual(self.request(server, "GET", "/api/state", headers={"Origin": "http://evil.example"})[0], 403)
        code, body = self.request(server, "POST", "/api/run", dict(action="geo", drive="H:"))
        self.assertEqual(code, 200)
        ident = json.loads(body)["job"]
        self.assertEqual(self.request(server, "POST", "/api/run", dict(action="info", drive="H:"))[0], 409)
        eventually(lambda: server.backend.events({}, reconnect=True))
        # HTTP SSE initial snapshot carries progress and pending questions.
        c = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        c.request("GET", "/api/events")
        response = c.getresponse()
        self.assertEqual(response.getheader("Content-Type"), "text/event-stream")
        lines = [response.readline() for _ in range(6)]
        self.assertTrue(any(b"event: progress" in line for line in lines))
        self.assertTrue(any(b"event: ask" in line for line in lines))
        c.close()
        self.assertEqual(self.request(server, "POST", f"/api/jobs/{ident}/answer", dict(id="q1", yes=False))[0], 200)
        self.assertEqual(self.request(server, "POST", f"/api/jobs/{ident}/cancel", {})[0], 200)
        self.assertEqual(self.request(server, "GET", "/api/burn-token")[0], 200)
        self.assertEqual(self.request(server, "POST", "/api/jobs/j-0000/cancel", {})[0], 404)

    def test_greetings_are_the_terminal_ones(self):
        from discprobe import greetings
        server = self.http_server()
        status, raw = self.request(server, "GET", "/api/greetings")
        body = json.loads(raw)
        self.assertEqual(status, 200)
        self.assertEqual(len(body["week"]), 7)
        self.assertEqual(tuple(body["week"][0][2]), greetings.WEEK[0][2])
        self.assertEqual(tuple(body["first_time"][0]), greetings.FIRST_TIME[0])

    def test_state_takes_the_disc_type_per_request(self):
        b = webui.Backend(self.root, media="dvd", drive_provider=lambda: [])
        self.assertEqual(b.state()["media"], "dvd")
        self.assertEqual(b.state("cd")["media"], "cd")
        self.assertEqual(b.state("bd")["media"], "bd")
        with self.assertRaises(webui.APIError):
            b.state("hddvd")
        self.assertEqual(b.state()["platform"], sys.platform)      # the terminal page dresses as this machine's shell

    def test_disc_in_the_drive_is_read_on_request_and_kept(self):
        found = dict(tray="ready", drive="HL-DT-ST GH70N",
                     disc=dict(present=True, media="dvd", kind="DVD-R Sequential", mid="RITEKF1", blank=True, sectors=2298496))
        reads = []
        def reader(drive):
            reads.append(drive)
            # while it reads, the drive is busy for jobs
            with self.assertRaisesRegex(webui.APIError, "drive busy"):
                b.start(dict(action="info", drive=drive))
            return found
        b = webui.Backend(self.root, drive_provider=lambda: [dict(id="H:", name="H:", disc=None)], disc_reader=reader)
        self.assertIsNone(b.state()["drives"][0]["disc"])            # nothing is read on page load
        with self.assertRaisesRegex(webui.APIError, "unknown drive"):
            b.read_disc(dict(drive="Z:"))
        got = b.read_disc(dict(drive="H:"))["disc"]
        self.assertEqual((got["mid"], got["media"], got["tray"]), ("RITEKF1", "dvd", "ready"))
        self.assertEqual(reads, ["H:"])
        self.assertEqual(b.state()["drives"][0]["disc"]["mid"], "RITEKF1")    # kept for the page
        # a blank disc seen this way never authorizes a burn by itself
        token = b.burn_token()["token"]
        with self.assertRaisesRegex(webui.APIError, "verified blank"):
            b.start(dict(action="burn", drive="H:", burn_token=token))
        # no disc: an empty tray is reported, not an error
        found.update(tray="open", disc=None)
        got = b.read_disc(dict(drive="H:"))["disc"]
        self.assertEqual((got["present"], got["tray"]), (False, "open"))

    def test_calibrate_is_one_job_and_burns_only_under_the_burn_rules(self):
        geo = self.result("geo", {"fit": {"media": "dvd"}})
        script = f'''import json, os
p = os.environ['DISCPROBE_EVENTS']
with open(p, 'a') as f:
 f.write(json.dumps(dict(type='step', name='geo', index=2, total=3))+'\\n')
 f.write(json.dumps(dict(type='calibrated', ok=True, disc=dict(mid='RITEKF1'), geo=dict(path={str(geo)!r}, verdict='usable')))+'\\n')
'''
        b = self.backend(script)
        for bad in (dict(action="calibrate", drive="H:", media="bd"),
                    dict(action="calibrate", drive="H:", args={"mid": "a\nb"}),
                    dict(action="calibrate", args={})):
            with self.assertRaises(webui.APIError):
                b.start(bad)
        # without an image it only measures: no token asked, nothing written
        ident = b.start(dict(action="calibrate", drive="H:", args={"mid": "RITEKF1", "preset": "presets/p.json"}))["job"]
        self.assertNotIn("--yes-write", self.argv)
        self.assertEqual(self.argv.count("--media"), 1)
        self.assertIn("--out", self.argv)
        eventually(lambda: b.jobs[ident].exit is not None)
        result = b.job_state(ident)["result"]
        self.assertTrue(result["ok"])
        self.assertEqual((result["verdict"], result["geo"]["path"]), ("usable", "results/" + geo.name))
        self.assertTrue(any(e["type"] == "step" for e in b.job_state(ident)["events"]))      # the page follows the steps
        # with an image it starts with a burn: the burn's token and blank check apply
        (self.root / "iso").mkdir()
        (self.root / "iso" / "m.iso").write_bytes(b"\0" * 4096)
        with self.assertRaisesRegex(webui.APIError, "burn token"):
            b.start(dict(action="calibrate", drive="I:", args={"iso": "iso/m.iso"}))
        token = b.burn_token()["token"]
        b.start(dict(action="calibrate", drive="I:", args={"iso": "iso/m.iso"}, burn_token=token))
        self.assertIn("--yes-write", self.argv)
        self.assertEqual(self.argv.count("--media"), 1)

    def test_disc_command_prints_one_json_line(self):
        env = dict(os.environ, PYTHONPATH=str(ROOT))
        out = subprocess.run([sys.executable, "-m", "discprobe", "disc", "--sim", "cav"], cwd=self.root, env=env,
                             capture_output=True, text=True, timeout=60).stdout.strip().splitlines()[-1]
        report = json.loads(out)
        self.assertEqual(report["tray"], "ready")
        self.assertEqual(report["disc"]["media"], "dvd")
        self.assertFalse((self.root / "results").exists())         # nothing written

    def test_design_upload_size_sets_the_cell(self):
        import numpy as np
        b = webui.Backend(self.root, drive_provider=lambda: [])
        dark = np.zeros((12000, 12000), bool)
        dark[0, 0] = dark[11999, 11999] = True
        saved = b.save_design(np.packbits(dark).tobytes())
        back = np.load(self.root / saved["design_npy"])
        self.assertEqual((back.shape, back.dtype), ((12000, 12000), np.dtype(bool)))
        self.assertTrue(np.array_equal(back, dark))
        with self.assertRaises(webui.APIError):
            b.save_design(b"x" * 1000)

    def test_design_upload_feeds_image(self):
        import numpy as np
        from discprobe import imagedisc
        self.assertEqual(webui.DESIGN_BYTES, imagedisc.SIZE * imagedisc.SIZE // 8)
        server = self.http_server()
        dark = np.zeros((imagedisc.SIZE, imagedisc.SIZE), bool)
        dark[100:200, 3000:3100] = True
        dark[5999, 5999] = True
        packed = np.packbits(dark).tobytes()
        octet = {"Content-Type": "application/octet-stream"}
        c = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
        c.request("POST", "/api/design", packed, octet)
        response = c.getresponse()
        body = json.loads(response.read())
        c.close()
        self.assertEqual(response.status, 200, body)
        saved = np.load(server.backend.root / body["design_npy"])
        self.assertEqual(saved.dtype, bool)
        self.assertTrue((saved == dark).all())
        # wrong size or type is refused before anything is written
        c = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
        c.request("POST", "/api/design", packed[:-1], octet)
        self.assertEqual(c.getresponse().status, 413)
        c.close()
        self.assertEqual(self.request(server, "POST", "/api/design", {"x": 1})[0], 415)
        argv, _ = webui.command(dict(action="image", args={"geo": "latest", "design_npy": body["design_npy"],
                                                           "light": "92", "output": "iso/web.iso"}),
                                server.backend.root, [])
        self.assertIn("--design-npy", argv)
        self.assertEqual(argv[argv.index("--light") + 1], "92")
        for bad in ({"light": "9"}, {"dark": "A5 --force"}, {"design_npy": "x.npy", "picture": "p.png"}):
            with self.subTest(bad=bad), self.assertRaises(webui.APIError):
                webui.command(dict(action="image", args={"geo": "latest", **bad}), server.backend.root, [])
        (server.backend.root / "iso").mkdir()
        (server.backend.root / "iso" / "web.iso").write_bytes(bytes(4096))
        code, body = self.request(server, "GET", "/api/iso?path=iso/web.iso")
        self.assertEqual((code, json.loads(body)["sectors"]), (200, 2))
        self.assertEqual(self.request(server, "GET", "/api/iso?path=designs/x.npy")[0], 400)
        self.assertEqual(self.request(server, "GET", "/api/iso?path=../x.iso")[0], 400)

    def test_lan_every_request_requires_token(self):
        server = self.http_server(lan=True)
        self.assertEqual(server.server_address[0], "0.0.0.0")
        for method, path in [("GET", "/"), ("GET", "/api/state"), ("GET", "/api/events"), ("GET", "/api/burn-token"), ("POST", "/api/run")]:
            self.assertEqual(self.request(server, method, path, {})[0], 403)
        self.assertEqual(self.request(server, "GET", "/api/state", headers={"X-Discprobe-Token": server.token})[0], 200)
        self.assertEqual(self.request(server, "GET", "/api/state?token=" + server.token)[0], 200)


def test_stdlib_suite():
    """Adapter for discprobe selftest, which discovers top-level functions only."""
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(BackendTests)
    output = io.StringIO()
    result = unittest.TextTestRunner(stream=output).run(suite)
    assert result.wasSuccessful(), output.getvalue()


# Pytest already collects the class; the adapter is for the built-in runner.
test_stdlib_suite.__test__ = False


if __name__ == "__main__":
    unittest.main()

# Shared fake for HTTP/browser checks. It never invokes command argv or a device API.
def workflow_fake_backend(root, out='results', ask=True):
    import shutil
    from types import SimpleNamespace
    root = Path(root)
    sequence = [0]
    written = [False]
    original = ROOT / 'evidence/geo/gh70n-20261107/geo-H-20261107-210507'
    calls = []

    class FakeChild:
        def __init__(self, argv, *, env, cwd, stdout):
            self.stop = threading.Event()
            self.done = threading.Event()
            self.code = 0
            calls.append(argv)
            threading.Thread(target=self.work, args=(argv, env), daemon=True).start()

        def work(self, argv, env):
            def event(**data):
                with open(env['DISCPROBE_EVENTS'], 'a', encoding='utf-8') as stream:
                    stream.write(json.dumps(data) + '\n')
            def arg(name, default=None):
                flag = '--' + name
                return argv[argv.index(flag)+1] if flag in argv else default
            try:
                action = argv[argv.index("discprobe") + 1]
                event(type='progress', fraction=.15, eta_s=1, stage='Fake runner: no hardware')
                if action == 'timing' and ask:
                    event(type='ask', id='fake-tray', question='Fake tray question. Continue?', default=False, kind='tray')
                    answers = Path(env['DISCPROBE_ANSWERS'])
                    deadline = time.monotonic() + 15
                    while time.monotonic() < deadline and not self.stop.is_set():
                        if answers.exists():
                            rows = [json.loads(line) for line in answers.read_text().splitlines()]
                            reply = next((r for r in rows if r['id']=='fake-tray'), None)
                            if reply:
                                event(type='answer', id='fake-tray', yes=reply['yes'])
                                if not reply['yes']: self.code = 1
                                break
                        time.sleep(.02)
                    else: self.code = 1
                if self.stop.wait(.25) or self.code:
                    self.code = 1
                    event(type='stopped', reason='Fake job cancelled')
                    return
                if action in ('random','disexport'):
                    target = Path(arg('output'))
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(json.dumps({'preset':{'id':'fake-export','displayName':'Fake preset','totalSectors':2295104}}) if action=='disexport' else 'FAKE ISO - NOT FOR BURNING')
                    if action=='random': written[0] = True
                else:
                    sequence[0] += 1
                    path = root/out/f'{action}-H-20261110-12{sequence[0]:04d}'
                    path.mkdir(parents=True)
                    if action == 'info':
                        report={k:{'parsed':v} for k,v in dict(configuration=dict(current_profile=0x11,current_profile_name='DVD-R'),
                            inquiry=dict(vendor='TEST',product='FAKE DRIVE'),
                            capacity=dict(last_lba=2295103), track_1=dict(blank=not written[0],track_start=0,free_blocks=2295104),
                            dvd_prerecorded_0e=dict(manufacturer_id='FAKE NEW MID')).items()}
                        (path/'info.json').write_text(json.dumps(report))
                    elif action == 'timing':
                        (path/'summary.json').write_text(json.dumps(dict(period=dict(rotation=dict(mode='CAV'),zones=[dict(jitter_deg=.5)]))))
                    elif action == 'geo':
                        data=json.loads((original/'summary.json').read_text())
                        data['identity']={'disc':'FAKE NEW MID','drive':'TEST FAKE DRIVE'}
                        data['setup']={'last_lba':2295103}
                        (path/'summary.json').write_text(json.dumps(data))
                        shutil.copy2(original/'targets.csv',path/'targets.csv')
                event(type='progress', fraction=1, eta_s=0, stage='Fake job complete',radius_mm=49.9)
            finally:
                self.done.set()

        def wait(self):
            self.done.wait()
            return self.code

        def cancel(self):
            self.stop.set()

        def close(self):
            self.stop.set()

    b = webui.Backend(root, out=out, runner=FakeChild,
        drive_provider=lambda:[dict(id='H:',name='TEST FAKE DRIVE',disc=None)])
    b.fake_calls = calls
    return b


def test_catalogue_and_finished_job_http():
    with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
        backend = workflow_fake_backend(tmp, ask=False)
        server = webui.Server(backend, 0)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            c=http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
            c.request('GET','/api/state')
            state=json.loads(c.getresponse().read())
            assert state['catalogue']==dict(dvd=[],cd=[],bd=[]) and backend.fake_calls==[]
            c.request('POST','/api/run',json.dumps(dict(action='info',drive='H:')),{'Content-Type':'application/json'})
            ident=json.loads(c.getresponse().read())['job']
            eventually(lambda: backend.get_job(ident).finished.is_set())
            c.request('GET','/api/jobs/'+ident)
            snapshot=json.loads(c.getresponse().read())
            assert snapshot['exit']==0 and snapshot['result']['disc']['blank'] is True
            assert snapshot['result']['disc']['mid']=='FAKE NEW MID'
            assert any(e['type']=='result' for e in snapshot['events'])
            assert snapshot['events'][-2]['type']=='done'
            c.request('GET','/api/catalogue')
            assert json.loads(c.getresponse().read())==dict(dvd=[],cd=[],bd=[])
            c.close()
        finally:
            backend.close();server.shutdown();server.server_close();thread.join()


def test_fake_workflow_results_answers_and_persistence():
    with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
        backend=workflow_fake_backend(tmp)
        try:
            def run(action, **args):
                ident=backend.start(dict(action=action,drive='H:' if action in ('info','timing','geo') else None,args=args))['job']
                if action=='timing':
                    eventually(lambda: [e for e in backend.job_state(ident)['events'] if e['type']=='ask'])
                    backend.answer(ident,dict(id='fake-tray',yes=True))
                eventually(lambda: backend.get_job(ident).finished.is_set())
                result=backend.job_state(ident)
                assert result['exit']==0
                return result['result']
            assert run('info')['disc']['blank']
            assert run('random',output='iso/fake.iso',sectors=10)['path']=='iso/fake.iso'
            assert run('info')['disc']['blank'] is False
            assert run('timing')['verdict']=='good'
            geometry=run('geo')
            assert geometry['verdict']=='good'
            run('disexport',geo=geometry['path'],sectors=2295104,output='presets/fake.json')
            entry=backend.state()['catalogue']['dvd'][0]
            from discprobe import webui_catalog
            webui_catalog.save_entry(backend.root,backend.out,dict(id=entry['id'],name='My test batch',left=17))
            assert backend.state()['catalogue']['dvd'][0]['left']==17
        finally: backend.close()


def test_version_is_a_release_tag_or_empty():
    import re
    from discprobe import webui
    v = webui.version()
    assert v == "" or re.fullmatch(r"v[\d.]+(-dev)?", v), v
