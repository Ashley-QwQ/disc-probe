"""Where each recorded bit really is, and when a drive says it finished reading it.

Conventions (all angles in radians):

* theta_g(m): accumulated groove angle at groove bit m, 2 pi (s - u) / v - phi(r), s = sqrt(u^2 + v m / pi),
  r = b s. phi(r) is the stamper's variable pitch (degrees in the answer file). Same form as calib.theta.
* A burn puts user bit n at groove bit m = n + w (w: this burn's write offset in bits).
* Physical picture angle, data-side view, maths orientation (as imagedisc and pcal use): alpha(n) = -theta_g(n + w).
* Timing angle the reading drive reports for a read ending at user bit n:
      theta_t(n) = theta_g(n + w + d) + asin(h / r) - (e / r) sin(psi + theta_g)
  d: the drive's completion delay in bits (unknown to geo), h: head offset from the spindle line (mm),
  e, psi: groove eccentricity against the hole. So the path's along-track constant is L = d b + h, which is
  what pcal's tau(r) = c + L / r measures: a feature placed for theta_geo lands L / r further on.
"""
from __future__ import annotations

import math

import numpy as np

TWO_PI = 2 * math.pi


class Disc:
    def __init__(self, truth: dict, burn: dict | None = None):
        self.t = truth
        self.u = float(truth["u"])
        self.v = float(truth["v"])
        self.b_mm = float(truth["b_nm"]) * 1e-6
        self.bps = float(truth["bits_per_sector"])
        self.family = truth["family"]
        self.vp_r = np.asarray(truth["varpitch_r_mm"], float)
        self.vp_deg = np.asarray(truth["varpitch_deg"], float)
        self.ecc_mm = float(truth["ecc_um"]) * 1e-3
        self.ecc_rad = math.radians(float(truth["ecc_deg"]))
        first = ((burn or {}).get("sessions") or [{}])[0]
        self.w_bits = float(first.get("write_offset_bits", (burn or {}).get("write_offset_bits", 0.0)))

    # ------------------------------------------------------------ groove
    def s(self, m):
        return np.sqrt(self.u * self.u + self.v * np.asarray(m, float) / math.pi)

    def radius(self, m):
        return self.b_mm * self.s(m)

    def phi(self, r):
        return np.radians(np.interp(r, self.vp_r, self.vp_deg))

    def theta_g(self, m):
        m = np.asarray(m, float)
        s = self.s(m)
        return 2.0 * m / (s + self.u) - self.phi(self.b_mm * s)

    # ------------------------------------------------------------ data
    def alpha(self, n):
        """Physical angle (data-side view, maths orientation) of user bit n of this burn."""
        return -self.theta_g(np.asarray(n, float) + self.w_bits)

    def data_radius(self, n):
        return self.radius(np.asarray(n, float) + self.w_bits)

    def timing_theta(self, n, d_bits: float, head_mm: float):
        m = np.asarray(n, float) + self.w_bits
        th = self.theta_g(m + d_bits)
        r = self.radius(m)
        return th + np.arcsin(np.clip(head_mm / r, -1, 1)) - (self.ecc_mm / r) * np.sin(self.ecc_rad + th)

    def bit_at(self, r, alpha):
        """User bit index of the track nearest (r, alpha) (data-side angles), as a float; NaN outside."""
        r = np.asarray(r, float)
        alpha = np.asarray(alpha, float)
        s = r / self.b_mm
        th0 = TWO_PI * (s - self.u) / self.v - self.phi(r)        # angle a groove at this radius would have
        target = -alpha                                             # theta_g must equal this modulo 2 pi
        k = np.round((th0 - target) / TWO_PI)
        th = target + TWO_PI * k
        # invert theta_g(m) = th with phi held at this radius (phi changes far slower than one turn)
        s_m = self.u + self.v * (th + self.phi(r)) / TWO_PI
        m = math.pi * (s_m * s_m - self.u * self.u) / self.v
        return m - self.w_bits


def ref_bit_offsets(family: str):
    """Bit offset of each user byte in its sector, and the channel bits per sector (DVD layout from calib)."""
    from discprobe import calib
    if family == "dvd":
        return calib._byte_bit_offsets(), float(calib.SECTOR_BITS)
    raise NotImplementedError("byte layout is only modelled for DVD")
