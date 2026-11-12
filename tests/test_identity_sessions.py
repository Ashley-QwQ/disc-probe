"""Cross-feature checks use synthetic sectors and injected recorders only."""
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from discprobe import burner, discid, labelsession, randomdisc, randomlabel
from discprobe.sim import SimDrive
from discprobe.timing import TimingProbe

class IdentitySessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir='C:/disc-probe-scratch/release-alpha')
        self.addCleanup(self.temp.cleanup)
        self.image = Path(self.temp.name) / 'first.iso'
        with patch.object(randomlabel, 'STOP_SECTORS', 32768):
            randomdisc.write_iso(str(self.image), label='ALPHA', disc_id_code='ALP-A 1-01', log=lambda *_: None)
        self.spec = json.loads(self.image.with_suffix('.image.json').read_text())
        self.slots = {}
        with self.image.open('rb') as stream:
            for start in discid.positions(32768):
                stream.seek(start*2048)
                for i in range(4):
                    self.slots[start+i] = stream.read(2048)

    def drive(self, closed=False, damaged=False):
        slots = dict(self.slots)
        if damaged:
            slots[21] = b'!' + slots[21][1:]
        layouts = {32:randomlabel.marker(self.spec)}
        final = labelsession.measured_label('ALPHA',2295104,'evidence/geo/random_disc_summary.json').spec
        if closed:
            final.update(first_lba=1630976, avoid_lba=[[32768,1630976],[32,33]])
            layouts[randomlabel.MARKER_LBA] = randomlabel.marker(final)
        dev = SimDrive(identity_sectors=slots,layout_sectors=layouts,jitter_us=0,outlier_rate=0)
        if closed:
            original=dev.execute
            def execute(cdb,*args,**kwargs):
                result=original(cdb,*args,**kwargs)
                if cdb[0] == 0x51:
                    data=bytearray(34);data[2]=2;result.status=0;result.data=bytes(data)
                return result
            dev.execute=execute
        return dev

    def test_first_session_identity_and_readonly_burn_patch(self):
        original=self.image.read_bytes()
        result=discid.read_image(self.image,detailed=True)
        self.assertEqual([c['status'] for c in result['copies']],['ok']*4)
        self.assertEqual(self.spec['disc_identity_layout']['total_sectors'],32768)
        rec=Mock();rec.inspect.return_value=dict(media='dvd',blank=True,closed=False,free_sectors=2295104,speeds_x=[8])
        rec.write.return_value=8
        result=burner.burn('SIM',self.image,yes_write=True,disc_id=True,keep_open=True,recorder=rec,no_verify=True)
        stream=rec.write.call_args.args[0]
        self.assertIsInstance(stream,discid.PatchedImage)
        self.assertTrue(rec.write.call_args.kwargs['keep_open'])
        self.assertEqual(len(stream.verification_lbas()),4)
        with stream.open('rb') as patched:
            records=[]
            for i,lba in enumerate(discid.positions(32768)):
                patched.seek(lba*2048);records.append(discid.decode_copy(patched.read(8192),i))
        self.assertTrue(all(r==result['identity'] for r in records))
        self.assertEqual(self.image.read_bytes(),original)

    def test_whois_after_append_recovers_without_copy_zero(self):
        for closed in (False,True):
            result=discid.read_device(self.drive(closed,True),detailed=True)
            self.assertEqual(result['reason'],'ok')
            self.assertEqual([c['lba'] for c in result['copies']],discid.positions(32768))
            self.assertEqual(sum(c['status']=='ok' for c in result['copies']),3)

    def test_shared_reservations_before_and_after_append(self):
        for closed in (False,True):
            tp=TimingProbe(self.drive(closed),log=lambda *_:None,period_reads=20,reps=8)
            tp.setup()
            self.assertEqual([c['lba'] for c in tp.summary['disc_identity']['copies']],discid.positions(32768))
            self.assertEqual(tp.last_lba,2295103 if closed else 32767)
            safe=tp.safe_ranges([(0,tp.last_lba+1)],16)
            spans=[*self.spec['disc_identity_layout']['physical_lba'],[32,33]]
            if closed:
                spans += tp.summary['random_label']['avoid_lba']+[tp.summary['random_label']['exclude_lba']]
            self.assertTrue(all(not(a<hi+3000 and b>lo-3000) for a,b in safe for lo,hi in spans))
            for event in tp.events:
                if event.label not in ('layout','disc-identity'):
                    self.assertTrue(any(a<=event.lba and event.lba+1<=b for a,b in safe))

    def test_append_identity_is_refused_before_device_inspection(self):
        # An actual appended image has no first-session filesystem or identity slots.
        session=Path(self.temp.name)/'label.iso';session.write_bytes(bytes(32768))
        rec=Mock()
        with self.assertRaisesRegex(burner.BurnError,'first session'):
            burner.burn('SIM',session,yes_write=True,append=True,expect_start=1630976,disc_id=True,recorder=rec)
        rec.inspect.assert_not_called();rec.write.assert_not_called()

    def test_windows_passes_both_patch_and_keep_open(self):
        stream=discid.patch_burn(self.image,{},speed=None,selected=8,media='dvd')
        rec=object.__new__(burner.WindowsDVD);rec.base=['powershell.exe']
        process=Mock();process.stdout=io.StringIO('');process.wait.return_value=0
        rec.popen=Mock(return_value=process)
        rec.write(stream,8,threading.Event(),lambda **_:None,keep_open=True)
        argv=rec.popen.call_args.args[0]
        self.assertIn('-KeepOpen',argv);self.assertIn('-IdentityPatch',argv)
        self.assertEqual(argv[argv.index('-Iso')+1],str(self.image))

def test_stdlib_suite():
    result=unittest.TextTestRunner(stream=io.StringIO()).run(unittest.defaultTestLoader.loadTestsFromTestCase(IdentitySessionTests))
    assert result.wasSuccessful(),result.errors+result.failures

test_stdlib_suite.__test__=False
