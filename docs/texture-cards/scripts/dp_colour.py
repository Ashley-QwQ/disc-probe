"""Verbatim DP function. Source: D:/disc-probe/.claude/worktrees/editor-template/discprobe/first_order.py
SHA-256 (whole source file): 8722aa2a074ee1876502a629587536c3a6c522e24fd97e3476c489d4450c9a7e
No transfer function is present in the original.
"""

def wavelength_rgb(nm):
    """Rough visible-spectrum colour (unchanged from tools/lut_scatter.py)."""
    if nm < 440:
        r, g, b = -(nm - 440) / 40, 0.0, 1.0
    elif nm < 490:
        r, g, b = 0.0, (nm - 440) / 50, 1.0
    elif nm < 510:
        r, g, b = 0.0, 1.0, -(nm - 510) / 20
    elif nm < 580:
        r, g, b = (nm - 510) / 70, 1.0, 0.0
    elif nm < 645:
        r, g, b = 1.0, -(nm - 645) / 65, 0.0
    else:
        r, g, b = 1.0, 0.0, 0.0
    return (r, g, b)
