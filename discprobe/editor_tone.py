"""Tone and dithering of a picture layer on the burn grid, shared with the page (web/home/design/tone.mjs).

Integer arithmetic only, so the page and the core give the same cells: a cell's grey is the floor of the BT.709
luminance of the nearest source pixel, mapped through the layer's tone table, then dithered to dark or light on the
grid being composed (the burn grid for `compose`). Error diffusion is serpentine Floyd-Steinberg in units of
1/1600 grey, by global row parity (even rows left to right), skipping cells that are outside the picture,
transparent or matched to a template colour. The matrix modes threshold against a rank tile indexed by the global
cell. The spec is in docs/EDITOR_DOCUMENT.md ("Tone and dither").
"""
from __future__ import annotations

MODES = ("floyd-steinberg", "blue-noise", "ordered", "clustered", "threshold")
DEFAULT_TONE = dict(brightness=0, contrast=0, highlights=0, shadows=0, dither="floyd-steinberg", strength=100)

# The page's 32 x 32 void-and-cluster rank tile (design/processing.mjs BLUE_NOISE_HEX), three hex digits a rank.
BLUE_NOISE_HEX = (
    "3621dd33a18125830b38c0c03fe1d233602221705e3ed17a1e53692e027d3f10f230205522e1cc35a08b33004b3dd1a0"
    "0b81012ca3ee02f2071421a92db06e2941943102a91112d604a13c08d33215a23e3871802c301c3f215b0d11e22502e7"
    "3b42240542810e834d2a10173550f838d0c53bc1dc0903882253d71981fe0b902629c11a3ac0e227721d2da398112079"
    "3221a814b3a11d00893cb11c25c20315c24d0351412693210d729803b3a92c636e1c10921f52fc19605b34101116f28e"
    "03737b0b431523c1702f71b90a33da05932e2ce37718400d1c612e30c2510fe17431b2623610733c51351c525f3ec1fb"
    "12a2522b500c10629304438427b2ec19c1ee10c0ac2123c62b13920a91d90673e70d90001542bc0f52923780960e52e4"
    "08618d3df1fd3913250c121b13800436d08c3e82823440f007123718a35328f2142dc3892381d63350282203041b1368"
    "1e62f50ce16107c1c33f018c3450df29a22f17705d1b42d415533701a3bb14603d1ad12109d3fc1870c23bd15f04729f"
    "3c20333332312c811325904e2c21df39312b3073a402325a3f82021102bb0d03283af2843090412112dd1162783970fa"
    "17c2741273d10243703030a03b71650340b32bd2001193120c60842fb1a12601e80571730ec37c26a07534c1f20a822b"
    "06937a09f1ab29016e1f40f623332726e3dc19507635f1761de27a3990483e10ad34b2462cd1c71493db1ae0072e332a"
    "1ca2b221035e0d307a3ab2b314306a1c93470de2a024b3d002c34f1262151622ef1173ca0130a63170e02a616b3a8118"
    "3f901b13e2f42403291b70183f72f610822700a38f0ff09a2ba1930d52d33750702281851f93a224e04f3732230c825b"
    "2d80f438618e04010736f2682060bb37e1682ea1b020e1523312413d900b1c826b0cf2b835d0fc2d71e3132323045197"
    "34e1ec06b2893e02c415708117f2ac0562533c40502c739f05f1ea0a228a14531d3f603215607d19b3e90aa2663be094"
    "1472393a60b01d12220cb3163961d53261280a53420d225d11e3113660ef3b00611a52f220d28033f0212fd1661d329b"
    "2e80d43241712fe0023c02851150253e619228d1e91633fd03a1ba15d2af1f124711f3760b53b510b21f2ad0e438000e"
    "3eb1bc03e2721233561a706c2422cc0dd21c30001535c2ab20a2f008038a02934608e2631752d20601ac3aa078201124"
    "06236c2093b908a2b70d81f83a51673520773ba11d1a20950f93c127619a0da2df1bf3d20081e736013a24f30a35426d"
    "2bf1880e72e115822c3e313132d0491bd2a70ca26738b23432f0011252263ef1402960f731e23a0be3ff02a1910b6159"
    "0982483400311da36b02028c0a425e38e1481ff2f804214e2cf1e434a09130503c20435b06f14d2f127e1042d11e13c3"
    "3191203d527c0b730d18b2ed1eb0e130e01d3c909b1d73ea0bc1823a32aa1b53820b11892713a71b608833c22a372012"
    "1b221905819e3a010507437d1393f32301992b41363392870682560ee04d15323d2d93e210202d20838314a0530f1291"
    "39c0c42eb1441fa2b92431ce0362c908710336a2450db1a637f30f20c3ce2861140101cf31329e0d62c11a33de2ff151"
    "07b3582953fa00632b0a13b827916d34920b05c3b200f2cb10d03816c2e90bf3943340972211783cf0642570b21f026c"
    "1091db04c24c0e638517b10e31a0ba3d32991d430114f21e3d81d833e07f1f317e2a513d3ae05131f1373632e501f3b6"
    "23f18333b1331c429d20f02724a1c00520f317d0ae28335108f2a812f2613fb03f2493670dc27f1b323b0eb1cd16431c"
    "0cd2c53cc09c3080633e42e637113b3382d53743f50461af0e93ad01e3591b81002fa06d1e02de01439d0853f4297065"
    "39a0391fc2733641500c91900832881f701623613020532026f1862162d00993b121318f3e510f35016a2c01f611b348"
    "21814c0e319f0192292b61ed3b30fb39b19d07e2be0c339e13f0663140cc15e2ae00932c09326521a0bd31802b2641aa"
    "2f93d62a23812e23c810a33d0302ee0a72703653061be0052a43d41a439025535712d28b1723950431bb3bf0ed37909e"
    "00324407212c0ab1c205a2751692321223cd1600ea2543430af22d0fd02e1cb0821ef3c70c72f31292a32351792b0134"
)
BLUE_NOISE = [int(BLUE_NOISE_HEX[i * 3:i * 3 + 3], 16) for i in range(1024)]


