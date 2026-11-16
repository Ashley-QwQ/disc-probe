"""Make auditable trial renderers from the supplied x79 scripts; originals stay intact."""
from pathlib import Path
import json
import shutil
import os

ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / 'tools/night_lobby'
TRIAL = Path(os.environ.get('LOBBY_TRIAL', 'F:/dp-archive/tmp/lobbypool/trial2'))
GAIN = float(os.environ.get('LOBBY_GAIN', '5.8'))
SIGMA_SCALE = float(os.environ.get('LOBBY_SIGMA_SCALE', '1.0'))
SOURCE = Path('F:/dp-archive/tmp/lobbypool/x79stage/stage')


def replace_once(text, before, after):
    assert text.count(before) == 1, before
    return text.replace(before, after)


for name in ('render_fax_nightb.py', 'render_round5_nightb.py'):
    text = (SOURCE / name).read_text(encoding='utf-8')
    text = replace_once(text, 'FORCE = "--force" in argv',
        'FORCE = "--force" in argv\n'
        f'NIGHT_GAIN = float(arg("--night-gain", "{GAIN}"))\n'
        f'NIGHT_SIGMA_SCALE = float(arg("--night-sigma-scale", "{SIGMA_SCALE}"))')
    text = replace_once(text,
        'amb=(0.9, 0.9, 0.9), gain=(1.6, 1.4, 1.1), add=(0.035, 0.018, 0.004)',
        'amb=(0.64, 0.64, 0.64), gain=(NIGHT_GAIN,) * 3, add=(0.0, 0.0, 0.0)')
    text = replace_once(text,
        'amb=(0.8, 0.8, 0.8), gain=(2.0, 1.75, 1.35), add=(0.05, 0.028, 0.006)',
        'amb=(0.64, 0.64, 0.64), gain=(NIGHT_GAIN,) * 3, add=(0.0, 0.0, 0.0)')
    text = replace_once(text, 'pooled_lamp(nt, color, is_top, st), v)',
                        'pooled_lamp(nt, color, is_top, st, v), v)')
    text = replace_once(text, 'def pooled_lamp(nt, color, is_top, st):',
                        'def pooled_lamp(nt, color, is_top, st, v):')
    text = replace_once(text, 'k.inputs[1].default_value = -1.0 / (2.0 * POOL["sigma"] ** 2)',
        '# Card T review 2: original width by default; paper and lines stay unchanged.\n'
        '    sigma = POOL["sigma"] * (NIGHT_SIGMA_SCALE if v == "dark" else 1.0)\n'
        '    k.inputs[1].default_value = -1.0 / (2.0 * sigma ** 2)')
    # CPU is an explicit branch, not an invalid enum followed by incidental fallback.
    begin = text.index('try:\n    prefs = bpy.context.preferences.addons["cycles"].preferences')
    end = text.index('if scene.world is None:', begin)
    old = text[begin:end]
    text = text[:begin] + 'if DEVICE == "CPU":\n    cyc.device = "CPU"\nelse:\n' + ''.join(
        '    ' + line if line.strip() else line for line in old.splitlines(True)) + text[end:]
    text = replace_once(text, 'info["ss"], info["samples"] = SS, SAMPLES',
        'info["ss"], info["samples"] = SS, SAMPLES\n'
        '    info["night_pool_trial"] = {"amb": 0.64, "gain": NIGHT_GAIN, "add": 0,\n'
        '                                "sigma_scale_dark": NIGHT_SIGMA_SCALE, "sigma_original": POOL["sigma"],\n'
        '                                "sigma_dark": POOL["sigma"] * NIGHT_SIGMA_SCALE,\n'
        '                                "paper_and_lines_unchanged": True, "device": cyc.device}')
    (DEST / name).write_text(text, encoding='utf-8')
    shutil.copyfile(DEST / name, TRIAL / 'stage' / name)
for name in ('night_b_palette.py', 'glow_review.json'):
    shutil.copyfile(SOURCE / name, DEST / name)
    shutil.copyfile(SOURCE / name, TRIAL / 'stage' / name)
print('Prepared both renderers; only the fax base trial will run.')
