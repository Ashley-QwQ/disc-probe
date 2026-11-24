"""Python access to the shared test browser launcher."""
import json
from pathlib import Path
import subprocess


def run_browser(profile, args, *, executable=None, timeout, disable_gpu=False, check=False):
    launcher = Path(__file__).resolve().parents[1] / "tests" / "browser.mjs"
    request = json.dumps({
        "explicit": str(executable) if executable else None,
        "profile": str(profile),
        "args": args,
        "timeout": int(timeout * 1000),
        "disableGpu": disable_gpu,
    })
    return subprocess.run(
        ["node", str(launcher)], input=request.encode("utf-8"),
        capture_output=True, check=check,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