def bayer(size=8):
    n, ranks = 1, [0]
    while n < size:
        m = n * 2
        out = [0] * (m * m)
        for y in range(n):
            for x in range(n):
                v = ranks[y * n + x] * 4
                out[y * m + x] = v
                out[y * m + x + n] = v + 2
                out[(y + n) * m + x] = v + 3
                out[(y + n) * m + x + n] = v + 1
        ranks, n = out, m
    return ranks


def clustered(size=8):
    c = (size - 1) / 2
    order = sorted(range(size * size), key=lambda i: ((i % size - c) ** 2 + (i // size - c) ** 2, i))
    ranks = [0] * (size * size)
    for rank, index in enumerate(order):
        ranks[index] = rank
    return ranks


TILES = {"blue-noise": (32, BLUE_NOISE), "ordered": (8, bayer(8)), "clustered": (8, clustered(8))}


def tone(t=None) -> dict:
    """A layer's tone settings with defaults filled and checked."""
    t = {**DEFAULT_TONE, **(t or {})}
    for k in ("brightness", "contrast", "highlights", "shadows"):
        if type(t[k]) is not int or not -100 <= t[k] <= 100:
            raise ValueError(f"tone {k} must be a whole number from -100 to 100")
    if type(t["strength"]) is not int or not 0 <= t["strength"] <= 100:
        raise ValueError("tone strength must be a whole number from 0 to 100")
    if t["dither"] not in MODES:
        raise ValueError("unknown dither mode")
    return {k: t[k] for k in DEFAULT_TONE}


def table(t) -> list:
    """Grey 0..255 -> toned grey 0..255. Contrast scales around mid grey by (100 + c) / 100, brightness adds up to
    half the range, shadows / highlights lift or lower the dark / light half (cubic weights)."""
    t = tone(t)
    k, b, sh, hi = 100 + t["contrast"], t["brightness"], t["shadows"], t["highlights"]
    out = []
    for u in range(256):
        v = ((2 * u - 255) * k // 100 + 255 + b * 255 // 100) // 2
        v = min(255, max(0, v))
        w = 255 - v
        v += (2 * sh * v * w * w) // 6502500 + (2 * hi * v * v * w) // 6502500
        out.append(min(255, max(0, v)))
    return out


def luminance(r, g, b):
    """floor(0.2126 R + 0.7152 G + 0.0722 B), exactly (numpy arrays or ints)."""
    return (2126 * r + 7152 * g + 722 * b) // 10000


class Diffusion:
    """Floyd-Steinberg state of one layer across the rows of one grid."""

    def __init__(self, width, strength):
        self.w, self.s = width, strength
        self.acc = [0] * (width + 2)

    def row(self, j, grey, take):
        """grey, take: arrays of the row's width; returns the row's dark flags (False where not taken). Only the span
        from the first to the last taken cell is walked; the error carried to the next row is zero outside it."""
        import numpy as np
        w, s = self.w, self.s
        nxt = [0] * (w + 2)
        dark = np.zeros(w, bool)
        idx = np.flatnonzero(take)
        if idx.size:
            x0, x1 = int(idx[0]), int(idx[-1])
            g, tk, acc = grey[x0:x1 + 1].tolist(), take[x0:x1 + 1].tolist(), self.acc
            out = [False] * (x1 - x0 + 1)
            d = 1 if j % 2 == 0 else -1
            carry = 0
            for k in (range(x1 - x0 + 1) if d > 0 else range(x1 - x0, -1, -1)):
                if not tk[k]:
                    carry = 0
                    continue
                x = x0 + k
                v = g[k] + (acc[x + 1] + carry) // 1600
                if v < 128:
                    out[k] = True
                    e = v * s
                else:
                    e = (v - 255) * s
                carry = 7 * e
                nxt[x + 1 - d] += 3 * e
                nxt[x + 1] += 5 * e
                nxt[x + 1 + d] += e
            dark[x0:x1 + 1] = out
        self.acc = nxt
        return dark


def matrix_dark(mode, strength, j, xs, grey):
    """Dark flags for a threshold-tile mode: grey/255 below 1/2 + strength * (rank + 1/2 - N/2) / N."""
    import numpy as np
    if mode == "threshold":
        return grey < 128
    n, ranks = TILES[mode]
    r = np.asarray(ranks).reshape(n, n)[j % n][xs % n]
    nn = n * n
    return grey * 200 * nn < 25500 * nn + strength * 255 * (2 * r + 1 - nn)
