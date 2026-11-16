"""Zero-filled timing/capacity fixtures without allocating the whole image on Windows."""
import os
from pathlib import Path
import subprocess
import sys


def zero_file(path, size):
    path=Path(path)
    path.touch()
    if sys.platform=='win32':
        subprocess.run(['fsutil','sparse','setflag',str(path)],check=True,capture_output=True)
    with path.open('r+b') as stream:
        if sys.platform!='win32':
            stream.truncate(size)
            return
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
