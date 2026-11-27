"""Device-free completion convention tests, also runnable by the built-in selftest."""
import contextlib
import csv
import io
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

import numpy as np
import pytest

from discprobe import read_completion as rc, disexport, webui, calibrate
from discprobe.calib import theta, SECTOR_BITS
from discprobe.geo import Ladder, write_outputs

ROOT = Path(__file__).resolve().parents[1]


def make_run(root, events=False):
    run = root / 'geo-test'
    lad = Ladder(None)
    lad.u, lad.v, lad.c = 179983.3, 5.53741687, math.radians(.23)
    lad.ref = 1000000
    lad.n_ref = lad._n_end(lad.ref)
    lad.T = .01675
    lad.tp.last_lba = 2295103
    lad.tp.summary = dict(identity=dict(drive='HL-DT-ST DVDRAM GUE0N', firmware='T.02'),
                          setup=dict(last_lba=2295103), cache=dict(strategy='fua'))
    raw = []
    for k, lba in enumerate([70000, 900000, 1000096, 1200000, 1600000, 1900000]):
        n = lad._n_end(lba)
        unwrapped = math.degrees(theta(n, lad.u, lad.v) - theta(lad.n_ref, lad.u, lad.v) + lad.c)
        phase = round(unwrapped % 360, 3)
        lad.targets.append(dict(lba=lba, n=n, phase_deg=phase, unwrapped_deg=phase + 360 * round((unwrapped-phase)/360),
                                sigma_deg=.2, std_deg=0, used=24, period_ms=16.75, predicted_deg=unwrapped))
        for i in range(24):
            end = 10**12 + (k * 200 + i * 5) * 16750000
            for label, x, t in [('ref', lad.ref, end), ('target', lba, end + 2*16750000 + round(phase/360*16750000))]:
                raw.append(dict(experiment='phase', label=label, lba=x, command='read12', fua=True,
                                t_start_ns=t-40000000, t_end_ns=t, duration_us=40000, status=0, sense=''))
    lad.fit()
    write_outputs(lad, str(run))
    if events:
        with (run/'events.csv').open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(raw[0]))
            writer.writeheader()
            writer.writerows(raw)
    return run


def test_registry_exact_key_and_override():
    identity = dict(vendor=' HL-DT-ST ', product='DVDRAM GUE0N   ', revision='T.02 ')
    assert rc.resolve(identity)[0] == 16
    assert rc.resolve(dict(drive='HL-DT-ST DVD-RAM GH70N', firmware='NYA2'))[0] == 0
    assert rc.resolve(identity, 0)[0] == 0
    for field, value in [('revision', 'T.03'), ('product', 'GUE0N'), ('vendor', 'OTHER')]:
        assert rc.drive_entry({**identity, field:value}) is None
    assert rc.resolve({}) == (0, None)
    assert 'registry:' in rc.notice(*rc.resolve(identity))
    for value in [True, 1.5, 65537, '16']:
        with pytest.raises(ValueError):
            rc.sectors(value)
    with pytest.raises(ValueError):
        rc.resolve(identity, 0, 'cd')


def test_completion_is_exactly_unidentifiable_in_relative_phase():
    n = np.array([16, 31, 32, 33, 100000, 2000000]) * SECTOR_BITS
    u, v = 179983.3, 5.53741687
    shifted = rc.corrected_u(u, v, 16)
    first = theta(n, u, v) - theta(n[0], u, v)
    second = theta(n + 16*SECTOR_BITS, shifted, v) - theta(n[0] + 16*SECTOR_BITS, shifted, v)
    assert np.max(np.abs(np.degrees(first-second))) < 2e-7
    lad = Ladder(None, completion_sectors=16)
    assert lad._n_end(15) == 32*SECTOR_BITS
    assert lad._n_end(16) == 48*SECTOR_BITS
    lad.ref, lad.n_ref = 1000000, lad._n_end(1000000)
    assert abs(lad._lba_at_turns(0)-lad.ref) <= 16


