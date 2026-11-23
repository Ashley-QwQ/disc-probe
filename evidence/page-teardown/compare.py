"""Summarize the paired PM samples and compare the stationary Edge captures pixel by pixel."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageChops


MIB = 2 ** 20
CASES = tuple(f'{size}-{theme}-normal' for size in ('1366x768', '390x844') for theme in ('light', 'dark'))
SCENES = ('lobby', 'library', 'newplan', 'calibration', 'geometry', 'editor', 'preview', 'return',
          'reopen', 'pastworks', 'presets', 'faxnews')


def total(sample, field, kind=None):
    return sum(row[field] for row in sample['processes'] if kind is None or row['process_type'] == kind) / MIB


def numbers(sample):
    fields = ('private_bytes', 'working_set_bytes')
    pair = lambda kind: ' / '.join(f'{total(sample, field, kind):.1f}' for field in fields)
    return [pair(None), pair('renderer'), pair('gpu-process'), f"{sample['heap']['usedSize'] / MIB:.2f}", str(sample['dom']['nodes'])]


def measurement(root):
    print('| Theme | Scene | Rev | PB / WS | renderer | GPU | JS heap | DOM nodes |')
    print('| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |')
    for case in CASES[:2]:
        pair = {}
        for run in ('before', 'after'):
            path = root / run / 'samples' / f'{case}.json'
            if path.is_file():
                data = json.loads(path.read_text(encoding='utf-8'))
                if len(data['samples']) == 6 and all(row['idle_seconds'] >= 30 for row in data['samples']):
                    pair[run] = {row['scene']: row for row in data['samples']}
        for scene in ('blank', 'lobby', 'library', 'geometry', 'editor', 'return'):
            for run, samples in pair.items():
                print('| ' + ' | '.join([case.split('-')[1], scene, run, *numbers(samples[scene])]) + ' |')
        for run, samples in pair.items():
            net = [total(samples['return'], field) - total(samples['lobby'], field)
                   for field in ('private_bytes', 'working_set_bytes')]
            print(f"| {case.split('-')[1]} | return − lobby | {run} | {net[0]:+.1f} / {net[1]:+.1f} | | | | |")


def changed_pixels(before, after):
    with Image.open(before) as source, Image.open(after) as candidate:
        if source.size != candidate.size:
            return None, (source.size, candidate.size)
        delta = ImageChops.difference(source.convert('RGB'), candidate.convert('RGB'))
        r, g, b = delta.split()
        maximum = ImageChops.lighter(ImageChops.lighter(r, g), b)
        return source.width * source.height - maximum.histogram()[0], maximum.getbbox()


def screenshots(root):
    print('| Case | Scene | Changed pixels | Bounds |')
    print('| --- | --- | ---: | --- |')
    for case in CASES:
        for scene in SCENES:
            before, after = (root / 'shots' / run / case / f'{scene}.png' for run in ('before', 'after'))
            if not before.is_file() or not after.is_file():
                print(f'| {case} | {scene} | missing | |')
                continue
            count, bounds = changed_pixels(before, after)
            print(f'| {case} | {scene} | {count} | {bounds or ""} |')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path, nargs='?', default=Path('D:/dp-dev/tmp/pageteardown'))
    args = parser.parse_args()
    measurement(args.root)
    print()
    screenshots(args.root)
