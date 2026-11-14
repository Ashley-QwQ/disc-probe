"""disclab: a standalone virtual test bench for a matching disc-probe release.

A lab is a folder that holds a box of made-up discs, the drives they go into, what was burned on each,
and an answer file with every true parameter. disc-probe itself never reads the answer file: it only sees
SCSI replies from a virtual drive (see `boot/sitecustomize.py`), the files it writes, and photos rendered
from the true geometry.

    python -m disclab box --lab LAB --media dvd-r --count 12 --seed 1
    python -m disclab loop geo --lab LAB
    python -m disclab loop photo --lab LAB      # geo -> target -> photos -> L -> picture
"""
