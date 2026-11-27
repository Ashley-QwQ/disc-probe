"""Isolated Disc Lab practice; never enumerates physical drives."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
root=Path(sys.argv[1]).resolve()
from disclab.lab import Lab
from discprobe.image_output import mark_checked

if '--short' in sys.argv:
    # A separate, explicit media fixture: Lab's user-cancel path does not retain partial writes.
    lab=Lab(root)
    with lab.locked_state() as state:
        disc=state['drives']['X:']['tray']
        iso=root/'iso/stop.iso'
        state.setdefault('burns',{})[disc]=dict(closed=True,sessions=[dict(
            iso=str(iso),iso_size=iso.stat().st_size,iso_mtime=iso.stat().st_mtime,
            start_lba=0,sectors=576,speed_x=4,writer='imapi',mode='dvd',drive='X:',
            write_offset_bits=0,low_speed_fail_mm=None)])
    raise SystemExit(0)

from disclab.practice import prepare
media=os.environ.get('RW_DISC_TEST_MEDIA','dvd-r')
prepare(root,media)
iso=root/'iso/stop.iso';iso.parent.mkdir(exist_ok=True)
iso.touch()
if sys.platform=='win32':
    subprocess.run(['fsutil','sparse','setflag',str(iso)],check=True,capture_output=True)
with iso.open('r+b') as stream:
    size=524288*2048  # Sparse timing fixture, not a measurement image.
    if sys.platform=='win32':
        # CRT truncate fills the extension with allocated zeros, even on a sparse file.
        import ctypes
        from ctypes import wintypes
        import msvcrt
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.SetFilePointerEx.argtypes=[wintypes.HANDLE,ctypes.c_longlong,ctypes.c_void_p,wintypes.DWORD]
        kernel.SetFilePointerEx.restype=wintypes.BOOL
        kernel.SetEndOfFile.argtypes=[wintypes.HANDLE]
        kernel.SetEndOfFile.restype=wintypes.BOOL
        handle=msvcrt.get_osfhandle(stream.fileno())
        if not kernel.SetFilePointerEx(handle,size,None,0) or not kernel.SetEndOfFile(handle):
            raise ctypes.WinError(ctypes.get_last_error())
    else:
        stream.truncate(size)
mark_checked(iso, [])
with socket.socket() as sock:
    sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
(root/'ready.json').write_text(json.dumps(dict(port=port)),encoding='utf-8')
env=dict(os.environ,TEMP=str(root.parent),TMP=str(root.parent),DISCPROBE_HOME=str(root))
# The practice process installs Disc Lab's virtual drive provider.
env.pop("DISC_PROBE_NO_DRIVES", None)
raise SystemExit(subprocess.call([sys.executable,'-X','utf8','-B','-m','disclab','practice',
    '--media',media,'--burn-time','0.3','--lab',str(root),'--port',str(port)],cwd=ROOT,env=env))
