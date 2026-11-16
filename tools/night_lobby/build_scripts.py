"""Make auditable trial renderers from the supplied x79 scripts; originals stay intact."""
from pathlib import Path
import json
import shutil

ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / 'tools/night_lobby'
TRIAL = Path('F:/dp-archive/tmp/lobbypool/trial')
SOURCE = Path('F:/dp-archive/tmp/lobbypool/x79stage/stage')


def replace_once(text, before, after):
    assert text.count(before) == 1, before
    return text.replace(before, after)


for name in ('render_fax_nightb.py', 'render_round5_nightb.py'):
    text = (SOURCE / name).read_text(encoding='utf-8')
    text = replace_once(text,
        'amb=(0.9, 0.9, 0.9), gain=(1.6, 1.4, 1.1), add=(0.035, 0.018, 0.004)',
        'amb=(0.64, 0.64, 0.64), gain=(2.4, 2.4, 2.4), add=(0.0, 0.0, 0.0)')
    text = replace_once(text,
        'amb=(0.8, 0.8, 0.8), gain=(2.0, 1.75, 1.35), add=(0.05, 0.028, 0.006)',
        'amb=(0.64, 0.64, 0.64), gain=(2.4, 2.4, 2.4), add=(0.0, 0.0, 0.0)')
    text = replace_once(text, 'pooled_lamp(nt, color, is_top, st), v)',
                        'pooled_lamp(nt, color, is_top, st, v), v)')
    text = replace_once(text, 'def pooled_lamp(nt, color, is_top, st):',
                        'def pooled_lamp(nt, color, is_top, st, v):')
    text = replace_once(text, 'k.inputs[1].default_value = -1.0 / (2.0 * POOL["sigma"] ** 2)',
        '# Card T: narrow only the night pool, including segment distance. Paper and lines stay unchanged.\n'
        '    sigma = POOL["sigma"] * (0.557 if v == "dark" else 1.0)\n'
        '    k.inputs[1].default_value = -1.0 / (2.0 * sigma ** 2)')
    # CPU is an explicit branch, not an invalid enum followed by incidental fallback.
    begin = text.index('try:\n    prefs = bpy.context.preferences.addons["cycles"].preferences')
    end = text.index('if scene.world is None:', begin)
    old = text[begin:end]
    text = text[:begin] + 'if DEVICE == "CPU":\n    cyc.device = "CPU"\nelse:\n' + ''.join(
        '    ' + line if line.strip() else line for line in old.splitlines(True)) + text[end:]
    text = replace_once(text, 'info["ss"], info["samples"] = SS, SAMPLES',
        'info["ss"], info["samples"] = SS, SAMPLES\n'
        '    info["night_pool_trial"] = {"amb": 0.64, "gain": 2.4, "add": 0,\n'
        '                                "sigma_scale_dark": 0.557, "sigma_original": POOL["sigma"],\n'
        '                                "sigma_dark": POOL["sigma"] * 0.557,\n'
        '                                "paper_and_lines_unchanged": True, "device": cyc.device}')
    (DEST / name).write_text(text, encoding='utf-8')
    shutil.copyfile(DEST / name, TRIAL / 'stage' / name)
for name in ('night_b_palette.py', 'glow_review.json'):
    shutil.copyfile(SOURCE / name, DEST / name)
print('Prepared both renderers; only the fax base trial will run.')
