"""Generate title-only CSS from bundled and local font metrics (no downloads).

Run on Windows with fontTools[woff]:
  python -X utf8 -B tools/align_title_fonts.py --report D:/temp/title-metrics.json

Only the two titles.css files are written. Local font bytes are never copied.
Fallback calibration uses Archivo 800 at each existing title width. Static
fallbacks cannot reproduce every variable weight/width instance or shaped run.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "discprobe/web/fonts"
SELECTORS = """h1, h2, h3, h4, .wordmark, .mark, .name, .gallery .word, .floor-log .fl-title,
.lb-label, .np-title, .np-face-text, .pw-d-name, .pw-name-edit, .pw-code,
.pc-wordmark, .ws-title b, .fx-print > b, .fx-sect, #hello"""
# Fixed calibration corpus: product names, media names, mixed-title Latin runs.
# Match the total advance, rather than fitting screenshot dimensions by eye.
LATIN_CORPUS = "DISC-PROBE Disc Probe Disc Lab Disc Neo DVD-R CD-R BD 0123456789 16x"
# Existing title widths, plus the bundled variable font's lower endpoint.
TITLE_WIDTHS = (62, 100, 105, 108, 110, 112, 115, 118, 120, 122, 125)


def read_font(path, index=0):
    font = TTFont(path, fontNumber=index, recalcTimestamp=False)
    upem = font["head"].unitsPerEm
    os2, hhea = font["OS/2"], font["hhea"]
    record = {
        "file": Path(path).name, "index": index,
        "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
        "family": font["name"].getDebugName(1),
        "postscript": font["name"].getDebugName(6), "unitsPerEm": upem,
        "hhea": {key: getattr(hhea, key) for key in ("ascent", "descent", "lineGap")},
        "OS/2": {key: getattr(os2, key) for key in (
            "sTypoAscender", "sTypoDescender", "sTypoLineGap", "usWinAscent",
            "usWinDescent", "sxHeight", "sCapHeight", "fsSelection")},
    }
    return font, record


def advance(font, text):
    cmap = font.getBestCmap()
    return sum(font["hmtx"][cmap[ord(c)]][0] for c in text) / font["head"].unitsPerEm


def unicode_ranges(codepoints):
    """Compact an exact cmap; calibrated Latin fallback must never claim Han."""
    runs = []
    for cp in sorted(codepoints):
        if runs and cp == runs[-1][1] + 1:
            runs[-1][1] = cp
        else:
            runs.append([cp, cp])
    return ", ".join(f"U+{a:X}" + (f"-{b:X}" if a != b else "") for a, b in runs)


