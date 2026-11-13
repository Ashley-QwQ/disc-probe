"""disclab: a developer test bench for disc-probe. Not part of any release package.

A lab is a folder that holds a box of made-up discs, the drives they go into, what was burned on each,
and an answer file with every true parameter. disc-probe itself never reads the answer file: it only sees
SCSI replies from a virtual drive (see `boot/sitecustomize.py`), the files it writes, and photos rendered
from the true geometry.

    python -m disclab box --lab LAB --media dvd-r --count 12 --seed 1
    python -m disclab loop --lab LAB            # random disc -> geo -> target -> photos -> L -> picture
    python -m disclab score --lab LAB
"""
