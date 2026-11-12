"""Sparse media and timing tests. No device backend is constructed."""
import copy
import io
import json
import tempfile
import unittest
import subprocess
import struct
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from discprobe import discid, iso9660, burner, mmc
from discprobe.sim import SimDrive
from discprobe.scsi import Sense

N = 2295104


def media(record=None, total=N):
    return iso9660.sectors(total, 'TEST', record or discid.create(code='KOI-A 3-05'))


class DamagedDrive(SimDrive):
    def __init__(self, sectors, total=N, failed=(), **kwargs):
        super().__init__(capacity=total, identity_sectors=sectors, jitter_us=0,
                         outlier_rate=0, **kwargs)
        self.failed = set(failed)
        self.reads = []

    def execute(self, cdb, data_len=0, direction=1, timeout_s=30):
        result = super().execute(cdb, data_len, direction, timeout_s)
        if cdb[0] in (0x28, 0xA8):
            lba = int.from_bytes(cdb[2:6], 'big')
            count = int.from_bytes(cdb[7:9] if cdb[0] == 0x28 else cdb[6:10], 'big')
            self.reads.append((lba,count))
            if self.failed.intersection(range(lba,lba+count)):
                result.status, result.data, result.sense = 2, b'', Sense(3,0x11,0)
        return result


def scenarios():
    record = discid.create(code='KOI-A 3-05')
    h = media(record)
    starts = discid.positions(N)
    cases = {}
    def inspect(name, data=h, failed=()):
        d = DamagedDrive(data, failed=failed)
        cases[name] = discid.read_device(d, detailed=True)
        assert all((x,4) in d.reads for x in starts)
        assert not any(x in (16,20) for x,_ in d.reads)
    inspect('all_ok')
    inspect('copy0_unreadable', failed=range(16,32))
    inspect('root_unreadable', failed=[20])
    inspect('two_unreadable', failed=[starts[0],starts[2]])
    bad = dict(h)
    slot = bytearray(b''.join(h[x] for x in range(starts[1], starts[1]+4)))
    pos = slot.index(b'KOI-A')
    slot[pos] ^= 1
    for i in range(4):
        bad[starts[1]+i] = bytes(slot[i*2048:(i+1)*2048])
    inspect('bad_hash', bad)
    other = copy.deepcopy(record['body']); other['code'] = 'KOI-A 3-06'
    bad = dict(h); slot = discid.encode_copy(discid.seal(other), 2)
    for i in range(4):
        bad[starts[2]+i] = slot[i*2048:(i+1)*2048]
    inspect('disagree', bad)
    inspect('old_absent', iso9660.sectors(N, 'OLD'))
    old = iso9660.sectors(N, 'OLD'); slot = discid.encode(record)
    for i in range(4):
        old[21+i] = slot[i*2048:(i+1)*2048]
    inspect('legacy_single', old)
    inspect('all_unreadable', failed=starts)
    return cases


