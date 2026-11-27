"""Offline, read-only input discovery and isolated process helpers."""
from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / 'tests' / 'slim_artifacts'


def allowed(path):
    return not any('b' + 'lind' in part.casefold() for part in Path(path).parts)


def walk(root):
    root = Path(root)
    if not allowed(root) or not root.is_dir():
        return
    for folder, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if allowed(Path(folder) / d) and d not in ('.git', '__pycache__'))
        for name in sorted(files):
            path = Path(folder) / name
            if allowed(path):
                yield path


def low_priority():
    if os.name == 'nt':
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)
    os.environ['OPENBLAS_NUM_THREADS'] = '1'
    os.environ['OMP_NUM_THREADS'] = '1'


def isolated_children():
    """Apply the task's isolation rule to legacy tests' Python subprocesses too."""
    original = subprocess.Popen
    class IsolatedPopen(original):
        def __init__(self, args, *rest, **kwargs):
            if isinstance(args, (list, tuple)) and os.path.normcase(str(args[0])) == os.path.normcase(sys.executable):
                args = list(args)
                if '-I' not in args and '-P' not in args:
                    args.insert(1, '-P')
                env = dict(kwargs.get('env') or os.environ)
                env['PYTHONPATH'] = str(ROOT)  # explicit path, never the process working directory
                env['PYTHONDONTWRITEBYTECODE'] = '1'
                kwargs['env'] = env
            super().__init__(args, *rest, **kwargs)
    subprocess.Popen = IsolatedPopen

