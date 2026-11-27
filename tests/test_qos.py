import subprocess
import sys
import unittest

from discprobe import qos


@unittest.skipUnless(sys.platform == "win32", "EcoQoS is a Windows setting")
class KeepFullSpeedTest(unittest.TestCase):
    def test_opt_out_reads_back(self):
        # Run in a fresh process so this test process is left as it was.
        code = ("from discprobe import qos; ok = qos.keep_full_speed(); s = qos.throttling_state(); "
                "print(ok, s[0] & qos.EXECUTION_SPEED, s[1] & qos.EXECUTION_SPEED)")
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.split()
        self.assertEqual(out, ["True", "1", "0"])     # speed throttling controlled, and off

    def test_every_process_opts_out(self):
        # The command line, the web server and its jobs all enter through main(); pool workers through _job_init.
        from discprobe import imagedisc
        import inspect
        from discprobe import __main__ as cli
        self.assertIn("qos.keep_full_speed()", inspect.getsource(cli.main))
        self.assertIn("keep_full_speed()", inspect.getsource(imagedisc._job_init))


class OtherSystemsTest(unittest.TestCase):
    def test_noop_elsewhere(self):
        if sys.platform != "win32":
            self.assertFalse(qos.keep_full_speed())
            self.assertIsNone(qos.throttling_state())


if __name__ == "__main__":
    unittest.main()
