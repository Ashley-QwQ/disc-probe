"""Designs at 20, 10 and 5 um cells: the cell size is the array's, and finer cells sample the same disc."""
import numpy as np

from discprobe import cdimage, imagedisc

U, V, BIT_MM = 9500.0, 0.000555, 0.267e-3


def _coarse():
    # blocks of 0.2 mm, so cell edges at 20 um are edges at 10 and 5 um too
    rng = np.random.default_rng(4)
    return np.repeat(np.repeat(rng.random((600, 600)) < 0.5, 10, 0), 10, 1)


def _finer(design, k):
    return np.repeat(np.repeat(design, k, 0), k, 1)


def test_sides_and_checks():
    coarse = _coarse()
    assert imagedisc.check_cells(coarse) == 20
    assert imagedisc.check_cells(_finer(coarse, 2)) == 10
    assert abs(imagedisc.cell_mm(_finer(coarse, 2)) - 0.01) < 1e-12
    for design, cell_um in ((_finer(coarse, 2), 20), (np.zeros((7000, 7000), bool), None)):
        try:
            imagedisc.check_cells(design, cell_um)
        except ValueError:
            continue
        raise AssertionError("a design of the wrong size or cell was accepted")


def test_finer_copy_of_a_design_samples_the_same():
    coarse = _coarse()
    for k, lbas in ((2, (40_000, 900_000, 2_000_000)), (4, (1_200_000,))):
        fine = _finer(coarse, k)
        for lba in lbas:
            a = imagedisc._sector_q(coarse, ["A5", "B9"], U, V, BIT_MM, lba, 4, None)
            b = imagedisc._sector_q(fine, ["A5", "B9"], U, V, BIT_MM, lba, 4, None)
            assert np.array_equal(a, b), (k, lba)


def test_cd_sampler_follows_the_cell_size_too():
    coarse = _coarse()
    frame, slot = np.arange(200_000, 200_050)[:, None], np.array([0, 16])[None, :]
    a = cdimage._labels(coarse, 9000.0, 0.0006, 1.0e-3, frame, slot, None)
    b = cdimage._labels(_finer(coarse, 2), 9000.0, 0.0006, 1.0e-3, frame, slot, None)
    assert np.array_equal(a, b)


def test_grid_coordinates_at_a_finer_cell():
    x, y = imagedisc._grid_coords(12000)
    assert x.shape == (1, 12000) and y.shape == (12000, 1)
    assert abs(x[0, 0] - (-60 + 0.005)) < 1e-9 and abs(x[0, 1] - x[0, 0] - 0.01) < 1e-9
