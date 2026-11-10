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
            self.assertEqual(argv[:4], [sys.executable, "-m", "discprobe", action])
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
