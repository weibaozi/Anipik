"""Release title parsing, filtering and magnet normalization."""
import base64
import hashlib
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode

import bencodepy

_V = r"(?:\s*v\d)?"  # 03v2
# Tried in order; within a pattern the last plausible match wins (episode follows the title).
_PATTERNS = [
    re.compile(r"S\d{1,2}\s*E(\d{1,4})" + _V + r"(?!\d)", re.I),
    re.compile(r"第\s*(\d{1,4})\s*[话話集回]"),
    re.compile(r"\s-\s(\d{1,4})" + _V + r"(?:\s*END)?(?=$|[\s\[\(【（.])", re.I),
    re.compile(r"[\[【]\s*(\d{1,4})" + _V + r"(?:\s*END)?\s*[\]】]", re.I),
    re.compile(r"(?<![A-Za-z])EP?\s?(\d{1,4})" + _V + r"(?![\dA-Za-z])", re.I),
    re.compile(r"(?<!\d)(\d{1,4})\s*[话話集]"),
]
_BATCH = [
    # "01-12", "01~12", "[01 - 12]"; but not "S02 - 12" (season, then " - episode")
    re.compile(r"(?<![\dSs])(\d{1,4})(?:-|\s*[~～]\s*|\s+to\s+)(\d{1,4})(?!\d)(?!\s*[pPiI年月])", re.I),
    re.compile(r"[\[【第]\s*(\d{1,4})\s*-\s*(\d{1,4})\s*[\]】话話集]"),
    re.compile(r"合集|全集|batch|complete(?:\s+series)?\b", re.I),
]
_NOISE = re.compile(
    r"(?i)\b\d{3,4}[pi]\b|\b\d{3,4}x\d{3,4}\b|\b[248]k\b|[xh]\.?26[45]|\b\d{1,2}[-\s]?bits?\b|"
    r"\baac\d?(?:\.\d)?\b|\bflac\b|\b\d\.\d\b|\b(?:19|20)\d{2}\b|\d+\s*(?:年|月)")
_FALLBACK = re.compile(r"(?<![\w.])(\d{1,4})(?![\w.])")
_RESOLUTIONS = {480, 540, 576, 720, 1080, 1440, 2160}


def _is_year(text):
    return len(text) == 4 and text[:2] in ("19", "20")


def is_batch(title):
    title = unicodedata.normalize("NFKC", title)
    for pattern in _BATCH:
        for match in pattern.finditer(title):
            if match.lastindex is None:
                return True
            start, end = int(match.group(1)), int(match.group(2))
            if start < end and not _is_year(match.group(1)):
                return True
    return False


def parse_episode(title):
    """Episode number of a single-episode release title, or None (unknown / batch)."""
    title = unicodedata.normalize("NFKC", title)
    if is_batch(title):
        return None
    for pattern in _PATTERNS:
        found = [m.group(1) for m in pattern.finditer(title) if not _is_year(m.group(1))]
        if found:
            return int(found[-1])
    cleaned = _NOISE.sub(" ", title)
    found = [n for n in _FALLBACK.findall(cleaned) if int(n) not in _RESOLUTIONS and not _is_year(n)]
    return int(found[-1]) if found else None


def matches_filters(title, include=(), exclude=()):
    """include: every pattern must match; exclude: none may match. Case-insensitive regexes."""
    return (all(re.search(p, title, re.I) for p in include or ())
            and not any(re.search(p, title, re.I) for p in exclude or ()))


def info_hash_from_magnet(magnet):
    """Lowercase hex BTIH of a magnet (accepts hex or base32 forms), or None."""
    if not magnet or not magnet.startswith("magnet:?"):
        return None
    for key, value in parse_qsl(magnet[len("magnet:?"):]):
        if key == "xt" and value.lower().startswith("urn:btih:"):
            digest = value[len("urn:btih:"):]
            if re.fullmatch(r"[0-9a-fA-F]{40}", digest):
                return digest.lower()
            if re.fullmatch(r"[A-Za-z2-7]{32}", digest):
                return base64.b32decode(digest.upper()).hex()
    return None


def info_hash_from_torrent(data: bytes):
    torrent = bencodepy.decode(data)
    return hashlib.sha1(bencodepy.encode(torrent[b"info"])).hexdigest()


def normalize_magnet(magnet):
    """Rewrite xt to lowercase hex so the same torrent always compares equal; keep trackers."""
    digest = info_hash_from_magnet(magnet)
    if digest is None:
        return None
    rest = [(k, v) for k, v in parse_qsl(magnet[len("magnet:?"):]) if k != "xt"]
    tail = ("&" + urlencode(rest)) if rest else ""
    return f"magnet:?xt=urn:btih:{digest}{tail}"


def magnet_from_hash(digest):
    return f"magnet:?xt=urn:btih:{digest.lower()}"
