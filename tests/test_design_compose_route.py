"""The design page's export route: /api/compose says which textures the composed design really uses, so the page
can refuse a black-and-white burn file that would carry a colour texture; and it takes a multi-photo work."""
import base64

import numpy as np

from discprobe import editor_ops as E
from discprobe import webui


def ring_work(fill_spec):
    mg = E.grid(96)
    mask = E.selection(dict(tool="ring", inner=31, outer=45), mg)
    return dict(version=2, format="disc-probe design", media="dvd", cell=.02, layers=[], maskGrid=mg,
                materials=[dict(id="background", spec="B9"), dict(id="dark", spec="A5"), dict(id="red", spec=fill_spec, period_um=1.8)],
                selections=[dict(id="ring", name="ring", bits=base64.b64encode(mask).decode())],
                assignments=[dict(id="a", selection="ring", material="red")])


def test_textures_used_names_only_the_labels_on_the_disc(tmp_path):
    backend = webui.Backend(tmp_path, drive_provider=lambda: [])
    colour = backend.compose_document(ring_work("92"))
    assert colour["textures"] == ["B9", "A5", "92"]
    assert colour["textures_used"] == ["92", "B9"]          # A5 is listed but nothing is dark
    # the page's black-and-white mapping: every material but the background becomes the dark texture
    plain = backend.compose_document(ring_work("A5"))
    assert plain["textures_used"] == ["A5", "B9"]
    labels = np.load(tmp_path / plain["design_npy"], mmap_mode="r")
    assert labels.shape == (6000, 6000)


def test_textures_used_reads_in_bands(tmp_path):
    npy = tmp_path / "d.npy"
    a = np.zeros((2500, 2500), np.uint8)
    a[2400, 7] = 3                                          # past the first band
    np.save(npy, a)
    assert webui.Backend._textures_used(npy, ["b9", "A5", "66", "e4"]) == ["B9", "E4"]


def test_compose_takes_a_multi_photo_work():
    # three 2048 x 2048 RGBA layers in base64 are already over 64 MiB; sixteen fit
    one = 4 * (2048 * 2048 * 4 + 2) // 3
    assert 3 * one > 64 * 2 ** 20
    assert 16 * one < webui.COMPOSE_BYTES
