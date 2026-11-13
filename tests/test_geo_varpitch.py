"""Variable pitch, whole turns and actual-use coverage. Synthetic instrument only."""
import contextlib
import io
import json
import math
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from discprobe.calib import theta
from discprobe.coverage import assess_range, range_warning
from discprobe.geo import Ladder, write_outputs
from discprobe.guide import Result, install_blocker, latest_geo
from discprobe.imagedisc import load_correction
from discprobe.sim import SimDrive


class PhaseOracle(Ladder):
    def __init__(self, readable=None, perturb=None, **kwargs):
        super().__init__(None, state_check=False, log=lambda *_: None, **kwargs)
        self.tp = SimpleNamespace(setup=lambda: None, cache_test=lambda: None, strategy='fua',
                                  last_lba=2295103, summary={}, audio=False, events_as_rows=lambda: [])
        self.rng = np.random.default_rng(0)
        self.readable, self.perturb = readable, perturb
        self.truth_u, self.truth_v = 23.93 / .0001336, .000735 / .0001336

    def _random_parts(self, ranges):
        return ranges

    def check_rotation(self):
        pass

    def settle(self, *args, **kwargs):
        self.T = .02
        return self.T

    def _measure_retry(self, lba, reps=None):
        if self.readable and not any(a <= lba <= z for a, z in self.readable):
            return None
        n = self._n_end(lba)
        phase = math.degrees(theta(n, self.truth_u, self.truth_v) - theta(self.n_ref, self.truth_u, self.truth_v))
        phase += self.perturb(lba) if self.perturb else 0
        return dict(lba=lba, n=n, phase_deg=(phase + self.rng.normal(0, .2)) % 360,
                    sigma_deg=.2, std_deg=.2 * math.sqrt(24), used=24, period_ms=20.)


