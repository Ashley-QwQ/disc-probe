"""No device enumeration, device opens, or real recorder processes in these tests."""
import io
import json
from pathlib import Path
import subprocess
import os
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from discprobe import burner, scsi, webui

ROOT = Path(__file__).resolve().parents[1]


class BurnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "iso").mkdir()
        self.iso = self.root / "iso" / "测试 image.iso"
        self.iso.write_bytes(bytes(4096))
        self.recorder = Mock()
        self.recorder.inspect.return_value = dict(blank=True, media="dvd", free_sectors=20, speeds_x=[8, 4])
        self.recorder.write.return_value = 4.01

    def burn(self, **kw):
        return burner.burn("H:", self.iso, recorder=self.recorder, **{"no_verify": True, **kw})

    def test_confirmation_precedes_all_hardware(self):
        with patch.object(burner, "adapter") as factory:
            with self.assertRaisesRegex(burner.BurnError, "yes-write"):
                burner.burn("H:", self.iso)
            factory.assert_not_called()
        self.recorder.inspect.assert_not_called()

    def test_media_safety_and_size(self):
        for changes, message in [({"blank": False}, "blank"), ({"media": "cd"}, "Wrong"),
                                 ({"free_sectors": 1}, "fit"), ({"speeds_x": []}, "speeds")]:
            with self.subTest(changes=changes):
                saved = self.recorder.inspect.return_value.copy()
                self.recorder.inspect.return_value.update(changes)
                with self.assertRaisesRegex(burner.BurnError, message):
                    self.burn(yes_write=True)
                self.recorder.write.assert_not_called()
                self.recorder.inspect.return_value = saved
        self.iso.write_bytes(b"bad")
        with self.assertRaisesRegex(burner.BurnError, "2048"):
            self.burn(yes_write=True)

    def test_speed_selection(self):
        self.assertEqual(burner.choose_speed(None, [8, 4, 4]), 8)
        self.assertEqual(burner.choose_speed(None, [4, 16], "cd"), 4)
        self.assertEqual(burner.choose_speed(None, [4, 6, 10, 16]), 6)
        self.assertEqual(burner.choose_speed(None, [12, 16]), 12)
        self.assertEqual(burner.choose_speed(4, [4, 8]), 4)
        self.assertEqual(burner.choose_speed(8, [4, 5410 / 675]), 5410 / 675)
        for speed in (0, -1, float("nan"), float("inf"), 12):
            with self.assertRaises(burner.BurnError):
                burner.choose_speed(speed, [4, 8])

    def test_actual_speed_result_and_progress_outlet(self):
        def write(image, speed, cancel, progress):
            self.assertEqual((image, speed), (self.iso.resolve(), 8))
            progress(fraction=.5, elapsed_s=2, eta_s=2, stage="writing")
            return 4.01
        self.recorder.write.side_effect = write
        with patch.object(burner.ui, "event") as event:
            result = self.burn(yes_write=True)
        self.assertFalse(result["verified"])
        self.assertEqual(result["actual_speed_x"], 4.01)
        self.assertEqual(event.call_args_list[1].args, ("progress",))
        self.assertEqual(event.call_args_list[-1].args, ("burn_result",))

    def test_durable_speed_log_and_events(self):
        events = self.root / "events.jsonl"
        with patch.dict(os.environ, DISCPROBE_EVENTS=str(events)), patch("sys.stdout", new_callable=io.StringIO) as output:
            result = self.burn(yes_write=True, speed=8)
        records = [json.loads(line) for line in Path(result["log_path"]).read_text(encoding="utf-8").splitlines()]
        self.assertEqual(records[0]["requested_speed_x"], 8)
        self.assertEqual(records[1]["actual_speed_x"], 4.01)
        self.assertEqual(records[-1]["verification"]["status"], "skipped")
        self.assertEqual([x["type"] for x in records], ["burn_speed", "burn_speed", "burn_result"])
        emitted = [json.loads(line) for line in events.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(emitted[-1]["selected_speed_x"], 8)
        self.assertIn("Requested write speed: 8x", output.getvalue())
        self.assertIn("4.01x", output.getvalue())

    def test_sample_verification_recorded_reads(self):
        self.iso.write_bytes(bytes(1600 * 2048))
        lbas = burner.sample_lbas(1600)
        self.assertEqual((len(lbas), lbas[0], lbas[-1]), (96, 0, 1584))
        self.assertTrue(all(lba % 16 == 0 for lba in lbas))
        dev = Mock()
        dev.__enter__ = Mock(return_value=dev)
        dev.__exit__ = Mock(return_value=False)
        def read(cdb, **kw):
            scsi.check_allowed(cdb)
            self.assertEqual(cdb[0], 0x28)
            self.assertEqual(kw["data_len"], 16 * 2048)
            lba = int.from_bytes(cdb[2:6], "big")
            if lba == lbas[10]:
                return scsi.ScsiResult(2, b"", scsi.Sense(3, 17, 0), 0, 1)
            if lba == lbas[20]:
                raise OSError("injected unreadable")
            if lba == lbas[30]:
                return scsi.ScsiResult(0, b"", None, 0, 1)
            return scsi.ScsiResult(0, (b"x" if lba == lbas[40] else b"\0") * (16 * 2048), None, 0, 1)
        dev.execute.side_effect = read
        verifier = lambda drive, image, media, cancel: burner.verify_image(drive, image, media, cancel, device_factory=lambda _: dev)
        self.recorder.inspect.return_value["free_sectors"] = 1600
        with patch("sys.stdout", new_callable=io.StringIO) as output, patch.object(burner.ui, "event") as event:
            result = self.burn(yes_write=True, no_verify=False, verifier=verifier)
        summary = result["verification"]
        self.assertEqual((summary["ok"], summary["differing"], summary["unreadable"]), (92, 1, 3))
        self.assertEqual(dev.execute.call_count, 96)
        self.assertEqual([f["lba"] for f in summary["failures"]], [lbas[i] for i in (10, 20, 30, 40)])
        self.assertTrue(all(f["radius_mm"] >= 24 for f in summary["failures"]))
        self.assertEqual(result["result"], "completed")
        self.assertFalse(result["verified"])
        self.assertEqual(event.call_args_list[-1].kwargs["verification"], summary)
        self.assertIn("picture may still look fine", output.getvalue())
        self.recorder.write.assert_called_once()

    def test_verify_open_failure_and_cancel_preserve_write(self):
        def unavailable(*args):
            return burner.verify_image(*args, device_factory=Mock(side_effect=OSError("access denied")))
        result = self.burn(yes_write=True, no_verify=False, verifier=unavailable)
        self.assertEqual(result["result"], "completed")
        self.assertEqual(result["verification"]["status"], "unavailable")
        self.assertEqual(result["verification"]["untested"], 1)
        self.assertFalse(result["verified"])

    def test_no_verify_does_not_open_device(self):
        with patch.object(burner, "verify_image") as verify:
            result = self.burn(yes_write=True)
        verify.assert_not_called()
        self.assertFalse(result["verified"])
        self.assertEqual(result["verification"], {"status": "skipped"})

    def test_short_image_sample(self):
        self.assertEqual(burner.sample_lbas(2), [0])
        self.assertEqual(burner.sample_lbas(33), [0, 16])

    def test_sample_match_and_cancellation(self):
        self.iso.write_bytes(bytes(32 * 2048))
        dev = Mock()
        dev.__enter__ = Mock(return_value=dev)
        dev.__exit__ = Mock(return_value=False)
        cancel = threading.Event()
        dev.execute.return_value = scsi.ScsiResult(0, bytes(16 * 2048), None, 0, 1)
        summary = burner.verify_image("fake", self.iso, "dvd", cancel, device_factory=lambda _: dev)
        self.assertEqual((summary["ok"], summary["unreadable"], summary["untested"]), (2, 0, 0))
        def read(*args, **kw):
            cancel.set()
            return scsi.ScsiResult(0, bytes(16 * 2048), None, 0, 1)
        dev.execute.side_effect = read
        summary = burner.verify_image("fake", self.iso, "dvd", cancel, device_factory=lambda _: dev)
        self.assertEqual((summary["status"], summary["ok"], summary["untested"]), ("cancelled", 1, 1))

    def test_reported_speed_survives_failed_write(self):
        def write(image, speed, cancel, progress):
            progress(stage="speed", actual_speed_x=7.9)
            raise burner.BurnError("injected write failure")
        self.recorder.write.side_effect = write
        with patch.object(burner.ui, "event") as event, self.assertRaises(burner.BurnError):
            self.burn(yes_write=True)
        self.assertEqual(event.call_args_list[-1].kwargs["actual_speed_x"], 7.9)

    def test_cancel_before_write_and_no_retry(self):
        cancel = threading.Event()
        cancel.set()
        with self.assertRaisesRegex(burner.BurnError, "before writing"):
            self.burn(yes_write=True, cancel=cancel)
        self.recorder.write.assert_not_called()
        self.recorder.write.side_effect = burner.BurnError("failed WRITE")
        with self.assertRaisesRegex(burner.BurnError, "failed WRITE"):
            self.burn(yes_write=True)
        self.assertEqual(self.recorder.write.call_count, 1)

    def test_progress_parser(self):
        good = json.dumps(dict(type="progress", fraction=.2, elapsed_s=3, eta_s=12))
        self.assertEqual(burner.parse_progress(good)["fraction"], .2)
        for line in ("noise", "[]", "{}", good.replace("0.2", "1.2"),
                     good.replace("0.2", "NaN"), good.replace('"elapsed_s": 3', '"elapsed_s": -3')):
            self.assertIsNone(burner.parse_progress(line))

    def test_cd_preference_and_unsupported_platforms(self):
        self.assertEqual(burner.cd_sector_type([2, 3]), 3)
        self.assertEqual(burner.cd_sector_type([2]), 2)
        with self.assertRaises(burner.BurnError):
            burner.cd_sector_type([1])
        with self.assertRaisesRegex(burner.BurnError, "not yet"):
            burner.WindowsDVD("H:", "cd")
        with patch.object(burner.sys, "platform", "darwin"), self.assertRaisesRegex(burner.BurnError, "not yet"):
            burner.adapter("fake", "dvd")

    def windows(self, lines, code=0, cancel=None):
        process = Mock(stdout=iter(lines))
        process.wait.return_value = code
        with patch.object(burner, "tool", return_value="fake-powershell"):
            recorder = burner.WindowsDVD("H:", "dvd", popen=Mock(return_value=process))
        return recorder, process

    def test_fake_windows_process_success_and_hresult(self):
        rec, process = self.windows(['{"type":"speed","actual_x":4.01}\n',
                                     '{"type":"progress","fraction":0.5,"elapsed_s":1,"eta_s":1}\n'])
        progress = Mock()
        self.assertEqual(rec.write(self.iso, 4, threading.Event(), progress), 4.01)
        self.assertEqual(progress.call_count, 2)
        self.assertEqual(progress.call_args_list[0].kwargs, dict(stage="speed", actual_speed_x=4.01))
        self.assertIn("-Burn", rec.popen.call_args.args[0])
        rec, process = self.windows(["0xC0AA0301"], 1)
        with self.assertRaisesRegex(burner.BurnError, "raw P-W"):
            rec.write(self.iso, 4, threading.Event(), progress)
        self.assertEqual(rec.popen.call_count, 1)

    def test_fake_windows_cancel_creates_marker(self):
        cancel = threading.Event()
        def spawn(argv, **kw):
            marker = Path(argv[argv.index("-CancelFile") + 1])
            def lines():
                cancel.set()
                end = time.monotonic() + 3
                while not marker.exists() and time.monotonic() < end:
                    time.sleep(.01)
                self.assertTrue(marker.exists())
                yield "cancelled"
            return Mock(stdout=lines(), wait=Mock(return_value=1))
        with patch.object(burner, "tool", return_value="fake"):
            rec = burner.WindowsDVD("H:", "dvd", popen=spawn)
        with self.assertRaisesRegex(burner.BurnError, "unusable"):
            rec.write(self.iso, 4, cancel, Mock())

    def test_linux_inspection_and_argv(self):
        output = "Mounted Media: 1Bh, DVD+R\nDisc status: blank\nFree Blocks: 100\nWrite Speed #0: 4.0x1385=5540KB/s"
        run = Mock(return_value=Mock(returncode=0, stdout=output, stderr=""))
        process = Mock(stdout=iter(["50.0% done @ 4.1x\n"]), wait=Mock(return_value=0))
        with patch.object(burner, "tool", side_effect=lambda name: name):
            rec = burner.LinuxBurner("/dev/fake", "dvd", run=run, popen=Mock(return_value=process))
        self.assertEqual(rec.inspect(), dict(media="dvd", blank=True, free_sectors=100, speeds_x=[4]))
        self.assertEqual(rec.write(self.iso, 4, threading.Event(), Mock()), 4.1)
        self.assertEqual(rec.popen.call_args.args[0][-1], "/dev/fake=" + str(self.iso))
        self.assertIn("-dvd-compat", rec.popen.call_args.args[0])
        with patch.object(burner.shutil, "which", return_value=None), self.assertRaisesRegex(burner.BurnError, "missing"):
            burner.LinuxBurner("/dev/fake", "dvd")

    def test_cli_keeps_write_units_separate(self):
        from discprobe import __main__
        with patch.object(burner, "burn") as write:
            __main__._main(["burn", "--drive", "H:", "--iso", str(self.iso), "--speed", "4", "--yes-write", "--no-verify"])
        self.assertEqual(write.call_args.kwargs["speed"], 4)
        self.assertTrue(write.call_args.kwargs["yes_write"])
        self.assertTrue(write.call_args.kwargs["no_verify"])

    def test_linux_cd_layout_and_cancel(self):
        from discprobe import cd
        answers = [Mock(returncode=0, stdout="ATIP info from disk:\nATIP start of lead out: 359849", stderr=""),
                   Mock(returncode=0, stdout="CD-R empty: yes", stderr=""),
                   Mock(returncode=0, stdout="Write speed # 0: 705 kB/s (CD 4x, DVD 0x)", stderr="")]
        cancel = threading.Event()
        process = Mock(wait=Mock(return_value=1))
        def lines():
            cancel.set()
            end = time.monotonic() + 3
            while not process.send_signal.called and time.monotonic() < end:
                time.sleep(.01)
            self.assertTrue(process.send_signal.called)
            yield "Wrote 1 of 2 MB"
        process.stdout = lines()
        with patch.object(burner, "tool", side_effect=lambda n: n):
            rec = burner.LinuxBurner("/dev/fake", "cd", run=Mock(side_effect=answers), popen=Mock(return_value=process))
        self.assertEqual(rec.inspect(), dict(media="cd", blank=True, free_sectors=359549, speeds_x=[4]))
        with self.assertRaisesRegex(burner.BurnError, "unusable"):
            rec.write(self.iso, 4, cancel, Mock())
        toc = Path(cd.toc_path(str(self.iso)))
        self.assertIn('DATAFILE "' + str(self.iso.resolve()) + '"', toc.read_text(encoding="utf-8"))
        self.assertIn("TRACK " + cd.CDRDAO_MODES[cd.sector_layout()][1], toc.read_text())
        process.send_signal.assert_called_once_with(burner.signal.SIGINT)

    def test_speeds_http_handler_uses_readonly_inspect_on_demand(self):
        backend = webui.Backend(self.root, drive_provider=lambda: [dict(id="/dev/fake", disc=None)])
        handler = webui.Handler.__new__(webui.Handler)
        handler.server = Mock(backend=backend)
        handler._allowed = Mock()
        handler._json = Mock()
        fake = Mock()
        fake.inspect.return_value = self.recorder.inspect.return_value
        with patch.object(burner, "adapter", return_value=fake) as factory:
            factory.assert_not_called()
            handler.path = "/api/burn-speeds?drive=%2Fdev%2Ffake&media=dvd"
            handler.do_GET()
            factory.assert_called_once_with("/dev/fake", "dvd")
            fake.inspect.assert_called_once()
            fake.write.assert_not_called()
            self.assertEqual(handler._json.call_args.args[0], 200)
            handler.path = "/api/burn-speeds?drive=unknown"
            handler.do_GET()
            self.assertEqual(handler._json.call_args.args[0], 404)

    def test_fresh_blank_inspection_opens_the_gate_briefly(self):
        """A burn needs a blank disc found by a read-only inspection made just now, on that drive and media."""
        drives = lambda: [dict(id="H:", disc=None)]
        started = []
        backend = webui.Backend(self.root, drive_provider=drives,
                                runner=lambda argv, **kw: started.append(argv) or Mock(wait=Mock(return_value=0), close=Mock()))
        (self.root / "iso").mkdir(exist_ok=True)
        (self.root / "iso" / "p.iso").write_bytes(bytes(4096))
        handler = webui.Handler.__new__(webui.Handler)
        handler.server = Mock(backend=backend)
        handler._allowed = Mock()
        handler._json = Mock()
        run = lambda media="dvd": backend.start(dict(action="burn", drive="H:", media=media, args={"iso": "iso/p.iso"},
                                                      burn_token=backend.burn_token()["token"]))
        with self.assertRaisesRegex(webui.APIError, "blank"):
            run()                                                  # nothing inspected yet
        fake = Mock()
        fake.inspect.return_value = dict(media="dvd", blank=False, free_sectors=0, speeds_x=[4])
        with patch.object(burner, "adapter", return_value=fake):
            handler.path = "/api/burn-speeds?drive=H%3A&media=dvd"
            handler.do_GET()
        with self.assertRaisesRegex(webui.APIError, "blank"):
            run()                                                  # inspected, but not blank
        fake.inspect.return_value = dict(media="dvd", blank=True, free_sectors=2295104, speeds_x=[4, 8])
        with patch.object(burner, "adapter", return_value=fake):
            handler.do_GET()
        with self.assertRaisesRegex(webui.APIError, "blank"):
            run("cd")                                              # blank DVD does not authorize a CD burn
        backend.verified_blank["H:"] = (time.monotonic() - 1, "dvd")
        with self.assertRaisesRegex(webui.APIError, "blank"):
            run()                                                  # expired
        with patch.object(burner, "adapter", return_value=fake):
            handler.do_GET()
        run()
        self.assertIn("--yes-write", started[-1])

    def test_web_no_verify_flag(self):
        for value in (True, False):
            argv, _ = webui.command(dict(action="burn", drive="H:", args=dict(iso="iso/" + self.iso.name, no_verify=value)), self.root, [dict(id="H:")])
            self.assertEqual("--no-verify" in argv, value)
        with self.assertRaises(webui.APIError):
            webui.command(dict(action="burn", drive="H:", args=dict(iso="iso/" + self.iso.name, no_verify="true")), self.root, [dict(id="H:")])

    def test_web_child_cooperative_cancel(self):
        class FakeChild:
            def __init__(self, *args, **kw):
                self.process = Mock()
                self.process.poll.return_value = None
                self.closed = False
            def close(self):
                self.closed = True
        env = dict(DISCPROBE_EVENTS=str(self.root / "events.jsonl"))
        with patch.object(webui, "Child", FakeChild):
            child = burner.web_child(["fake"], env=env)
        child.cancel()
        self.assertTrue(Path(env["DISCPROBE_BURN_CANCEL"]).exists())
        child.process.kill.assert_not_called()
        child.process.poll.return_value = 1
        child.close()
        self.assertTrue(child.closed)

    def test_web_token_blank_whitelist_and_job(self):
        drives = [dict(id="H:", disc=dict(blank=True))]
        process = Mock()
        process.wait.side_effect = lambda: process.stopped.wait(3) or 0
        process.stopped = threading.Event()
        process.cancel.side_effect = process.stopped.set
        runner = Mock(return_value=process)
        backend = webui.Backend(self.root, runner=runner, drive_provider=lambda: drives)
        self.addCleanup(backend.close)
        payload = dict(action="burn", drive="H:", args=dict(iso="iso/" + self.iso.name, speed=4))
        with self.assertRaisesRegex(webui.APIError, "token"):
            backend.start(payload)
        token = backend.burn_token()["token"]
        drives[0]["disc"]["blank"] = False
        with self.assertRaisesRegex(webui.APIError, "blank"):
            backend.start({**payload, "burn_token": token})
        drives[0]["disc"]["blank"] = True
        with self.assertRaisesRegex(webui.APIError, "token"):
            backend.start({**payload, "burn_token": token})
        token = backend.burn_token()["token"]
        backend.tokens[token] = 0
        with self.assertRaisesRegex(webui.APIError, "token"):
            backend.start({**payload, "burn_token": token})
        for bad in ({"iso": "../x.iso"}, {"iso": "iso/x.iso", "yes_write": True}, {"iso": "iso/x.iso", "speed": True}):
            with self.assertRaises(webui.APIError):
                webui.command({**payload, "args": bad}, self.root, drives)
        ident = backend.start({**payload, "burn_token": backend.burn_token()["token"]})["job"]
        argv = runner.call_args.args[0]
        self.assertIn("--yes-write", argv)
        self.assertIn(str(self.iso), argv)
        job = backend.jobs[ident]
        job.events.write_text('{"type":"progress","fraction":0.4}\n')
        self.assertTrue(any(e["type"] == "progress" for e in backend.events({})))
        backend.cancel(ident)
        self.assertTrue(job.finished.wait(3))
        self.assertTrue(any(e["type"] == "done" for e in backend.events({})))
        with self.assertRaisesRegex(webui.APIError, "token"):
            backend.start({**payload, "burn_token": next(iter(backend.tokens), "used")})

    def test_write_allowlist_unchanged(self):
        for opcode in (0x04, 0x2A, 0xAA, 0x8A, 0x5B):
            with self.assertRaises(PermissionError):
                scsi.check_allowed(bytes([opcode]) + bytes(15))

    @unittest.skipUnless(os.name == "nt", "Windows compiler-only fake COM test")
    def test_compiled_imapi_with_fake_objects(self):
        # Extract ONLY Add-Type's source; never execute the burn script or create COM objects.
        script = (ROOT / "tools" / "burn_imapi.ps1").read_text(encoding="utf-8")
        source = script.split('-TypeDefinition @"', 1)[1].split('\n"@', 1)[0]
        fake = r'''
public class FakeMaster { public int Count { get { return 1; } } public string this[int i] { get { return "fake"; } } }
public class FakeRecorder {
    public string[] VolumePathNames { get { return new [] { "H:\\" }; } }
    public int[] CurrentProfiles { get { return new [] { 0x1B }; } }
    public void InitializeDiscRecorder(string id) { }
}
public class FakeProgress {
    public int SectorCount = 2, LastWrittenLba = 0, StartLba = 0;
    public int ElapsedTime = 1, RemainingTime = 1, CurrentAction = 4;
}
public class FakeFormat : IBurnVerification {
    public object Recorder { get; set; }
    public string ClientName { get; set; }
    public int CurrentPhysicalMediaType = 6, CurrentMediaStatus = 2;
    public bool MediaPhysicallyBlank = true;
    public long FreeSectorsOnMedia = 100, NextWritableAddress = 0;
    public int[] SupportedWriteSpeeds = new [] { 5400, 2700 };
    public bool BufferUnderrunFreeDisabled = true, ForceMediaToBeClosed = false, ForceOverwrite = true;
    public int CurrentWriteSpeed = 0, Level = -1, Writes = 0, Cancels = 0;
    public bool Fail, ExpectKeepOpen;
    public string CancelMarker;
    public MachineBurn.UpdateHandler Handler;
    public bool IsCurrentMediaSupported(object recorder) { return true; }
    public void SetBurnVerificationLevel(int level) { Level = level; }
    public int GetBurnVerificationLevel() { return Level; }
    public void SetWriteSpeed(int speed, bool cav) { CurrentWriteSpeed = speed; }
    public void CancelWrite() { Cancels++; }
    public void Write(object stream) {
        Writes++;
        if (BufferUnderrunFreeDisabled || ForceMediaToBeClosed == ExpectKeepOpen || ForceOverwrite || Level != 0)
            throw new Exception("Unsafe settings");
        if (CancelMarker != null) System.IO.File.WriteAllText(CancelMarker, "");
        Handler(this, new FakeProgress());
        if (Cancels > 0 || Fail) throw new COMException("fake write failure", unchecked((int)0xC0AA0301));
    }
}
public static class FakeHarness {
    public static void Run(string image) {
        for (int mode = 0; mode < 15; mode++) {
            FakeFormat format = new FakeFormat();
            if (mode == 1) format.MediaPhysicallyBlank = false;
            if (mode == 2) format.CurrentPhysicalMediaType = 2;
            if (mode == 3) format.FreeSectorsOnMedia = 1;
            if (mode == 5) format.Fail = true;
            if (mode == 6) format.CancelMarker = image + ".cancel";
            if (mode == 7) format.CurrentMediaStatus = 0;
            if (mode >= 9) { format.MediaPhysicallyBlank = false; format.CurrentMediaStatus = 4; format.NextWritableAddress = 1640000; }
            if (mode == 8) format.ExpectKeepOpen = true;
            if (mode == 10) format.NextWritableAddress++;
            if (mode == 11) { format.MediaPhysicallyBlank = true; format.CurrentMediaStatus = 2; }
            if (mode == 12) format.CurrentMediaStatus = 0x4000;
            bool failed = false;
            try {
                MachineBurn.RunWithFactory("H:", image, mode == 4 ? 12 : 4, true, format.CancelMarker,
                    name => name.EndsWith("Master2") ? (object)new FakeMaster() :
                            name.EndsWith("Recorder2") ? (object)new FakeRecorder() : format,
                    (obj, handler) => format.Handler = handler,
                    (obj, handler) => format.Handler = null, mode == 8 || mode == 14, mode >= 9, mode >= 9 && mode != 13 ? 1640000 : -1);
            } catch { failed = true; }
            if (mode == 0 || mode == 8 || mode == 9) {
                if (failed || format.Writes != 1 || format.CurrentWriteSpeed != 2700) throw new Exception("success path failed");
            } else if (mode == 5 || mode == 6) {
                if (!failed || format.Writes != 1) throw new Exception("failed write retried or hidden");
                if (mode == 6 && format.Cancels != 1) throw new Exception("CancelWrite missing");
            } else if (!failed || format.Writes != 0) throw new Exception("unsafe preflight");
        }
        Console.WriteLine("FAKE_IMAPI_PASSED");
    }
}
'''
        file = self.root / "fake-imapi.ps1"
        file.write_text("$ErrorActionPreference='Stop'\nAdd-Type -ReferencedAssemblies System.dll,System.Core.dll,Microsoft.CSharp.dll -TypeDefinition @'\n" +
                        source + fake + "\n'@\n[FakeHarness]::Run($args[0])\n", encoding="utf-8-sig")
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-File", str(file), str(self.iso)],
                                text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("FAKE_IMAPI_PASSED", result.stdout)


def test_stdlib_suite():
    result = unittest.TextTestRunner(stream=io.StringIO()).run(unittest.defaultTestLoader.loadTestsFromTestCase(BurnerTests))
    assert result.wasSuccessful(), result.errors + result.failures


test_stdlib_suite.__test__ = False
