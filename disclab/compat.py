"""The exact disc-probe release this Disc Lab snapshot was tested against."""
from importlib import import_module

REQUIRED_DISCPROBE_VERSION = "0.1.2.1"


def require_discprobe():
    try:
        version = import_module("discprobe.version").__version__
    except (ImportError, AttributeError):
        raise SystemExit(
            f"Disc Lab requires disc-probe {REQUIRED_DISCPROBE_VERSION}; install its wheel "
            "or place disclab beside the matching discprobe folder."
        ) from None
    if version != REQUIRED_DISCPROBE_VERSION:
        raise SystemExit(
            f"Disc Lab requires disc-probe {REQUIRED_DISCPROBE_VERSION}, but found {version}; "
            "the version strings must be equal, including any pre-release tag."
        )

