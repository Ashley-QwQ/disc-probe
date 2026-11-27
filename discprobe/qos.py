"""Keep disc-probe's processes off Windows' power-saving schedule.

Windows 11 can put a process it thinks is in the background under EcoQoS: it runs on the efficiency
cores at low clocks. Jobs started from the web page have no window of their own, so Windows may take
them for background work, and building a preview or an image then runs several times slower. A process
can opt out for itself; every disc-probe process (the command line, the web server, its jobs and their
worker processes) does so as it starts. Nothing measured or written depends on it."""

import sys

PROCESS_POWER_THROTTLING = 4                 # PROCESS_INFORMATION_CLASS ProcessPowerThrottling
EXECUTION_SPEED = 0x1                        # PROCESS_POWER_THROTTLING_EXECUTION_SPEED
IGNORE_TIMER_RESOLUTION = 0x4                # PROCESS_POWER_THROTTLING_IGNORE_TIMER_RESOLUTION (Windows 11)


def _state_type():
    import ctypes
    from ctypes import wintypes

    class State(ctypes.Structure):
        _fields_ = [("Version", wintypes.ULONG), ("ControlMask", wintypes.ULONG), ("StateMask", wintypes.ULONG)]
    return State


def keep_full_speed() -> bool:
    """Ask Windows never to throttle this process (EcoQoS) and to honour its timer requests.
    Returns False where the request is not available (other systems, Windows before 10 1709)."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        set_info = k.SetProcessInformation
    except (OSError, AttributeError):
        return False
    set_info.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    set_info.restype = wintypes.BOOL
    k.GetCurrentProcess.restype = wintypes.HANDLE
    State = _state_type()
    # Control a bit and leave its state bit clear = "never throttle". Windows 10 does not know the timer
    # bit and refuses the whole request, so it falls back to the speed bit alone.
    for mask in (EXECUTION_SPEED | IGNORE_TIMER_RESOLUTION, EXECUTION_SPEED):
        state = State(1, mask, 0)
        if set_info(k.GetCurrentProcess(), PROCESS_POWER_THROTTLING, ctypes.byref(state), ctypes.sizeof(state)):
            return True
    return False


def throttling_state():
    """(ControlMask, StateMask) as Windows reports them for this process, or None."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    get_info = getattr(k, "GetProcessInformation", None)
    if get_info is None:
        return None
    get_info.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    get_info.restype = wintypes.BOOL
    k.GetCurrentProcess.restype = wintypes.HANDLE
    state = _state_type()(1, 0, 0)
    if not get_info(k.GetCurrentProcess(), PROCESS_POWER_THROTTLING, ctypes.byref(state), ctypes.sizeof(state)):
        return None
    return state.ControlMask, state.StateMask
