"""Build the offline Chinese title face (fontTools[woff] required).

Input: Adobe source-han-sans release 2.005R, 19_SourceHanSansCN.zip,
SubsetOTF/CN/SourceHanSansCN-Heavy.otf. Download/extract outside the checkout.
No network access is performed by this script.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import unicodedata

from fontTools import subset
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = ("discprobe/web", "disclab/web")
SCAN_SUFFIXES = {".html", ".js", ".mjs"}
# CJK punctuation only; ASCII letters, digits and punctuation deliberately absent.
PUNCTUATION = "、。，；：？！‘’“”（）《》〈〉【】〔〕［］｛｝「」『』…—·～　％＋－＝／＼｜＜＞＃＆＊＠￥"
OUTPUT = "SourceHanSansSC-Heavy-subset.woff2"
RELEASE_URL = "https://github.com/adobe-fonts/source-han-sans/releases/download/2.005R/19_SourceHanSansCN.zip"
SOURCE_SHA256 = "88c749b0a54a0800124ded6544e399302ed224aa49992ea364b88769f825c54c"


def allowed(name):
    return "b" + "lind" not in name.casefold()


def web_sources(root=ROOT):
    for folder in SCAN_ROOTS:
        for base, dirs, names in os.walk(root / folder):
            dirs[:] = sorted(n for n in dirs if allowed(n))
            for name in sorted(names):
                if allowed(name) and Path(name).suffix in SCAN_SUFFIXES:
                    yield Path(base) / name


def is_han(char):
    return unicodedata.name(char, "").startswith("CJK UNIFIED IDEOGRAPH") or unicodedata.name(char, "").startswith("CJK COMPATIBILITY IDEOGRAPH")


def page_characters(root=ROOT):
    return {c for path in web_sources(root) for c in path.read_text(encoding="utf-8")
            if is_han(c) or c in PUNCTUATION}


def gb2312_level_one():
    # GB2312 zones 16..55: B0A1..D7F9 (55's final five positions are unused).
    chars = set()
    for high in range(0xB0, 0xD8):
        for low in range(0xA1, 0xFF):
            try:
                chars.add(bytes((high, low)).decode("gb2312"))
            except UnicodeDecodeError:
                pass
    assert len(chars) == 3755
    return chars


def required_characters(root=ROOT):
    return page_characters(root) | gb2312_level_one() | set(PUNCTUATION)


def build(source, root=ROOT):
    digest = hashlib.sha256(Path(source).read_bytes()).hexdigest()
    if digest != SOURCE_SHA256:
        raise ValueError("Expected Adobe 2.005R CN Heavy OTF (source SHA256 mismatch)")
    chars = required_characters(root)
    font = TTFont(source, recalcTimestamp=False)
    missing = sorted(ord(c) for c in chars if ord(c) not in font.getBestCmap())
    if missing:
        raise ValueError(f"Adobe source lacks required codepoints: {missing}")
    options = subset.Options()
    options.recalc_timestamp = False
    options.canonical_order = True
    options.name_IDs = [0, 1, 2, 3, 4, 5, 6, 13, 14, 16, 17]
    sub = subset.Subsetter(options=options)
    sub.populate(unicodes=sorted(map(ord, chars)))
    sub.subset(font)
    # OFL reserves 'Source'. Derivative internal family/PostScript names use Disc.
    names = {1: "Disc Title SC", 2: "Heavy", 3: "DiscTitleSC-Heavy-2.005-subset",
             4: "Disc Title SC Heavy", 6: "DiscTitleSC-Heavy", 16: "Disc Title SC", 17: "Heavy"}
    for record in font["name"].names:
        if record.nameID in names:
            record.string = names[record.nameID].encode(record.getEncoding())
    if "CFF " in font:
        cff = font["CFF "].cff
        cff.fontNames = ["DiscTitleSC-Heavy"]
        cff.topDictIndex[0].FamilyName = "Disc Title SC"
        cff.topDictIndex[0].FullName = "Disc Title SC Heavy"
    font["OS/2"].usWeightClass = 900
    font.flavor = "woff2"
    destination = root / "discprobe/web/fonts" / OUTPUT
    font.save(destination)
    # Lab's desk is an independent static root and distributable.
    lab = root / "disclab/web/fonts" / OUTPUT
    lab.write_bytes(destination.read_bytes())
    result = dict(characters=len(chars), han=sum(map(is_han, chars)),
                  page_characters=len(page_characters(root)), gb2312_level_one=3755,
                  bytes=destination.stat().st_size, source_url=RELEASE_URL,
                  source_sha256=digest,
                  sha256=hashlib.sha256(destination.read_bytes()).hexdigest())
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    build(parser.parse_args().source)
