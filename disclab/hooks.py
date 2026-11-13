"""Module patches applied by boot/sitecustomize.py when DISCPROBE_DISCLAB names a lab folder."""
from __future__ import annotations

from .lab import Lab


def _lab():
    return Lab.from_env()


def lab_drives() -> list[str]:
    lab = _lab()
    if lab is None or not lab.state_path.exists():
        return []
    return sorted(lab.state().get("drives", {}))


def is_lab_drive(name) -> bool:
    lab = _lab()
    return bool(lab and isinstance(name, str) and lab.drive_for(name) is not None)


def patch(module):
    name = module.__name__
    if name in ("discprobe.spti", "discprobe.sg", "discprobe.imapi"):
        attr = {"discprobe.spti": "SptiDevice", "discprobe.sg": "SgDevice", "discprobe.imapi": "ImapiDevice"}[name]
        real = getattr(module, attr)

        def device(drive, *args, _real=real, **kwargs):
            if is_lab_drive(drive):
                from .drive import LabDrive
                return LabDrive(_lab(), drive)
            raise OSError(f"disclab: {drive!r} is not a lab drive; real drives are off in a lab process")
        device.real = real
        setattr(module, attr, device)
        if hasattr(module, "list_optical_drives"):
            real_list = module.list_optical_drives

            def list_optical_drives(_real=real_list):
                # Only lab drives: a lab process never touches a real optical drive.
                return lab_drives()
            module.list_optical_drives = list_optical_drives
    elif name == "discprobe.burner":
        real_adapter = module.adapter

        def adapter(drive, media, _real=real_adapter):
            if is_lab_drive(drive):
                from .drive import LabRecorder
                return LabRecorder(_lab(), drive, media)
            raise module.BurnError("disclab: only lab drives can be burned in a lab process")
        module.adapter = adapter
