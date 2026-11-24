"""Try confirmation reads on SimDrive without changing the shipped ladder."""

import argparse
from itertools import combinations
import json
import math

from verify import instrument, setup


def install_trial(repeat_sigmas, keep_strong):
    import numpy as np

    from discprobe import geo, varpitch

    class ConfirmLadder(geo.Ladder):
        attempts = 0
        last_attempt = -10

        def fit(self, *args, **kwargs):
            was_bent = self.bend is not None
            super().fit(*args, **kwargs)
            count = len(self.targets)
            if was_bent or self.progress_stage != 'ladder' or count < 7 or not self.auto_correct:
                return
            typical_std = np.median([t['std_deg'] for t in self.targets])
            if typical_std < .55:
                return
            if keep_strong and self.bend is not None and self.chi2_dof > self.chi2_abort:
                return
            self.bend = None
            residual = np.array([t['residual_deg'] for t in self.targets])
            sigma = np.array([t['sigma_deg'] for t in self.targets])
            radii = self._fit_radius([t['n'] for t in self.targets])
            if (self.chi2_dof <= 4 or np.ptp(radii) < 5 or
                    np.max(abs(residual)) >= geo.TURN_ABORT_DEG or
                    np.mean(residual**2) <= max(.35**2, 4 * np.mean(sigma**2)) or
                    self.attempts == 2 or count - self.last_attempt < 3):
                return

            # Build contrasts from five measured radii. Their weights remove
            # the local constant-pitch basis (offset, radius and inverse radius).
            # Select from the most informative residuals before any reread.
            eligible = []
            for i in np.argsort(-abs(residual) / sigma):
                if all(abs(radii[i] - radii[j]) >= .02 for j in eligible):
                    eligible.append(i)
                if len(eligible) == 8:
                    break
            if len(eligible) < 5:
                return
            noise = np.hypot(sigma, .30)
            choices = np.array(list(combinations(eligible, 5)))
            r = radii[choices]
            s = noise[choices]
            design = np.stack([np.ones_like(r), r, 1 / r], axis=-1)
            basis, _ = np.linalg.qr(design / s[..., None])
            z = residual[choices] / s
            projection = np.einsum('nij,nj->ni', basis.transpose(0, 2, 1), z)
            contrast = z - np.einsum('nij,nj->ni', basis, projection)
            strength = np.linalg.norm(contrast, axis=1)
            best = np.argmax(strength)
            if strength[best] < 2.5:
                return
            self.attempts += 1
            self.last_attempt = count
            weights = contrast[best] / (s[best] * strength[best])
            repeat_errors = []
            for i in choices[best]:
                original = self.targets[i]
                new = self._measure_retry(original['lba'])
                self.progress_probe_done += self.reps
                self.progress_total += self.reps
                if new is None:
                    return
                innovation = (new['phase_deg'] - original['unwrapped_deg'] + 180) % 360 - 180
                if abs(innovation) > geo.SAFE_DEG:
                    return
                repeat_errors.append((residual[i] + innovation, math.hypot(new['sigma_deg'], .30)))
            errors, noise = np.array(repeat_errors).T
            if weights @ errors > repeat_sigmas * np.linalg.norm(weights * noise):
                self.bend = varpitch.Bend(radii, residual, sigma)

    geo.Ladder = ConfirmLadder


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('group', choices=('negative', 'positive'))
    parser.add_argument('--seeds', type=int, nargs='+')
    parser.add_argument('--start', type=int, default=0)
    parser.add_argument('--end', type=int, default=200)
    parser.add_argument('--detect-only', action='store_true')
    parser.add_argument('--repeat-sigmas', type=float, default=2.8)
    parser.add_argument('--keep-strong', action='store_true', help='keep an existing bend when the constant fit would abort')
    args = parser.parse_args()
    setup(False)
    install_trial(args.repeat_sigmas, args.keep_strong)
    cases = [('constant', 70)] if args.group == 'negative' else [
        (p, j) for p in ('i218', 'mild', 'step') for j in (20, 100)]
    for seed in args.seeds or range(args.start, args.end):
        profile, jitter = cases[seed % len(cases)]
        print(json.dumps(instrument(profile, seed, jitter, detect_only=args.detect_only)), flush=True)


if __name__ == '__main__':
    main()