def test_refit_roundtrip_and_originals_unchanged():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        for with_events in [False, True]:
            run = make_run(root, with_events)
            originals = {p.name:p.read_bytes() for p in run.iterdir()}
            f = json.loads(originals['summary.json'])['fit']
            doc, rows, method = rc.reapply(run, 16)
            assert method == ('events_refit' if with_events else 'targets_refit')
            assert abs(doc['fit']['u'] - rc.corrected_u(f['u'],f['v'],16)) < 1e-5
            assert abs(doc['fit']['v'] - f['v']) < 1e-9
            dest = root / ('new-events' if with_events else 'new-targets')
            rc.save_reapplied(run, 16, dest)
            f2, _ = rc.load_fit(dest)
            assert f2['completion_sectors'] == 16
            assert rc.reapply(dest,16)[2] == 'unchanged'
            back, _, _ = rc.reapply(dest,0)
            assert abs(back['fit']['u']-f['u']) < 1e-5
            assert all((run/name).read_bytes()==data for name,data in originals.items())
            if with_events:
                assert (dest/'events.csv').read_bytes() == originals['events.csv']
            with pytest.raises(ValueError):
                rc.save_reapplied(run, 16, run)


def test_summary_only_correction_and_no_double_application():
    with tempfile.TemporaryDirectory() as tmp:
        run = make_run(Path(tmp))
        (run/'targets.csv').unlink()
        f = rc.load_fit(run)[0]
        doc, rows, method = rc.reapply(run, 16)
        assert method == 'closed_form' and rows is None
        assert doc['fit']['u'] == rc.corrected_u(f['u'],f['v'],16)
        assert doc['fit']['v'] == f['v']
        assert doc['fit']['dis_equivalent']['inner_radius_mm'] == doc['fit']['r0_mm_at_bit']
        dest = Path(tmp)/'corrected'
        rc.save_reapplied(run,16,dest)
        assert rc.reapply(dest,16)[2] == 'unchanged'
        assert abs(rc.reapply(dest,0)[0]['fit']['u']-f['u']) < 1e-9


def test_export_stored_offset_override_and_zero_identity():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        run = make_run(root)
        def export(source, **kwargs):
            return disexport.export(str(source/'summary.json'),2297888,None,None,25.8,54.4,'test','Test',**kwargs)
        legacy = export(run)
        assert export(run,completion_sectors=0) == legacy
        assert 'completion_sectors' not in legacy['source']
        changed = export(run,completion_sectors=16)
        corrected = root/'corrected'
        rc.save_reapplied(run,16,corrected)
        stored = export(corrected)
        assert changed['preset'] == stored['preset']
        assert stored['source']['completion_sectors'] == 16
        assert stored['source']['completion_method'] == 'stored'


def test_cli_offline_and_chinese_help():
    from discprobe import __main__ as cli
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        run = make_run(root)
        parser = cli._build_parser()[0]
        args = parser.parse_args(['geo','--reapply',str(run),'--completion-sectors','16','--out',str(root/'new')])
        with patch.object(cli, '_open', side_effect=AssertionError('no device allowed')), contextlib.redirect_stdout(io.StringIO()) as output:
            cli.cmd_geo(args)
        assert 'targets_refit' in output.getvalue()
        assert rc.load_fit(root/'new')[0]['completion_sectors'] == 16
        # Exact help text is checked through the real language switch.
        for command in ['geo','disexport','calibrate']:
            result = subprocess.run([sys.executable,'-B','-m','discprobe',command,'--help','--lang','zh'],
                                    cwd=ROOT,capture_output=True,encoding='utf-8')
            assert result.returncode == 0 and '完成点' in result.stdout
        args = parser.parse_args(['geo','--reapply',str(run),'--out',str(root/'registry')])
        with patch.object(cli, '_open', side_effect=AssertionError('no device allowed')), contextlib.redirect_stdout(io.StringIO()) as output:
            cli.cmd_geo(args)
        assert 'registry:' in output.getvalue()
        assert rc.load_fit(root/'registry')[0]['completion_source']['origin'] == 'registry'