class CopyTests(unittest.TestCase):
    def test_windows_multiple_overlay(self):
        root = Path(__file__).resolve().parents[1]
        script = (root/'tools/burn_imapi.ps1').read_text(encoding='utf-8')
        source = script.split('-TypeDefinition @"',1)[1].split('\n"@',1)[0]
        with tempfile.TemporaryDirectory(dir='C:/disc-probe-scratch/disc-id') as tmp:
            folder = Path(tmp); image=folder/'x.iso'; bundle=folder/'patch.bin'
            starts = discid.positions(32768)
            with image.open('wb') as f:
                f.truncate(32768*2048)
            bundle.write_bytes(b'DPIDPAT2'+struct.pack('<I',4)+b''.join(
                struct.pack('<qI', x*2048,8192)+bytes([101+i])*8192 for i,x in enumerate(starts)))
            harness = '''
public static class MultiTest {
 public static void Run(string image, string patch) {
  long[] offsets = new long[] { OFFSETS };
  using (IdentityStream s = new IdentityStream(image, patch, 43008)) {
   IntPtr got = Marshal.AllocHGlobal(8);
   try {
    for (int i=0;i<4;i++) {
     s.Seek(offsets[i]-1,0,got);
     byte[] b = new byte[8194]; s.Read(b,b.Length,got);
     if(b[0]!=0 || b[1]!=101+i || b[8192]!=101+i || b[8193]!=0)
      throw new Exception("Lost scattered overlay");
     s.Seek(offsets[i],0,got); IStream clone; s.Clone(out clone);
     clone.Read(b,1,got); if(b[0]!=101+i) throw new Exception("Lost clone overlay");
     ((IDisposable)clone).Dispose();
     s.Seek(offsets[i]-1,0,got);
     using(var sink = new IdentitySink()) {
      s.CopyTo(sink,8194,got,IntPtr.Zero);
      b=sink.data.ToArray();
      if(b.Length!=8194 || b[1]!=101+i || b[8193]!=0) throw new Exception("Lost CopyTo overlay");
     }
    }
   } finally { Marshal.FreeHGlobal(got); }
  }
 }
}
public class IdentitySink : IStream, IDisposable {
 public System.IO.MemoryStream data=new System.IO.MemoryStream();
 public void Write(byte[] b,int n,IntPtr p) { data.Write(b,0,n); Marshal.WriteInt32(p,n); }
 public void Read(byte[] b,int n,IntPtr p) { throw new NotSupportedException(); }
 public void Seek(long n,int o,IntPtr p) { throw new NotSupportedException(); }
 public void SetSize(long n) { throw new NotSupportedException(); }
 public void CopyTo(IStream s,long n,IntPtr r,IntPtr w) { throw new NotSupportedException(); }
 public void Commit(int f) {} public void Revert() {} public void LockRegion(long a,long b,int c) {}
 public void UnlockRegion(long a,long b,int c) {} public void Stat(out STATSTG s,int f) {s=new STATSTG();}
 public void Clone(out IStream s) {s=null;} public void Dispose() {data.Dispose();}
}
'''.replace('OFFSETS', ','.join(str(x*2048) for x in starts))
            ps=folder/'compile.ps1'
            ps.write_text("$ErrorActionPreference='Stop'\nAdd-Type -ReferencedAssemblies System.dll,System.Core.dll,Microsoft.CSharp.dll -TypeDefinition @'\n"+
                          source+harness+"\n'@\n[MultiTest]::Run($args[0],$args[1])\n", encoding='utf-8-sig')
            result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-File',str(ps),str(image),str(bundle)],
                                  capture_output=True,encoding='utf-8',errors='replace',timeout=30)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            with image.open('rb') as f:
                self.assertTrue(all(f.read(8192)==bytes(8192) for _ in range(32768//4)))

    def test_recovery(self):
        cases = scenarios()
        for name in ('all_ok','copy0_unreadable','root_unreadable','two_unreadable','bad_hash','legacy_single'):
            self.assertEqual(cases[name]['reason'], 'ok', name)
        self.assertEqual(cases['bad_hash']['copies'][1]['status'], 'hash_mismatch')
        self.assertEqual(cases['disagree']['reason'], 'valid_copies_disagree')
        self.assertIsNone(cases['disagree']['record'])
        self.assertEqual(cases['old_absent']['reason'], 'absent')
        self.assertEqual(cases['all_unreadable']['reason'], 'no_valid_copy')

    def test_size_and_units(self):
        for total in (32768, 32801, 100003, N, 359849, 12219392):
            starts = discid.positions(total)
            self.assertEqual(len(starts), 4)
            self.assertTrue(all(x+4 <= total for x in starts))
            self.assertGreater(min(b-a for a,b in zip(starts,starts[1:])), 9000)
            for unit in (16,32):
                self.assertEqual(len({x//unit for x in starts}), 4)
                self.assertTrue(all(x//unit == (x+3)//unit for x in starts))
        for total in (24,128,8192,32767):
            with self.assertRaisesRegex(ValueError, '32768'):
                discid.positions(total)

    def test_whois_exit_and_reasons(self):
        from discprobe import __main__
        for name,result in scenarios().items():
            with patch.object(__main__.discid if hasattr(__main__, 'discid') else discid,
                              'read_device', return_value=result), \
                 patch.object(__main__, '_open', return_value=Mock()), redirect_stdout(io.StringIO()) as output:
                args = Mock(image=None, drive='SIM', sim=None, register=None)
                if result['reason'] == 'ok':
                    __main__.cmd_whois(args)
                else:
                    with self.assertRaises(SystemExit) as exc:
                        __main__.cmd_whois(args)
                    self.assertEqual(exc.exception.code, 1)
                self.assertEqual(json.loads(output.getvalue())['reason'], result['reason'], name)

    def test_patch_refused_before_drive_inspection(self):
        with tempfile.TemporaryDirectory(dir='C:/disc-probe-scratch/disc-id') as tmp:
            path = Path(tmp)/'test.iso'
            h = media(total=32768)
            with path.open('wb') as f:
                f.truncate(32768*2048)
                for lba,data in h.items():
                    f.seek(lba*2048); f.write(data)
            for start in discid.positions(32768):
                with path.open('r+b') as f:
                    f.seek(start*2048); original=f.read(2048)
                    f.seek(start*2048); f.write(bytes(2048))
                recorder=Mock()
                with self.assertRaises(burner.BurnError):
                    burner.burn('SIM', path, disc_id=True, yes_write=True, recorder=recorder)
                recorder.inspect.assert_not_called()
                recorder.write.assert_not_called()
                with path.open('r+b') as f:
                    f.seek(start*2048); f.write(original)

    def test_measurement_avoidance(self):
        from discprobe.geo import Ladder
        from discprobe.timing import TimingProbe, NoReadableDisc
        h = media(); starts = discid.positions(N)
        for ranges,ref in ((None,None), ([(0,N)],starts[1]),
                           ([(starts[2]-5000,starts[2]+5000)], starts[2])):
            d = DamagedDrive(h)
            ladder = Ladder(d, ranges=ranges, ref_lba=ref, max_targets=4, reps=16,
                            state_check=False, log=lambda *_:None)
            ladder.run()
            safe = ladder.tp.safe_ranges([(0,N)], ladder.completion_sectors)
            for event in ladder.tp.events:
                if event.label != 'disc-identity':
                    self.assertTrue(any(a <= event.lba and event.lba+1 <= b for a,b in safe), event)
            self.assertTrue(any(a <= ladder.ref < b for a,b in safe))
        d = DamagedDrive(h)
        tp = TimingProbe(d, targets=[x/(N-1) for x in starts], ref_fraction=starts[1]/(N-1),
                         reps=12, period_reads=16, log=lambda *_:None)
        tp.run()
        safe = tp.safe_ranges([(0,N)])
        for e in tp.events:
            if e.label != 'disc-identity':
                self.assertTrue(any(a <= e.lba < b for a,b in safe), e)
        # Merge contract: an arbitrary label reservation joins the identity list.
        tp.summary['random_label'] = dict(exclude_lba=[1970960,2247568], avoid_lba=[[32,33]])
        self.assertTrue(all(not (a < 2247568+3000 and b > 1970960-3000) for a,b in tp.safe_ranges([(0,N)])))
        tp.reserved_lba = [(0,N)]
        with self.assertRaises(NoReadableDisc):
            tp._align(.5)


def test_stdlib_suite():
    result = unittest.TextTestRunner(stream=io.StringIO()).run(unittest.defaultTestLoader.loadTestsFromTestCase(CopyTests))
    assert result.wasSuccessful(), result.errors + result.failures


test_stdlib_suite.__test__ = False


if __name__ == '__main__':
    unittest.main()