def generate(windows_fonts=Path("C:/Windows/Fonts")):
    archivo, ar = read_font(FONTS / "Archivo-VF-latin.woff2")
    chinese, sc = read_font(FONTS / "SourceHanSansSC-Heavy-subset.woff2")
    latin, la = read_font(windows_fonts / "ariblk.ttf")
    han, ha = read_font(windows_fonts / "msyhbd.ttc", 1)  # YaHei UI Bold
    references = {width: instantiateVariableFont(archivo, {"wght": 800, "wdth": width}, inplace=False)
                  for width in TITLE_WIDTHS}
    # Archivo uses OS/2 typo metrics (USE_TYPO_METRICS); hhea agrees exactly.
    assert ar["OS/2"]["fsSelection"] & (1 << 7)
    target = {"ascent": ar["OS/2"]["sTypoAscender"] / ar["unitsPerEm"],
              "descent": -ar["OS/2"]["sTypoDescender"] / ar["unitsPerEm"],
              "line-gap": ar["OS/2"]["sTypoLineGap"] / ar["unitsPerEm"]}
    assert target == {"ascent": ar["hhea"]["ascent"] / ar["unitsPerEm"],
                      "descent": -ar["hhea"]["descent"] / ar["unitsPerEm"],
                      "line-gap": ar["hhea"]["lineGap"] / ar["unitsPerEm"]}
    # Same x-height / em, using metadata retained by the Han-only subset.
    sc_scale = (ar["OS/2"]["sxHeight"] / ar["unitsPerEm"]) / (sc["OS/2"]["sxHeight"] / sc["unitsPerEm"])
    # All covered ideographs have one-em advances in both fonts. Check that
    # assumption rather than silently using an arbitrary representative glyph.
    ideographs = [cp for cp in chinese.getBestCmap() if 0x4E00 <= cp <= 0x9FFF]
    for font in (chinese, han):
        cmap = font.getBestCmap()
        assert all(cp in cmap and font["hmtx"][cmap[cp]][0] == font["head"].unitsPerEm for cp in ideographs)
    han_scale = sc_scale * advance(chinese, chr(ideographs[0])) / advance(han, chr(ideographs[0]))
    latin_scales = {width: advance(font, LATIN_CORPUS) / advance(latin, LATIN_CORPUS)
                    for width, font in references.items()}
    scales = {"Archivo Title": 1.0, "Disc Title SC": sc_scale,
              "Disc Title Latin Fallback": latin_scales, "Disc Title SC Fallback": han_scale}

    def face(family, source, scale, weight="100 900", stretch=False, coverage=None):
        lines = ["@font-face {", f'  font-family: "{family}";', f"  src: {source};",
                 f"  font-weight: {weight};", "  font-style: normal;"]
        if stretch:
            lines.append(f"  font-stretch: {stretch};")
        lines.extend(["  font-display: swap;", f"  size-adjust: {scale * 100:.6f}%;"])
        # size-adjust scales overrides too; divide once to preserve the target.
        lines.extend(f"  {key}-override: {value / scale * 100:.6f}%;" for key, value in target.items())
        if coverage:
            lines.append(f"  unicode-range: {coverage};")
        return "\n".join(lines + ["}"])

    faces = [
        face("Archivo Title", 'url("Archivo-VF-latin.woff2") format("woff2")', 1, stretch="62% 125%"),
        face("Disc Title SC", 'url("SourceHanSansSC-Heavy-subset.woff2") format("woff2")', sc_scale, weight="900"),
        *(face("Disc Title Latin Fallback", 'local("Arial Black"), local("Arial-Black")', scale,
               stretch=f"{width}%", coverage=unicode_ranges(archivo.getBestCmap()))
          for width, scale in latin_scales.items()),
        face("Disc Title SC Fallback", 'local("Microsoft YaHei UI Bold"), local("MicrosoftYaHeiUI-Bold")', han_scale,
             coverage=unicode_ranges(chinese.getBestCmap())),
    ]
    css = """/* Generated by tools/align_title_fonts.py; do not tune percentages by eye.
   Archivo's title alias keeps every body @font-face and font stack untouched.
   SC scale = Archivo sxHeight/em / SC sxHeight/em; line metrics = Archivo.
   Local Latin matches aggregate advances at 800 / each title width; Han matches em width.
   size-adjust also scales metric overrides, so each override is target / scale.
   These descriptors are the fallback strategy from modern-web-guidance; adding
   font-size-adjust on top would cancel the advance-based local calibration.
   Missing local faces fall through to the existing platform stack (uncalibrated).
   Source Han derivative retains its OFL-compliant internal name Disc Title SC. */
""" + "\n".join(faces) + """
:root {
  --font-title: "Archivo Title", "Disc Title SC", "Disc Title Latin Fallback", "Disc Title SC Fallback", "Microsoft YaHei UI", "PingFang SC", system-ui, sans-serif;
}
/* Only title font declarations: incumbent size, weight, width and spacing remain.
   Local --font also covers the existing font shorthands on these elements. */
""" + SELECTORS + """ {
  --font: var(--font-title);
  font-family: var(--font-title);
}
"""
    report = {"inputs": [ar, sc, la, ha], "reference": {"wght": 800, "widths": TITLE_WIDTHS},
              "latin_corpus": LATIN_CORPUS, "target_em": target, "size_adjust": scales,
              "han_advance_counts": {str(k): v for k, v in Counter(
                  chinese["hmtx"][chinese.getBestCmap()[cp]][0] for cp in ideographs).items()},
              "latin_reference_advance_em": {width: advance(font, LATIN_CORPUS) for width, font in references.items()},
              "latin_fallback_advance_em": advance(latin, LATIN_CORPUS),
              "limits": "Static Windows local fallback; other platforms and non-reference variable instances are not exact."}
    return css, report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--windows-fonts", type=Path, default=Path("C:/Windows/Fonts"))
    parser.add_argument("--report", type=Path)
    parser.add_argument("--check", action="store_true", help="Verify generated CSS without writing")
    args = parser.parse_args()
    css, report = generate(args.windows_fonts)
    for folder in ("discprobe", "disclab"):
        path = ROOT / folder / "web/fonts/titles.css"
        if args.check:
            if path.read_text(encoding="utf-8") != css:
                raise SystemExit(f"Out of date: {path}")
        else:
            path.write_text(css, encoding="utf-8", newline="\n")
    serialized = json.dumps(report, indent=2, ensure_ascii=True) + "\n"
    if args.report:
        args.report.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
