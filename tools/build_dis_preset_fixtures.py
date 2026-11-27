"""Rebuild the 51 offline interchange fixtures from read-only study sources.

Run from repository root; only tests/data/dis-presets is written.
"""
import copy
import json
from pathlib import Path


def main():
    builtin = json.loads(Path('D:/dis-study/DiscImageStudio/src/DiscImageStudio.Core/Presets/built-in-disc-presets.json').read_text(encoding='utf-8'))
    community = json.loads(Path('D:/disc-probe/data/community-calibrations/dis-github.json').read_text(encoding='utf-8'))
    root = Path('tests/data/dis-presets')
    root.mkdir(parents=True, exist_ok=True)
    cases = []

    def add(name, data, reason, source, valid=True, media=None):
        cases.append((name, data, reason, source, valid, media))

    def catalog(media, items, schema=4):
        d = dict(schemaVersion=schema, cdPresets=[], dvdPresets=[])
        if schema == 4:
            d['bluRayPresets'] = []
        d[{'cd': 'cdPresets', 'dvd': 'dvdPresets', 'bd': 'bluRayPresets'}[media]] = items
        return d

    dvd, cd, bd = (copy.deepcopy(builtin[k][0]) for k in ['dvdPresets', 'cdPresets', 'bluRayPresets'])
    # Source-exact catalog entries (not fabricated measurements).
    for media, key, indexes in [('cd', 'cdPresets', [0, 1, 2, 3]), ('dvd', 'dvdPresets', [0, 1, 2, 3, 4, 5]), ('bd', 'bluRayPresets', [0, 1, 2, 3])]:
        for i in indexes:
            p = builtin[key][i]
            add(f'builtin-{media}-{i}', catalog(media, [p]), 'Source-exact built-in entry ' + p['id'], f'619ec75:{key}[{i}]')
    for i in [0, 1, 2, 3, 4, 5]:
        e = community['entries'][i]
        p = {**e['parameters'], 'id': e['id'], 'displayName': e['disc'].get('brand') or e['id'],
             'description': 'Community starting point ' + e['source_url']}
        complete = type(p.get('sectors', p.get('totalSectors'))) is int
        add(f'community-{i}', catalog(e['media'], [p]),
            'Posted fields retained; calibration unverified' if complete else 'Incomplete posted parameters: missing sector count refused without inventing capacity',
            e['id'] + ' ' + e['source_url'], valid=complete)

    def variant(name, changes, reason, base=dvd, media='dvd', valid=True, remove=()):
        p = copy.deepcopy(base); p.update(changes)
        for k in remove: p.pop(k, None)
        add(name, catalog(media, [p]), reason, f'619ec75:{base["id"]}, synthetic mutation', valid)

    variant('chinese-name', {'displayName': '我的盘片：第二桶'}, 'Chinese custom name')
    variant('emoji-name', {'id': '../CON:盘💿', 'displayName': '盘 💿 <script>& " odd'}, 'Path-like id, emoji and HTML text stay data')
    variant('mid-present', {'mid': 'MCC 004'}, 'Nonstandard MID extension retained, DIS install refused')
    variant('mid-absent', {}, 'MID stays unknown')
    variant('pitch-absent', {}, 'Missing coefficients default to zero', remove=('pitchLinear', 'pitchQuadratic', 'pitchCubic'))
    variant('pitch-zero', dict(pitchLinear=0, pitchQuadratic=0, pitchCubic=0), 'Explicit zeros preserved')
    variant('pitch-linear', dict(pitchLinear=.001), 'Positive variable pitch; bounded DP angle conversion')
    variant('pitch-cubic', dict(pitchLinear=.002, pitchQuadratic=-.003, pitchCubic=.001), 'Cubic pitch model')
    variant('dvd-odd-sectors', dict(totalSectors=2295103), 'DIS permits odd DVD geometry capacity', remove=('usableSectors',))
    variant('cd-rw', dict(displayName='CD-RW 74 min', sectors=333001, usableSectors=333000), 'CD-RW and odd CD capacity', base=cd, media='cd')
    variant('dvd-plus-rw', dict(displayName='DVD+RW', totalSectors=2295104), 'Rewritable DVD+RW label')
    variant('dvd-minus-rw', dict(displayName='DVD-RW'), 'DVD-RW label')
    variant('unknown-field', {'futureGeometry': {'order': 4, 'coefficients': [1, 2]}}, 'Unknown future field preserved, geometry/install refused')
    variant('resource-null', {'displayNameResourceKey': None, 'contributor': None}, 'Nullable optional resource/contributor')
    variant('cd-legacy-speed', {'linearVelocityMmPerSecond': 1400}, 'Stored compatibility speed retained; generation fixed at 1200', base=cd, media='cd')
    variant('dvd-legacy-bit', {'channelBitLengthNm': 150}, 'Stored compatibility bit length retained; generation fixed at 133.3')
    variant('bd-pitch', {'pitchLinear': .0002, 'invertMapping': True}, 'BD variable pitch and polarity', base=bd, media='bd')
    add('single-preset', dvd, 'One standalone DVD preset', '619ec75:dvdPresets[0]')
    add('dp-wrapper', dict(preset=cd, fit={}, source={}), 'Existing DP export wrapper', '619ec75:cdPresets[0]')
    add('schema-2', catalog('dvd', [dvd], 2), 'Old schema supported by v1.5.0 and current reader', '29b8cc1:DiscPresetJsonStore schema 2')
    add('schema-3', catalog('cd', [{k:v for k,v in cd.items() if k != 'linearVelocityMmPerSecond'}], 3), 'Interim schema missing compatibility speed', '29b8cc1:DiscPresetJsonStore schema 3')
    add('duplicate-ids', catalog('dvd', [dvd, {**dvd, 'outerRadiusMm': 57.99}]), 'Duplicate ids reported; index selection; never overwrite', '619ec75:dvdPresets[0], synthetic duplicate')
    disabled = catalog('cd', [cd]); disabled['disabledCdPresetIds'] = [cd['id']]
    add('disabled', disabled, 'Disabled entry is unchecked by default', '619ec75:cdPresets[0]')
    add('whole-catalog', builtin, 'Whole catalog, all three media and resource keys', '619ec75:built-in-disc-presets.json')
    add('bad-json', '{"schemaVersion": 4,', 'Truncated JSON is refused', 'synthetic broken JSON', False)
    variant('wrong-type', {'innerRadiusMm': '24'}, 'String radius refused', valid=False)
    variant('negative-radius', {'innerRadiusMm': -24}, 'Out-of-range radius refused', valid=False)
    variant('bad-pitch', {'pitchLinear': -2}, 'Nonpositive pitch inside interval refused', valid=False)
    variant('bd-odd', {'totalSectors': 12219391}, 'BD must be 32-sector aligned', base=bd, media='bd', valid=False)
    add('future-schema', {**catalog('dvd', [dvd]), 'schemaVersion': 99}, 'Unknown schema refused without guessing geometry', 'synthetic schema', False)
    variant('unwrapped-over360', dict(id='synthetic-unwrapped-over360', displayName='Synthetic extreme pitch', pitchLinear=1e8),
            'Corrected unwrapped error >360 degrees; archive only, no DP image use')
    assert len(cases) == 51, len(cases)
    lines = ['# DIS interchange fixtures', '', '51 mock files. Built-in values come from the read-only DIS checkout at `619ec75`;',
             'community values come from `D:/disc-probe/data/community-calibrations/dis-github.json` (174 entries, collected 2026-11-10).',
             'Variants are synthetic edge cases, not new measurements. DVD±R and CD-R examples retain source names.',
             'Old schemas are the schema 2/3 formats still supported at v1.5.0 (`29b8cc1`); schema 4 also already existed in that release.',
             'Regenerate with `python tools/build_dis_preset_fixtures.py` when those local sources exist.', '',
             '| File | Expected | Coverage | Source |', '|---|---|---|---|']
    for i, (name, data, reason, source, valid, media) in enumerate(cases, 1):
        filename = f'{i:02d}-{name}.json'
        text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
        (root / filename).write_text(text, encoding='utf-8')
        lines.append(f'| {filename} | {"parse" if valid else "refuse"} | {reason} | {source} |')
    (root / 'README.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
