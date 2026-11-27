"""Sweep spatial gate thresholds on fixed ladder prefixes before changing probe placement."""
import argparse
from itertools import product
import json

from verify import TEMP, instrument, setup


def capture(kind, start, end):
    from discprobe import varpitch

    cases = [(p, j) for p in ('i218', 'mild', 'step') for j in (20, 100)] if kind == 'positive' else [('constant', 70)]
    for seed in range(start, end):
        prefixes = []

        def record(targets, chi2, radii):
            if len(targets) >= 7:
                measurements = [(t['residual_deg'], t['sigma_deg'], t['std_deg'], t['used']) for t in targets]
                prefixes.append(dict(chi2=chi2, x=list(radii), r=measurements))
            return False

        varpitch.exceeds_noise = record
        profile, jitter = cases[seed % len(cases)]
        instrument(profile, seed, jitter, detect_only=True)
        print(json.dumps(dict(profile=profile, seed=seed, jitter=jitter, prefixes=prefixes)), flush=True)


def spatial_features(prefix):
    import numpy as np

    order = np.argsort(prefix['x'])
    radius = np.asarray(prefix['x'])[order]
    y, sigma, std, count = np.asarray(prefix['r'])[order].T
    fit_noise = np.sqrt(np.mean(sigma ** 2))
    if np.ptp(radius) < 5 or np.sqrt(np.mean(y ** 2)) <= max(.35, 2 * fit_noise):
        return False, []
    sem = std / np.sqrt(count)
    noise = np.maximum(sigma, np.maximum(sem, np.median(sem)))
    gap = np.diff(radius)
    neighbours = (gap >= .02) & (gap <= 8)
    local = neighbours & (gap <= 3)
    ratio = abs(np.diff(y))[local] / np.hypot(noise[:-1], noise[1:])[local]
    scale = max(1., np.median(ratio) / .67449) if len(ratio) >= 4 else 1.
    z = y / noise
    individual = np.minimum(abs(z[:-1]), abs(z[1:]))
    amplitude = (abs(y[:-1]) + abs(y[1:])) / 2
    combined = abs(z[:-1] + z[1:]) / np.sqrt(2)
    common = neighbours & (y[:-1] * y[1:] > 0)
    if np.median(std) < .55:
        return bool(np.any(common & (amplitude >= .55) & (individual >= .9) & (combined >= 3.5))), []

    # This optimistic steep-feature screen gives the stricter thresholds the
    # benefit of any prefix with two large residuals and a third excess point.
    second, third = sorted(abs(y))[-2:-4:-1]
    if second >= 4 and third >= 1:
        return True, []
    clipped = np.clip(z, -3, 3)
    weight = np.exp(-gap / 3) * neighbours
    power = np.sum(weight * (clipped[:-1] ** 2 + clipped[1:] ** 2) / 2)
    coherence = max(0., np.sum(weight * clipped[:-1] * clipped[1:]) / max(1., power))
    pairs = [(a, b, c, scale, coherence)
             for a, b, c in zip(individual[common], amplitude[common], combined[common])]
    return False, pairs


def sweep():
    import numpy as np

    def load(name):
        data = (TEMP / f'prefix-{name}.jsonl').read_bytes()
        return [json.loads(line) for line in data.decode('utf-16' if data.startswith(b'\xff\xfe') else 'utf-8').splitlines()]

    train, holdout, positive = (load(group) for group in ('neg', 'holdout', 'pos'))
    flags, pairs = [], []
    for i, row in enumerate(train + holdout + positive):
        features = [spatial_features(prefix) for prefix in row['prefixes']]
        flags.append(any(passed for passed, _ in features))
        pairs.extend((i, *pair) for _, local_pairs in features for pair in local_pairs)
    ids, individual, amplitude, combined, scale, coherence = np.asarray(pairs).T
    ids = ids.astype(int)
    flags = np.array(flags)
    options = []
    split = len(train) + len(holdout)
    grid = product((0, .25, .4, .5, .6, .8, 1.), (.85, .95, 1.05, 1.10, 1.15, 1.2, 1.25, 1.3, 1.4, 1.5),
                   (2.5, 3, 3.5, 4, 4.5, 5), (.7, 1., 1.3, 1.5, 1.8), (0., .5, 1.))
    for boost, amp_min, joint_min, individual_min, exponent in grid:
        inflation = scale ** exponent
        passing = ((amplitude + coherence * boost >= amp_min) & (combined >= joint_min * inflation)
                   & (individual >= individual_min * inflation))
        detected = flags.copy()
        detected[ids[passing]] = True
        first = int(detected[:len(train)].sum())
        second = int(detected[len(train):split].sum())
        if first <= .02 * len(train) and second <= .02 * len(holdout):
            options.append(dict(positive=int(detected[split:].sum()), train_false=first, holdout_false=second,
                                thresholds=(boost, amp_min, joint_min, individual_min, exponent)))
    best = sorted(options, key=lambda opt: (-opt['positive'], opt['train_false'] + opt['holdout_false']))
    print(json.dumps(dict(eligible=len(options), best=best[:8]), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('negative', 'positive', 'sweep'))
    parser.add_argument('start', type=int, nargs='?', default=0)
    parser.add_argument('end', type=int, nargs='?', default=200)
    args = parser.parse_args()
    setup(False)
    if args.mode == 'sweep':
        sweep()
    else:
        capture(args.mode, args.start, args.end)