def test_variable_pitch_end_to_end():
    with tempfile.TemporaryDirectory(prefix='geo-variable-') as temp:
        for profile, jitter in ((p, j) for j in (20, 100) for p in ('constant', 'i218', 'mild', 'step')):
            dev = SimDrive(phi_profile=profile, rev_period_ms=26, jitter_us=jitter, outlier_rate=0, seed=7)
            ladder = Ladder(dev, ranges=[(20000, 2294000)], speed_kbs=None, log=lambda *_: None)
            result = ladder.run()
            folder = Path(temp) / f'{profile}-{jitter}'
            write_outputs(ladder, str(folder))
            assert result['completion_status'] == 'target_reached'
            if profile == 'constant':
                assert ladder.bend is None and ladder.correction is None
            else:
                assert ladder.correction and len(ladder.probes) >= 90
                assert result['correction_validation']['independent_rms_deg'] < .5
                assert result['correction_validation']['independent_checks'] > 10
            lbas = np.linspace(20000, 2293984, 6000).astype(int)
            ns = np.array([ladder._n_end(int(l)) for l in lbas])
            model = np.degrees(theta(ns, ladder.u, ladder.v))
            if ladder.correction:
                corr = load_correction(str(folder / 'correction.json'))
                model -= corr(ladder._fit_radius(ns))
                # Clamp contract and process-pickle compatibility of the existing loader.
                import pickle
                cloned = pickle.loads(pickle.dumps(corr))
                assert cloned(corr.lo - 1) == cloned(corr.lo)
                assert cloned(corr.hi + 1) == cloned(corr.hi)
            truth = np.array([math.degrees(dev.track_angle((int(l) // 16 + 1) * 16)) for l in lbas])
            err = model - truth
            assert np.sqrt(np.mean((err - err.mean()) ** 2)) < .5
            rung_err = [t['unwrapped_deg'] - math.degrees(dev.track_angle((t['lba']//16+1)*16)
                        - dev.track_angle((ladder.ref//16+1)*16)) for t in ladder.targets]
            assert max(abs(np.array(rung_err) - np.median(rung_err))) < 180


def test_partial_run_has_task_scoped_trust():
    ladder = PhaseOracle(readable=[(850000, 1200000)])
    fit = ladder.run()
    assert len(ladder.targets) == 17
    assert fit['completion_status'] == 'candidates_exhausted'
    lo, hi = fit['measured_span_mm']
    local = [lo + .01, hi - .01]
    assert assess_range(fit, local)['covered']
    full = assess_range(fit, [24.5, 56])
    assert not full['covered'] and len(full['extrapolated_mm']) == 2
    assert full['conditional_angle_sigma_deg'] > 10
    with tempfile.TemporaryDirectory(prefix='geo-coverage-') as temp:
        folder = Path(temp) / 'geo-AUDIT-20261107-000000'
        write_outputs(ladder, str(folder))
        summary = str(folder / 'summary.json')
        run = Result(str(folder), 'geo', 'AUDIT', '20261107-000000')
        assert not run.geo_complete() and not run.reliable()
        assert run.reliable(local) and not run.reliable([24.5, 56])
        assert latest_geo(out=temp) is None
        assert latest_geo(out=temp, radius_range=local).path == str(folder)
        assert install_blocker(summary, radius_range=local) is None
        assert 'EXTRAPOLATION' in install_blocker(summary, radius_range=[24.5, 56])
        # Both command paths use the same range assessment before creating a preset.
        from discprobe.__main__ import _export_gate
        args = SimpleNamespace(geo=summary, install=False, force=False, _radius_range=local)
        _export_gate(args)
        args._radius_range = [24.5, 56]
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                _export_gate(args)
        except SystemExit:
            pass
        else:
            raise AssertionError('full-range partial export passed')


def test_three_islands_and_unsampled_model_bias():
    ladder = PhaseOracle(readable=[(100000, 500000), (850000, 1200000), (1600000, 1950000)])
    fit = ladder.run()
    islands = fit['coverage']['measured_intervals_mm']
    assert len(islands) >= 3
    assert not assess_range(fit, [islands[0][0], islands[-1][1]])['covered']
    assert range_warning(fit, [islands[0][0], islands[-1][1]])
    # A perturbation wholly between sampled addresses has exactly the same data.
    base = PhaseOracle()
    result = base.run()
    lbas = sorted(t['lba'] for t in base.targets)
    a, z = max(zip(lbas, lbas[1:]), key=lambda pair: pair[1] - pair[0])
    bump = lambda n: math.sin(math.pi * (n-a)/(z-a))**4 if a < n < z else 0.
    other = PhaseOracle(perturb=bump)
    changed = other.run()
    assert [t['lba'] for t in base.targets] == [t['lba'] for t in other.targets]
    assert result['u'] == changed['u'] and result['v'] == changed['v']
    assert changed['coverage']['model_bias'].startswith('not bounded')
    assert bump((a + z)/2) == 1
    assert changed['coverage']['largest_unsampled_gap_mm'] > 1
    # A four-degree local plateau can also sit wholly inside that gap. Its edges
    # have finite slope; sampled endpoints still cannot detect it.
    def local_step(n):
        fraction = (n - a) / (z - a)
        return 4 * min(1., max(0., min((fraction - .2) / .02, (.8 - fraction) / .02)))
    plateau = PhaseOracle(perturb=local_step)
    step_result = plateau.run()
    assert step_result['u'] == result['u'] and step_result['v'] == result['v']
    assert local_step((a+z)/2) == 4


def test_wrong_turn_is_not_smoothed_away():
    class WrongTurn(PhaseOracle):
        def _add(self, m, predicted_deg):
            super()._add(m, predicted_deg + (360 if len(self.targets) == 5 else 0))
    ladder = WrongTurn()
    try:
        ladder.run()
    except RuntimeError as exc:
        assert 'whole-turn' in str(exc)
        assert ladder.completion_status == 'unwrap_ambiguous'
    else:
        raise AssertionError('wrong turn passed')


def test_disabled_mode_and_legacy_polynomial():
    dev = SimDrive(phi_profile='i218', rev_period_ms=26, jitter_us=20, outlier_rate=0, seed=7)
    ladder = Ladder(dev, ranges=[(20000, 2294000)], auto_correct=False, speed_kbs=None, log=lambda *_: None)
    try:
        ladder.run()
    except RuntimeError:
        pass
    assert ladder.correction is None and not ladder.probes
    with tempfile.TemporaryDirectory(prefix='geo-old-format-') as temp:
        path = Path(temp) / 'correction.json'
        path.write_text(json.dumps({'poly_in_x': [1, 2], 'radius_valid_mm': [25, 55]}))
        c = load_correction(str(path))
        assert c(40) == 2 and c(0) == 1 and c(80) == 3


def test_image_reports_actual_drawing_extrapolation():
    from discprobe import __main__ as cli, imagedisc
    from discprobe.calib import SECTOR_BITS
    with tempfile.TemporaryDirectory(prefix='geo-image-') as temp:
        root = Path(temp)
        geo = root / 'summary.json'
        geo.write_text(json.dumps({'fit': dict(u=24/.0001333, v=.00074/.0001333,
                                              bit_nm_assumed=133.3, measured_span_mm=[40.5,44.6])}))
        design = np.zeros((6000, 6000), bool)
        design[3000, 5100] = True  # 42 mm
        args = cli._build_parser()[0].parse_args(['image', '--geo', str(geo), '--output', str(root/'out.iso')])
        spans = []
        from discprobe.coverage import range_warning as real_warning
        def warning(fit, span):
            spans.append(span)
            return real_warning(fit, span)
        for x, expect_warning in [(5100, False), (5750, True)]:
            design[:] = False
            design[3000, x] = True
            output = io.StringIO()
            with patch.object(imagedisc, 'grid_design', return_value=design), \
                 patch.object(imagedisc, 'write_iso', return_value=str(root/'out.json')), \
                 patch.object(imagedisc, 'verify_iso', return_value=[]), \
                 patch.object(imagedisc, 'preview'), \
                 patch('discprobe.coverage.range_warning', side_effect=warning), \
                 patch.object(cli, '_image_ready'), contextlib.redirect_stdout(output):
                if expect_warning:
                    import pytest
                    with pytest.raises(SystemExit, match='EXTRAPOLATION'):
                        cli.cmd_image(args)
                else:
                    cli.cmd_image(args)
            assert ('EXTRAPOLATION' in output.getvalue()) == expect_warning