def test_web_flow_and_preset_path():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        run = make_run(root)
        for action in ['geo','calibrate','disexport']:
            args = dict(completion_sectors=16)
            if action == 'disexport':
                args.update(geo='geo-test',sectors=2297888,output='preset.json',photo='photo.json')
            payload = dict(action=action,drive='H:',media='dvd',args=args)
            argv,_ = webui.command(payload,root,[dict(id='H:')])
            assert argv[argv.index('--completion-sectors')+1] == '16'
            for bad in [True, 1.5, 65537]:
                with pytest.raises(webui.APIError):
                    webui.command({**payload,'args':{**args,'completion_sectors':bad}},root,[dict(id='H:')])
        from argparse import Namespace
        args = Namespace(geo=str(run),preset=str(root/'preset.json'),sectors=2297888,media='dvd',completion_sectors=16)
        with contextlib.redirect_stdout(io.StringIO()), patch('discprobe.__main__._export_gate'):
            saved = calibrate.save_preset(args)
        assert saved['source']['completion_sectors'] == 16


def test_catalogue_blank_capacity_is_separate_from_image():
    from discprobe.capacity import catalogue_capacity
    entry = json.loads((ROOT/'presets/catalogue.json').read_text())['MCC 02RG20']
    assert entry['image_sectors'] == 2295104
    assert catalogue_capacity('MCC 02RG20','dvd',ROOT)[0] == 2297888
    assert entry['source'].startswith('https://github.com/exotic-namruth/')


def test_geo_uses_registry_before_fitting_and_explicit_zero_wins():
    from discprobe import __main__ as cli
    from discprobe.sim import SimDrive
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        fits = []
        for name, extra in [('registry',[]),('manual',['--completion-sectors','0'])]:
            output = root/name
            args = cli._build_parser()[0].parse_args(['geo','--sim','cav','--out',str(output),
                                                       '--max-targets','14','--reps','16',*extra])
            identity = dict(drive='HL-DT-ST DVDRAM GUE0N', firmware='T.02')
            with patch.object(cli,'_open',return_value=SimDrive(seed=7,reread_delay_ms=35.0)), \
                 patch.object(cli,'_identity',return_value=identity), contextlib.redirect_stdout(io.StringIO()) as text:
                cli.cmd_geo(args)
            fit = rc.load_fit(next(output.glob('geo-*')))[0]
            fits.append(fit)
            assert fit.get('completion_sectors',0) == (16 if name=='registry' else 0)
            assert ('registry:' in text.getvalue()) == (name=='registry')
        assert abs(fits[0]['u'] - rc.corrected_u(fits[1]['u'],fits[1]['v'],16)) < .01


def test_pitch_refit_retains_completion_convention():
    import importlib.util
    spec = importlib.util.spec_from_file_location('completion_pitch_test',ROOT/'tools/geo_polyfit.py')
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        run = make_run(root)
        corrected = root/'offset16'
        rc.save_reapplied(run,16,corrected)
        data = [tool.load(str(corrected))]
        bit = 133.3e-6
        fitted = tool.joint_fit(data,0,40/bit,15/bit)
        summary = tool.merged_summary(data,[str(corrected)],fitted)
        assert summary['fit']['completion_sectors'] == 16
        with pytest.raises(ValueError,match='completion sectors differ'):
            tool.joint_fit(data+[tool.load(str(run))],0,40/bit,15/bit)
    # Parsing options must keep working on a core install before numpy is installed.
    code = "import sys; sys.modules['numpy']=None; from discprobe.__main__ import _build_parser; _build_parser()"
    result = subprocess.run([sys.executable,'-B','-c',code],cwd=ROOT,capture_output=True,encoding='utf-8')
    assert result.returncode == 0, result.stderr
