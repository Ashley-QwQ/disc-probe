"""Compare existing image, info and burn outputs before and after adding gratingcard."""
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))


def child():
    from discprobe import burner, iso9660

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            date = cls(2026,11,21,12,tzinfo=timezone.utc)
            return date.astimezone(tz) if tz is not None else date.replace(tzinfo=None)

    path = Path(sys.argv[2])
    module = dict(__name__='discprobe.__main__', __package__='discprobe',
                  __file__=str(REPO/'discprobe/__main__.py'))
    exec(compile(path.read_bytes(),str(path),'exec'),module)
    module['datetime'] = SimpleNamespace(datetime=Frozen)
    iso9660.datetime = SimpleNamespace(datetime=Frozen,timezone=timezone)
    burner.time = SimpleNamespace(monotonic=lambda:100.,time=lambda:1795262400.)
    module['main'](sys.argv[3:])


def compare(root, base):
    from disclab.__main__ import lab_env
    from disclab.box import make_box
    from disclab.lab import Lab
    from discprobe.imagedisc import SECTOR_BITS

    root.mkdir(parents=True, exist_ok=True)
    old = root/'source-before.py'
    old.write_bytes(subprocess.check_output(['git','show',base+':discprobe/__main__.py'],cwd=REPO))
    out, prior, contrasts = root/'legacy-lab', {}, []
    assert out.resolve().parent == root.resolve() and not out.exists()
    for variant, source in [('before',old),('after',REPO/'discprobe/__main__.py')]:
        for lang in ('zh','en'):
            lab = Lab(out)
            make_box(lab,'dvd+r',1,seed=178)
            with lab.locked_state() as state:
                state['drives']['X:']['tray'] = lab.box()['discs'][0]
            try:
                u, b = 180518.44,133.3
                v = math.pi*((58.6/(b*1e-6))**2-u*u)/(8192*SECTOR_BITS)
                geo = dict(fit=dict(u=u,v=v,bit_nm_assumed=b,measured_span_mm=[24,58.6]))
                (out/'geometry.json').write_text(json.dumps(geo),encoding='utf-8')
                image = out/'iso/grid.iso'
                commands = [
                    ('image-help',('image','--help')),
                    ('burn-help',('burn','--help')),
                    ('info-help',('info','--help')),
                    ('image',('image','--geo','geometry.json')),
                    ('burn',('burn','--drive','X:','--iso',str(image),'--speed','8','--yes-write')),
                    ('info',('info','--drive','X:')),
                ]
                env = dict(lab_env(lab),DISCPROBE_HOME=str(out),DISCLAB_BURN_TIME='quick',
                           DISCPROBE_WORKERS='1',PYTHONHASHSEED='0')
                for name, args in commands:
                    proc = subprocess.run([sys.executable,'-B','-X','utf8',__file__,'--child',str(source),
                                           '--lang',lang,*args],cwd=out,env=env,capture_output=True,timeout=60)
                    (root/f'{variant}-{lang}-{name}.stdout').write_bytes(proc.stdout)
                    (root/f'{variant}-{lang}-{name}.stderr').write_bytes(proc.stderr)
                    proc.check_returncode()
                    image_hash = hashlib.sha256(image.read_bytes()).hexdigest() if name == 'image' else None
                    signature = (proc.stdout,proc.stderr,image_hash)
                    key = name,lang
                    if variant == 'before':
                        prior[key] = signature
                    else:
                        contrasts.append(dict(command=name,lang=lang,equal=signature == prior[key],
                                              stdout_bytes=len(proc.stdout),stderr_bytes=len(proc.stderr),
                                              iso_sha256=image_hash))
            finally:
                assert out.resolve().parent == root.resolve()
                shutil.rmtree(out)
    print(json.dumps(contrasts,indent=2))
    assert all(row['equal'] for row in contrasts)


if __name__ == '__main__':
    if sys.argv[1] == '--child':
        child()
    else:
        compare(Path(sys.argv[1]).resolve(),sys.argv[2])
