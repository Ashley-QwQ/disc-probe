"""The catalogue tells the page which radii each geometry measured (webui_catalog.measured_ring)."""
from discprobe.webui_catalog import measured_ring


def test_widest_measured_interval():
    assert measured_ring({'fit': {'coverage': {'measured_intervals_mm': [[25.7, 40.0], [41.0, 54.0]]}}}) == [25.7, 40.0]
    assert measured_ring({'fit': {'coverage': {'measured_intervals_mm': [[25.7, 30.0], [31.0, 54.0]]}}}) == [31.0, 54.0]


def test_span_fallback_and_unknown():
    assert measured_ring({'fit': {'measured_span_mm': [26.0, 55.0]}}) == [26.0, 55.0]
    assert measured_ring({'fit': {}}) is None
    assert measured_ring({}) is None
    assert measured_ring({'fit': {'coverage': {'measured_intervals_mm': [[30, 30], ['x', 2]]}}}) is None
