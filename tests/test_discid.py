"""Identity tests use files, injected sector readers and fake recorders only."""
import datetime
from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import threading
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import pytest

from discprobe import burner, calib, calibdisc, cd, cdimage, discid, imagedisc, iso9660

def assert_same_outside(a, b, ignored):
    ignore = set(ignored)
    assert len(a) == len(b)
    assert all(a[i*2048:(i+1)*2048] == b[i*2048:(i+1)*2048] for i in range(len(a)//2048) if i not in ignore)


ROOT = Path(__file__).resolve().parents[1]
FIXED = datetime.datetime(2026, 11, 12, tzinfo=datetime.timezone.utc)


def small_layout(seed=1):
    return calib.CalLayout(total_sectors=128, seed=seed,
        bands=[dict(index=0, s=0., lba_start=64, lba_end=112)], guards_lba=[[32, 64], [112, 128]])


def baseline_jobs(sectors=128):
    design = np.zeros((64, 64), bool)
    design[:12] = True
    args = (design, 24 / .0001333, .00074 / .0001333, 133.3, sectors)
    jobs = {}
    for i in range(2):
        jobs['image' + str(i)] = lambda p, i=i, **kw: imagedisc.write_iso(
            str(p), *args, dark=['A5', '92'][i], log=lambda _: None, **kw)
        from discprobe import randomdisc
        jobs['random' + str(i)] = lambda p, i=i, **kw: randomdisc.write_iso(
            str(p), sectors, seed=i, log=lambda _: None, **kw)
        jobs['calib' + str(i)] = lambda p, i=i, **kw: calib.write_iso(
            str(p), small_layout(i) if sectors == 128 else calib.CalLayout(total_sectors=sectors, seed=i, bands=[dict(index=0, s=0., lba_start=64, lba_end=sectors-64)], guards_lba=[[32,64],[sectors-64,sectors]]), log=lambda _: None, **kw)
        jobs['calibdisc' + str(i)] = lambda p, i=i, **kw: calibdisc.write(
            str(p), sectors=sectors, split=bool(i), log=lambda _: None, **kw)
    return jobs


def _check_prechange_hashes_and_only_filesystem_changes(tmp_path, name):
    before = json.loads((ROOT / 'tests/data/discid-baseline.json').read_text())[name]
    old, new = tmp_path / 'old.iso', tmp_path / 'new.iso'
    fn = baseline_jobs()[name]
    fn(old)
    assert hashlib.sha256(old.read_bytes()).hexdigest() == before
    fn = baseline_jobs(discid.MIN_SECTORS)[name]
    old.unlink()
    fn(old)
    fn(new, disc_id_code='KOI-A 3-05')
    a, b = old.read_bytes(), new.read_bytes()
    assert len(a) == len(b)
    changed = [i for i in range(len(a)//2048) if a[i*2048:(i+1)*2048] != b[i*2048:(i+1)*2048]]
    permitted = set([20, *discid.sectors_for(discid.MIN_SECTORS)])
    if name == 'calibdisc1':
        permitted.update(range(32))
    assert set(changed) <= permitted
    assert set(discid.sectors_for(discid.MIN_SECTORS)) <= set(changed)
    record = discid.read_image(new)
    assert record['body']['code'] == 'KOI-A 3-05'
    assert len(bytes.fromhex(record['body']['id'])) == 16
    assert record['body']['burn'] is None
    assert discid.decode(b[21*2048:25*2048]) == record


def _check_real_picture_bytes_and_cd(tmp_path):
    design = imagedisc.grid_design(r_min=24.15, r_max=25, line=.15, size=1024)
    args = (design, 24/.0001333, .00074/.0001333, 133.3, discid.MIN_SECTORS)
    a, b = tmp_path/'a.iso', tmp_path/'b.iso'
    imagedisc.write_iso(str(a), *args, log=lambda _: None)
    imagedisc.write_iso(str(b), *args, disc_id=True, log=lambda _: None)
    assert_same_outside(a.read_bytes(), b.read_bytes(), [20, *discid.sectors_for(discid.MIN_SECTORS)])
    assert imagedisc._sample(*args[:3], .0001333, 4096, 4096).any()
    assert imagedisc.verify_iso(str(b), *args) == []
    design = np.zeros((6000,6000), bool)
    args = (design, 25/(cd.BIT_NM*1e-6), .0016/(cd.BIT_NM*1e-6), cd.BIT_NM, discid.MIN_SECTORS)
    cdimage.write_iso(str(tmp_path/'cd0.iso'), *args, log=lambda _: None)
    cdimage.write_iso(str(tmp_path/'cd1.iso'), *args, log=lambda _: None, disc_id=True)
    assert_same_outside((tmp_path/'cd0.iso').read_bytes(), (tmp_path/'cd1.iso').read_bytes(), [20, *discid.sectors_for(discid.MIN_SECTORS)])
    assert cdimage.verify_iso(str(tmp_path/'cd1.iso'), *args, full=True) == []


def _check_metadata_privacy_and_provenance(tmp_path):
    source = tmp_path/'画.png'
    source.write_bytes(b'source content')
    geo = tmp_path/'geo-test'
    geo.mkdir()
    (geo/'summary.json').write_text('{"fit":{}}')
    record = discid.create(source=source, design=np.zeros((64,64), bool), code='KOI-A 3-05',
                           meta=dict(geometry_from=str(geo), completion_sectors=16,
                                     completion_source={'origin':'manual'}, along_track_frames=206,
                                     user='not recorded', host='not recorded', path=str(tmp_path)))
    body = record['body']
    assert body['design']['source_file'] == '画.png'
    assert body['design']['image_sha256'] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert body['geometry']['summary_sha256'] == hashlib.sha256((geo/'summary.json').read_bytes()).hexdigest()
    assert body['geometry']['geo_run'] == 'geo-test'
    assert body['geometry']['completion_sectors'] == 16
    assert body['generator']['git_commit']
    assert str(tmp_path) not in discid.canonical(record).decode()
    assert 'not recorded' not in discid.canonical(record).decode()


def _check_hash_malformed_record_and_extent(tmp_path):
    fn = baseline_jobs(discid.MIN_SECTORS)['random0']
    path = tmp_path/'x.iso'
    fn(path, disc_id=True)
    record = discid.read_image(path)
    record['body']['code'] = 'changed'
    with pytest.raises(ValueError, match='SHA-256'):
        discid.validate(record)
    with pytest.raises(ValueError, match='8192'):
        discid.encode(discid.create(code='a'*9000))
    with path.open('r+b') as f:
        f.seek(21*2048)
        f.write(b'!')
    assert discid.read_image(path)
    for lba in discid.positions(discid.MIN_SECTORS):
        with path.open('r+b') as f:
            f.seek(lba*2048); f.write(b'!')
    assert discid.read_image(path, detailed=True)['reason'] == 'absent'
    data = bytearray(iso9660.sectors(discid.MIN_SECTORS, 'TEST', discid.create())[20])
    entry = 68
    data[entry+2:entry+6] = (127).to_bytes(4,'little')
    header = iso9660.sectors(128,'TEST')
    header[20] = bytes(data)
    with pytest.raises(ValueError, match='extent'):
        discid.read(lambda lba,n: b''.join(header.get(i,bytes(2048)) for i in range(lba,lba+n)))


def _check_reject_overlap_partial_and_short_before_writing(tmp_path):
    path = tmp_path/'x.iso'
    design = np.ones((64,64),bool)
    args = (str(path), design, 24/.0001333, .00074/.0001333, 133.3, discid.MIN_SECTORS)
    with pytest.raises(ValueError, match='overlaps'):
        imagedisc.write_iso(*args, disc_id=True)
    assert not path.exists()
    with pytest.raises(ValueError, match='complete ISO'):
        imagedisc.write_iso(*args, disc_id=True, first_lba=32)
    with pytest.raises(ValueError, match='short'):
        from discprobe import randomdisc
        randomdisc.write_iso(str(path),24,disc_id=True)
    layout = small_layout()
    layout.total_sectors = discid.MIN_SECTORS
    layout.bands[0]['lba_start'] = 24
    with pytest.raises(ValueError, match='overlaps'):
        calib.write_iso(str(path), layout, disc_id=True)
    assert not path.exists()


class SectorDevice:
    def __init__(self, data):
        self.data = data
        self.reads = []
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def execute(self, cdb, **kwargs):
        from discprobe.scsi import check_allowed
        check_allowed(cdb)
        if cdb[0] == 0x25:
            return SimpleNamespace(ok=True, data=((len(self.data)//2048-1).to_bytes(4,'big') + (2048).to_bytes(4,'big')))
        assert cdb[0] == 0x28
        start, count = int.from_bytes(cdb[2:6],'big'), int.from_bytes(cdb[7:9],'big')
        self.reads.append((start,count))
        return SimpleNamespace(ok=True, data=self.data[start*2048:(start+count)*2048])


def _check_burn_stream_hash_log_and_readback(tmp_path):
    image = tmp_path/'x.iso'
    baseline_jobs(discid.MIN_SECTORS)['random1'](image, disc_id=True)
    before = image.read_bytes()
    template_id = discid.read_image(image)['body']['id']
    captured = {}
    def write(view, speed, cancel, progress):
        assert isinstance(view, discid.PatchedImage)
        with view.open('rb') as stream:
            stream.seek(21*2048-3)
            assert stream.read(6) == before[21*2048-3:21*2048] + view.patch_bytes[:3]
            stream.seek(0)
            captured['data'] = stream.read()
        captured['record'] = discid.read_device(SectorDevice(captured['data']))
        assert image.read_bytes() == before
        return 8.
    recorder = Mock()
    recorder.inspect.return_value = dict(blank=True, media='dvd', free_sectors=discid.MIN_SECTORS, speeds_x=[8],
        vendor='HL-DT-ST', product='DVD-RAM GH70N', firmware='NYA2', media_type='DVD-R', mid='RITEKF1', atip=None)
    recorder.write.side_effect = write
    def verify(drive, view, media, cancel):
        dev = SectorDevice(captured['data'])
        result = burner.verify_image(drive, view, media, cancel, device_factory=lambda _: dev)
        assert all((x//16*16,16) in dev.reads for x in discid.positions(discid.MIN_SECTORS))
        return result
    result = burner.burn('FAKE', image, yes_write=True, recorder=recorder, verifier=verify,
                         speed=8, disc_id_code='KOI-A 3-05')
    assert result['verified']
    assert result['identity'] == captured['record']
    assert result['identity']['body']['id'] != template_id
    assert result['identity']['body']['generator']['template_id'] == template_id
    burn = captured['record']['body']['burn']
    assert burn['requested_speed_x'] == 8 and burn['mid'] == 'RITEKF1'
    log = [json.loads(line) for line in Path(result['log_path']).read_text(encoding='utf-8').splitlines()]
    assert log[1]['type'] == 'disc_identity' and log[1]['identity'] == captured['record']
    assert image.read_bytes() == before
    # Comparing with the original ISO must fail; the patched view passes.
    with patch.object(burner, 'sample_lbas', return_value=sorted({x//16*16 for x in discid.positions(discid.MIN_SECTORS)})):
        wrong = burner.verify_image('FAKE', image, 'dvd', threading.Event(),
            device_factory=lambda _: SectorDevice(captured['data']))
    assert wrong['differing'] > 0
    broken = bytearray(captured['data'])
    broken[24*2048+10] ^= 1
    view = discid.PatchedImage(image, captured['record'])
    failed = burner.verify_image('FAKE', view, 'dvd', threading.Event(), device_factory=lambda _: SectorDevice(broken))
    assert failed['differing'] > 0
    second = discid.patch_burn(image, {}, speed=None, selected=8, media='dvd')
    assert second.record['body']['id'] != captured['record']['body']['id']


def _check_consent_no_flag_and_missing_slot(tmp_path, capsys):
    image = tmp_path/'x.iso'
    baseline_jobs()['random0'](image)
    assert 'anyone' not in capsys.readouterr().out
    rec = Mock()
    with pytest.raises(burner.BurnError, match='generated with'):
        burner.burn('FAKE', image, recorder=rec, yes_write=True, disc_id=True)
    rec.inspect.assert_not_called()
    baseline_jobs(discid.MIN_SECTORS)['random0'](image, disc_id=True)
    assert 'anyone with the disc' in capsys.readouterr().out
    before = image.read_bytes()
    rec.inspect.return_value = dict(blank=True, media='dvd', free_sectors=discid.MIN_SECTORS, speeds_x=[8])
    rec.write.return_value = 8
    result = burner.burn('FAKE', image, recorder=rec, yes_write=True, no_verify=True)
    assert rec.write.call_args.args[0] == image.resolve()
    assert image.read_bytes() == before
    assert result['identity'] == discid.read_image(image)
    assert result['identity']['body']['burn'] is None


def _check_whois_info_register(tmp_path, capsys):
    from discprobe import __main__
    image = tmp_path/'x.iso'
    baseline_jobs(discid.MIN_SECTORS)['random0'](image, disc_id_code='KOI-A 3-05')
    capsys.readouterr()
    record = discid.patch_burn(image, {}, speed=8, selected=8, media='dvd').record
    register = tmp_path/'register.json'
    original = dict(schema_version=1, status='draft', boxes=[], discs=[])
    register.write_text(json.dumps(original))
    entry = discid.append_register(register, record, image=image,
        result=dict(result='completed', verification={'status':'skipped'}))
    assert (entry['abbr'], entry['revision'], entry['batch'], entry['sequence']) == ('KOI','A',3,5)
    assert json.loads(register.read_text())['status'] == 'draft'
    with pytest.raises(ValueError, match='already'):
        discid.append_register(register, record, result={'result':'completed'})
    before = register.read_bytes()
    for command in ('whois','info'):
        __main__._main([command,'--image',str(image),'--register',str(register)])
        out = json.loads(capsys.readouterr().out)
        assert out['status'] == 'present' and out['hash_verified']
        assert out['register']['code_matches'][0]['id'] == record['body']['id']
        assert out['register']['id_matches'] == []
    with patch.object(__main__, '_open', return_value=SectorDevice(image.read_bytes())):
        __main__._main(['whois','--drive','H:'])
    assert json.loads(capsys.readouterr().out)['record'] == discid.read_image(image)
    assert register.read_bytes() == before


def _check_windows_compiled_overlay_without_com(tmp_path):
    # Compile the actual IStream implementation; do not execute script/COM entrypoints.
    script = (ROOT/'tools/burn_imapi.ps1').read_text(encoding='utf-8')
    source = script.split('-TypeDefinition @"',1)[1].split('\n"@',1)[0]
    image, patch_file = tmp_path/'x.iso', tmp_path/'identity.bin'
    image.write_bytes(bytes(64*2048))
    patch_file.write_bytes(bytes([123])*8192)
    harness = r'''
public static class IdentityTest {
    public static void Run(string image, string patch) {
        using (IdentityStream s = new IdentityStream(image, patch, 43008)) {
            IntPtr n = Marshal.AllocHGlobal(8);
            try {
                s.Seek(43006, 0, n);
                byte[] b = new byte[8200]; s.Read(b, b.Length, n);
                if (Marshal.ReadInt32(n) != 8200 || b[1] != 0 || b[2] != 123 || b[8193] != 123 || b[8194] != 0)
                    throw new Exception("Overlay bytes differ");
                STATSTG stat; s.Stat(out stat, 0);
                if (stat.cbSize != 131072) throw new Exception("Wrong stream size");
                s.Seek(43008, 0, n);
                IStream clone; s.Clone(out clone);
                clone.Read(b, 3, n);
                if (b[0] != 123 || Marshal.ReadInt32(n) != 3) throw new Exception("Clone lost patch");
                ((IDisposable)clone).Dispose();
                s.Seek(-3, 2, n); s.Read(b, 100, n);
                if (Marshal.ReadInt32(n) != 3) throw new Exception("Wrong EOF count");
            } finally { Marshal.FreeHGlobal(n); }
        }
        Console.WriteLine("IDENTITY_STREAM_PASSED");
    }
}
'''
    ps = tmp_path/'compile.ps1'
    ps.write_text("$ErrorActionPreference='Stop'\nAdd-Type -ReferencedAssemblies System.dll,System.Core.dll,Microsoft.CSharp.dll -TypeDefinition @'\n"
                  + source + harness + "\n'@\n[IdentityTest]::Run($args[0],$args[1])\n",encoding='utf-8-sig')
    result = subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-File',str(ps),str(image),str(patch_file)],
                            capture_output=True, encoding='utf-8', errors='replace', timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'IDENTITY_STREAM_PASSED' in result.stdout
    assert image.read_bytes() == bytes(64*2048)


class DiscIdTests(unittest.TestCase):
    """Also runnable by the project's fixture-free selftest runner."""
    def run_case(self, fn, name=None):
        class Fixed(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return FIXED
        class Capture(io.StringIO):
            def readouterr(self):
                out = self.getvalue()
                self.seek(0)
                self.truncate()
                return SimpleNamespace(out=out, err='')
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(iso9660.datetime,'datetime',Fixed), \
             patch.dict(os.environ, DISCPROBE_WORKERS='1'), \
             redirect_stdout(Capture()) as captured:
            import inspect
            values = dict(tmp_path=Path(folder), name=name, capsys=captured)
            fn(**{key: values[key] for key in inspect.signature(fn).parameters})


def _check_adapter_stream_contracts(tmp_path):
    image = tmp_path/'source.iso'
    baseline_jobs(discid.MIN_SECTORS)['random0'](image,disc_id=True)
    view = discid.patch_burn(image,{},speed=8,selected=8,media='dvd')
    with view.open('rb') as source:
        expected = source.read()
    captured = {}
    def windows_spawn(argv, **kwargs):
        assert Path(argv[argv.index('-Iso')+1]) == image
        captured['windows'] = Path(argv[argv.index('-IdentityPatch')+1]).read_bytes()
        assert argv[argv.index('-IdentityOffset')+1] == '43008'
        return Mock(stdout=iter([]),wait=Mock(return_value=0))
    with patch.object(burner,'tool',return_value='fake'):
        windows = burner.WindowsDVD('H:','dvd',popen=windows_spawn)
    windows.write(view,8,threading.Event(),Mock())
    assert captured['windows'] == view.patch_bundle()
    class Input:
        def __init__(self):
            self.buffer = io.BytesIO()
        def close(self):
            captured['linux'] = self.buffer.getvalue()
    def linux_spawn(argv, **kwargs):
        assert '/dev/fake=/dev/fd/0' in argv
        assert '-use-the-force-luke=tracksize:32768' in argv
        assert kwargs['stdin'] == subprocess.PIPE
        return Mock(stdin=Input(),stdout=iter([]),wait=Mock(return_value=0))
    with patch.object(burner,'tool',return_value='fake'):
        linux = burner.LinuxBurner('/dev/fake','dvd',popen=linux_spawn)
    linux.write(view,8,threading.Event(),Mock())
    assert captured['linux'] == expected


def _check_cli_consent_and_chinese_help(tmp_path):
    from discprobe import __main__, i18n, zh
    parser, sub, _ = __main__._build_parser()
    for name in ('image','random','calib','calibdisc','burn'):
        options = sub.choices[name]._option_string_actions
        assert '--disc-id' in options and '--disc-id-code' in options and '--disc-code' in options
        assert options['--disc-id'].default is False
        assert options['--disc-id'].help in zh.TEXT or i18n.active() == 'zh'
    from discprobe import randomdisc
    with patch.object(randomdisc,'write_iso') as write, \
         patch.object(__main__.ui,'iso_ready'), patch.object(__main__,'_next'):
        __main__._main(['random','--output',str(tmp_path/'x.iso'),'--sectors','128','--disc-id-code','KOI-A 3-05'])
    assert write.call_args.kwargs['disc_id_code'] == 'KOI-A 3-05'


def _install_checks():
    def method(fn, name=None):
        def run(self):
            self.run_case(fn,name)
        return run
    for name in baseline_jobs():
        setattr(DiscIdTests,'test_baseline_'+name,method(_check_prechange_hashes_and_only_filesystem_changes,name))
    for name,fn in list(globals().items()):
        if name.startswith('_check_') and name != '_check_prechange_hashes_and_only_filesystem_changes':
            run = method(fn)
            if name == '_check_windows_compiled_overlay_without_com':
                run = unittest.skipUnless(os.name == 'nt','Windows compiler only')(run)
            setattr(DiscIdTests,'test_'+name[7:],run)


_install_checks()


def test_stdlib_suite():
    result = unittest.TextTestRunner(stream=io.StringIO()).run(unittest.defaultTestLoader.loadTestsFromTestCase(DiscIdTests))
    assert result.wasSuccessful(), result.errors + result.failures


test_stdlib_suite.__test__ = False
