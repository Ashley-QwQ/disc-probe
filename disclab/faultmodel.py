"""Fault rules shared by scenario validation, devices, and scoring (lab-only)."""
from __future__ import annotations

KINDS = ("read_error", "spindle_unsteady", "capacity_misreport", "burn_interrupt")


def active_faults(answers, disc_id=None, kind=None):
    for fault in answers.get("faults", []):
        p = fault["params"]
        if (kind is None or fault["kind"] == kind) and (
                "disc" not in p or p["disc"] == disc_id):
            yield fault


def reported_sectors(answers, disc_id, actual):
    value = actual
    for f in active_faults(answers, disc_id, "capacity_misreport"):
        p = f["params"]
        value = p.get("sectors", value + p.get("offset", 0))
    return max(1, min(0xFFFFFFFF, value))


def burn_failure(answers, disc_id, reader):
    behaviour = dict(answers["readers"][reader].get("burn_failure", {"kind": "none"}))
    for f in active_faults(answers, disc_id, "burn_interrupt"):
        behaviour = dict(kind="stop_at", **{k: v for k, v in f["params"].items() if k != "disc"})
    return behaviour
