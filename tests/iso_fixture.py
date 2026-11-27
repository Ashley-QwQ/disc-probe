"""Record a successful self-check for byte fixtures used with fake recorders."""

from pathlib import Path

def write_checked_iso(path, data):
    from discprobe.image_output import mark_checked
    image = Path(path)
    image.write_bytes(data)
    mark_checked(image, [])
    return image
