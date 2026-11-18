"""Search bundled troubleshooting advice without a drive or network connection."""
from __future__ import annotations

import argparse
from collections import Counter
from functools import lru_cache
from importlib.resources import files
import json
from math import fsum
import re
import sys
import unicodedata

from . import i18n


RESULT_LIMIT = 3
MIN_SIMILARITY = 0.38
HELP = "search offline troubleshooting advice"
_PATH = re.compile(
    r"""["'](?:[a-z]:[/\\]|\\\\|/|\.{1,2}[/\\])[^"']+["']"""
    r"""|(?<![\w:/])(?:[a-z]:[/\\]|\\\\)[^"'<>|:;,()\[\]]*?\.[a-z0-9]{1,12}(?![\w./\\])"""
    r"""|(?<![\w:/])(?:[a-z]:[/\\]|\\\\|/|\.{1,2}[/\\])[^\s"'<>,;:()\[\]]+"""
    r"""|(?<![\w:/])(?:[\w.-]+[/\\])+[\w.-]+\.\w+(?!\w)""",
)
_DRIVE = re.compile(r"(?<!\w)[a-z]:(?=\s|$|[),;'\"])")
_NUMBER = re.compile(r"(?<![\w.])(?<!winerror )(?<!errno )[-+]?\d+(?:,\d{3})*(?:\.\d+)?(?:[eE][-+]?\d+)?(?![\d.])")
_WORDS = re.compile(r"[a-z0-9]+(?:[-'][a-z0-9]+)*|[\u3400-\u9fff]+")
_STOP = frozenset(
    "a am an and are be can can't could did do does for had has have how i in is it just me my of on "
    "or please says should so that the this to was were what when where which why will with won't would "
    "you your".split()
)
_COMMUNITY = {
    "en": ("No definite answer found. When asking the community, include your drive model, "
           "disc brand, write speed, read speed and complete log."),
    "zh": "没找到确定的答案。去社区提问时，请附上光驱型号、盘的品牌、刻录速度、读速和完整日志。",
}


def _fold(value):
    return unicodedata.normalize("NFKC", value).casefold()


def _normalize(line):
    line = _PATH.sub(lambda match: "<device>" if match[0].lstrip("\"'").startswith("/dev/") else "<path>",
                     _fold(line))
    line = _DRIVE.sub("<drive>", line)
    return " ".join(_NUMBER.sub("<n>", line).split())


def _signature(pattern):
    if "regex" in pattern:
        return re.compile(pattern["regex"])
    text = _normalize(pattern["text"])
    start = r"(?<![a-z0-9_])" if re.match(r"[a-z0-9_]", text) else ""
    end = r"(?![a-z0-9_])" if re.search(r"[a-z0-9_]$", text) else ""
    return re.compile(start + re.escape(text) + end)


def _tokens(value):
    tokens = set()
    for word in _WORDS.findall(_fold(value)):
        if word.isascii():
            if word not in _STOP:
                tokens.add(word)
        else:
            tokens.update(a + b for a, b in zip(word, word[1:]))
    return tokens


@lru_cache(maxsize=1)
def _index():
    path = files("discprobe").joinpath("data", "troubleshoot.json")
    entries = json.loads(path.read_text(encoding="utf-8"))
    variants = [[_tokens(phrase) for phrases in entry["symptoms"].values() for phrase in phrases]
                for entry in entries]
    frequency = Counter(word for phrases in variants for word in set().union(*phrases))
    weights = {word: 1 / count ** 0.5 for word, count in frequency.items()}
    return [
        (entry, [_signature(pattern) for pattern in entry["error_patterns"]],
         [(tokens, fsum(weights[word] for word in tokens)) for tokens in phrases])
        for entry, phrases in zip(entries, variants)
    ], weights


def _similarity(query, query_weight, phrases, weights):
    best = 0.0
    for tokens, weight in phrases:
        shared = query & tokens
        if len(shared) < 2 and query != tokens:
            continue
        score = 2 * fsum(weights[word] for word in shared) / (query_weight + weight)
        best = max(best, score)
    return best


def search(query: str, lang: str = "en") -> dict:
    """Rank distinct log signatures first, then bilingual symptom similarity."""
    if not isinstance(query, str):
        raise ValueError("query must be text")
    if not isinstance(lang, str) or lang not in _COMMUNITY:
        raise ValueError("lang must be zh or en")
    index, weights = _index()
    lines = tuple(dict.fromkeys(_normalize(line) for line in query.splitlines() if line.strip()))
    scores = []
    for entry, patterns, phrases in index:
        hits = [max((len(match[0]) for line in lines if (match := pattern.search(line))), default=0)
                for pattern in patterns]
        if any(hits):
            scores.append((entry, sum(bool(hit) for hit in hits), max(hits), 1.0))

    # With a known signature, avoid using surrounding log lines as conversational clues.
    if not scores:
        tokens = _tokens(query)
        query_weight = fsum(weights.get(word, 0.65) for word in tokens)
        if query_weight:
            for entry, _, phrases in index:
                similarity = _similarity(tokens, query_weight, phrases, weights)
                if similarity >= MIN_SIMILARITY:
                    scores.append((entry, 0, 0, similarity))

    scores.sort(key=lambda row: (-row[1], -row[2], -row[3], row[0]["id"]))
    results = [
        dict(id=entry["id"], confidence=round(score, 3), match="error" if matches else "symptom",
             cause=entry["cause"][lang], steps=entry["steps"][lang], commands=entry["commands"],
             manual=entry["manual"][lang], sources=entry["sources"])
        for entry, matches, _, score in scores[:RESULT_LIMIT]
    ]
    return dict(lang=lang, results=results, message=None if results else _COMMUNITY[lang])


def arguments(parser):
    parser.add_argument("query", metavar="QUERY", help="question, error message or - to read standard input")
    parser.add_argument("--json", action="store_true", help="write JSON")
    parser.set_defaults(func=run)


def cli(argv, *, prog):
    parser = argparse.ArgumentParser(prog=f"{prog} troubleshoot", description=i18n.tr(HELP))
    arguments(parser)
    i18n.localize_parser(parser)
    run(parser.parse_args(argv))


def run(args):
    query = args.query
    if query == "-":
        if hasattr(sys.stdin, "buffer") and not sys.stdin.isatty():
            raw = sys.stdin.buffer.read()
            try:
                query = raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                query = raw.decode(sys.stdin.encoding or "utf-8", errors="replace")
        else:
            query = sys.stdin.read()
    payload = search(query, i18n.active())
    if args.json:
        print(json.dumps(payload))
        return
    if payload["message"]:
        print(payload["message"])
        return
    for number, result in enumerate(payload["results"], 1):
        print(f"{number}. {result['cause']} [{result['id']}, {i18n.tr('Confidence')} {result['confidence']:.0%}]")
        for step in result["steps"]:
            print(f"   - {step}")
        for command in result["commands"]:
            print(f"     {command}")
        print("   " + i18n.tr("The manual is {name}.").format(name=result["manual"]))
