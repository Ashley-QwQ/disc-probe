"""Small QR Model 2 encoder: UTF-8 byte mode, ECC M, versions 1..6, no dependencies.

The maximum 106 bytes covers an IPv4 LAN URL plus a 256-bit photo token.
Uses mask 0 (a valid fixed mask); SVG includes the required four-module quiet zone.
"""
from __future__ import annotations

# (data codewords, ECC codewords per block, number of equal-sized blocks)
_BLOCKS = ((16, 10, 1), (28, 16, 1), (44, 26, 1), (64, 18, 2), (86, 24, 2), (108, 16, 4))


def _mul(x, y):
    out = 0
    while y:
        if y & 1:
            out ^= x
        x <<= 1
        if x & 0x100:
            x ^= 0x11D
        y >>= 1
    return out


def _ecc(data, count):
    divisor = [1]
    root = 1
    for _ in range(count):
        product = [0] * (len(divisor) + 1)
        for j, c in enumerate(divisor):
            product[j] ^= c
            product[j + 1] ^= _mul(c, root)
        divisor = product
        root = _mul(root, 2)
    remainder = list(data) + [0] * count
    for i in range(len(data)):
        factor = remainder[i]
        for j, c in enumerate(divisor):
            remainder[i + j] ^= _mul(c, factor)
    return remainder[-count:]


def matrix(text):
    data = text.encode("utf-8")
    version = next((v for v, (n, _, _) in enumerate(_BLOCKS, 1) if 12 + len(data) * 8 <= n * 8), None)
    if version is None:
        raise ValueError("QR byte payload exceeds 106 bytes")
    capacity, ecc_count, block_count = _BLOCKS[version - 1]
    bits = [int(b) for b in f"0100{len(data):08b}" + "".join(f"{b:08b}" for b in data)]
    bits += [0] * min(4, capacity * 8 - len(bits))
    bits += [0] * (-len(bits) % 8)
    words = [sum(bits[i + j] << (7 - j) for j in range(8)) for i in range(0, len(bits), 8)]
    while len(words) < capacity:
        words.append(0xEC if (len(words) - len(bits) // 8) % 2 == 0 else 0x11)
    width = capacity // block_count
    blocks = [words[i:i + width] for i in range(0, capacity, width)]
    check = [_ecc(b, ecc_count) for b in blocks]
    encoded = [b[i] for i in range(width) for b in blocks] + [b[i] for i in range(ecc_count) for b in check]
    bits = [bool((b >> j) & 1) for b in encoded for j in range(7, -1, -1)]
    size = version * 4 + 17
    cells = [[False] * size for _ in range(size)]
    reserved = [[False] * size for _ in range(size)]

    def put(x, y, value):
        cells[y][x], reserved[y][x] = bool(value), True

    # Timing lines first; finder patterns overwrite their overlapping parts.
    for i in range(size):
        put(6, i, i % 2 == 0)
        put(i, 6, i % 2 == 0)
    for cx, cy in ((3, 3), (size - 4, 3), (3, size - 4)):
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                x, y = cx + dx, cy + dy
                if 0 <= x < size and 0 <= y < size:
                    put(x, y, max(abs(dx), abs(dy)) not in (2, 4))
    if version > 1:
        center = size - 7
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                put(center + dx, center + dy, max(abs(dx), abs(dy)) != 1)

    # ECC M is 00; mask 0 is 000. BCH(15,5), then the format XOR mask.
    format_bits = 0x5412
    for i in range(6):
        put(8, i, format_bits >> i & 1)
    put(8, 7, format_bits >> 6 & 1)
    put(8, 8, format_bits >> 7 & 1)
    put(7, 8, format_bits >> 8 & 1)
    for i in range(9, 15):
        put(14 - i, 8, format_bits >> i & 1)
    for i in range(8):
        put(size - 1 - i, 8, format_bits >> i & 1)
    for i in range(8, 15):
        put(8, size - 15 + i, format_bits >> i & 1)
    put(8, size - 8, True)
    cursor, right = 0, size - 1
    while right >= 1:
        if right == 6:
            right = 5
        upward = (right + 1) & 2 == 0
        for row in range(size):
            y = size - 1 - row if upward else row
            for x in (right, right - 1):
                if not reserved[y][x]:
                    value = bits[cursor] if cursor < len(bits) else False
                    cells[y][x] = value ^ ((x + y) % 2 == 0)
                    cursor += 1
        right -= 2
    return cells


def svg(text):
    cells = matrix(text)
    size = len(cells) + 8
    path = "".join(f"M{x + 4},{y + 4}h1v1h-1z" for y, row in enumerate(cells) for x, dark in enumerate(row) if dark)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" '
            'role="img" aria-label="Open the phone photo page" shape-rendering="crispEdges">'
            f'<path fill="#fff" d="M0,0h{size}v{size}H0z"/><path fill="#000" d="{path}"/></svg>')
