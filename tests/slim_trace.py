"""Run a SciPy-free pack's checks and trace Python modules plus Windows DLLs.

The runner and pytest live outside the distributable. Child interpreters get
the same tracer and explicit isolation. This file never opens a drive.
"""
from __future__ import annotations
import argparse
import atexit
import ctypes
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys


def dlls():
    if os.name != 'nt':
        return []
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    psapi = ctypes.WinDLL('psapi', use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    proc = kernel.GetCurrentProcess()
    handles = (wintypes.HMODULE * 4096)()
    needed = wintypes.DWORD()
    psapi.EnumProcessModulesEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), wintypes.DWORD]
    psapi.GetModuleFileNameExW.argtypes = [wintypes.HANDLE, wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
    if not psapi.EnumProcessModulesEx(proc, handles, ctypes.sizeof(handles), ctypes.byref(needed), 3):
        raise ctypes.WinError(ctypes.get_last_error())
    result = []
    for handle in handles[:needed.value // ctypes.sizeof(wintypes.HMODULE)]:
        buf = ctypes.create_unicode_buffer(32768)
        if psapi.GetModuleFileNameExW(proc, handle, buf, len(buf)):
            result.append(buf.value)
    return sorted(result)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', required=True)
    ap.add_argument('--output', required=True)
    ap.add_argument('--deps')
    ap.add_argument('--mode', choices=('selftest', 'pytest', 'child'), default='selftest')
    ap.add_argument('args', nargs=argparse.REMAINDER)
    a = ap.parse_args()
    root, output = Path(a.root).resolve(), Path(a.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    os.chdir(root)
    os.environ['OPENBLAS_NUM_THREADS'] = '1'
    os.environ['OMP_NUM_THREADS'] = '1'
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    os.environ['PYTHONPATH'] = str(root)
    if os.name == 'nt':
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)
    sys.path[:0] = [str(root), str(root / 'tests')]
    if a.deps:
        sys.path.append(str(Path(a.deps).resolve()))
    # The embedded _pth omits all host site-packages. Verify the actual absence.
    import importlib.util
    if importlib.util.find_spec('scipy') is not None:
        raise RuntimeError('SciPy must be physically absent from this environment')
    try:
        __import__('scipy')
    except ModuleNotFoundError:
        pass
    else:
        raise AssertionError('SciPy unexpectedly imports')
    def save():
        data = dict(pid=os.getpid(), mode=a.mode, executable=sys.executable,
                    modules={name: str(getattr(module, '__file__', 'built-in')) for name, module in sorted(sys.modules.items())},
                    dlls=dlls(), scipy_absent=True)
        (output / f'{os.getpid()}.json').write_text(json.dumps(data, indent=2), encoding='utf-8')
    atexit.register(save)
    original = subprocess.Popen
    runner = str(Path(__file__).resolve())
    class TracedPopen(original):
        def __init__(self, args, *rest, **kwargs):
            if isinstance(args, (list, tuple)) and os.path.normcase(str(args[0])) == os.path.normcase(sys.executable):
                command = list(args[1:])
                args = [sys.executable, '-I', '-X', 'utf8', '-B', runner, '--root', str(root), '--output', str(output), '--mode', 'child', '--', *command]
                # Preserve the intended working directory of tests' children.
                env = dict(kwargs.get('env') or os.environ)
                env['SLIM_CHILD_CWD'] = str(Path(kwargs.get('cwd') or os.getcwd()).resolve())
                kwargs['env'] = env
            super().__init__(args, *rest, **kwargs)
    subprocess.Popen = TracedPopen
    if a.mode == 'selftest':
        sys.argv = ['discprobe', 'selftest']
        runpy.run_module('discprobe', run_name='__main__')
    elif a.mode == 'pytest':
        import pytest
        os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
        raise SystemExit(pytest.main(['-q', str(root / 'tests'), str(root / 'tests/scipy_oracle_checks.py'), '-p', 'no:cacheprovider', '--ignore=' + str(root / 'tests/slim_artifacts')]))
    else:
        command = a.args
        if command[:1] == ['--']:
            command = command[1:]
        os.chdir(os.environ.get('SLIM_CHILD_CWD', str(root)))
        while command and command[0] in ('-I', '-P', '-B', '-u'):
            command.pop(0)
        if command[:2] == ['-X', 'utf8']:
            del command[:2]
            while command and command[0] in ('-I', '-P', '-B', '-u'):
                command.pop(0)
        if command[:1] == ['-c']:
            sys.argv = ['-c', *command[2:]]
            exec(compile(command[1], '<string>', 'exec'), {'__name__': '__main__'})
        elif command[:1] == ['-m']:
            sys.argv = command[1:]
            runpy.run_module(command[1], run_name='__main__')
        else:
            sys.argv = command
            runpy.run_path(command[0], run_name='__main__')


if __name__ == '__main__':
    main()
