"""D'ni numbers, calendar and script helpers.

The calendar follows the community-standard conversion: the hahr is one mean tropical year long, and
Leefo 1, 9654 DE began at 1998-04-21 09:54:16 MST (16:54:16 UTC).
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone

# Keystrokes of the D'ni font for the digits 0..24.
DIGIT_KEYS = "0123456789)!@#$%^&*([]\\{}"

VAILEETEE = ["Leefo", "Leebro", "Leesahn", "Leetar", "Leevot", "Leevofo", "Leevobro", "Leevosahn", "Leevotar",
             "Leenovoo"]
YAHRTEE_PER_VAILEE = 29
YAHRTEE_PER_HAHR = 290

HAHR_SECONDS = 31_556_925.216
YAHR_SECONDS = HAHR_SECONDS / YAHRTEE_PER_HAHR
EPOCH = datetime(1998, 4, 21, 16, 54, 16, tzinfo=timezone.utc)
EPOCH_HAHR = 9654


# --------------------------------------------------------------------------------------------
# Numbers
# --------------------------------------------------------------------------------------------
def to_base25(n: int) -> list[int]:
    if n < 0:
        raise ValueError("D'ni numbers here are non-negative")
    digits = [n % 25]
    n //= 25
    while n:
        digits.insert(0, n % 25)
        n //= 25
    return digits


def from_base25(digits: list[int]) -> int:
    n = 0
    for d in digits:
        if not 0 <= d < 25:
            raise ValueError(f"digit {d} out of range")
        n = n * 25 + d
    return n


def to_font(n: int) -> str:
    return "".join(DIGIT_KEYS[d] for d in to_base25(n))


def from_font(s: str) -> int:
    return from_base25([DIGIT_KEYS.index(ch) for ch in s if ch in DIGIT_KEYS])


def number_info(n: int) -> dict:
    digits = to_base25(n)
    places = [{"digit": d, "key": DIGIT_KEYS[d], "place": 25 ** i, "value": d * 25 ** i}
              for i, d in reversed(list(enumerate(reversed(digits))))]
    return {"n": n, "digits": digits, "font": to_font(n), "places": places}


# --------------------------------------------------------------------------------------------
# Calendar & time
# --------------------------------------------------------------------------------------------
def to_dni(when: datetime) -> dict:
    """Gregorian datetime (aware, or naive = UTC) -> D'ni date and time."""
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    secs = (when - EPOCH).total_seconds()
    hahr_off = math.floor(secs / HAHR_SECONDS)
    into = secs - hahr_off * HAHR_SECONDS
    yahr_idx = int(into // YAHR_SECONDS)
    frac = (into - yahr_idx * YAHR_SECONDS) / YAHR_SECONDS  # fraction of the yahr elapsed
    # Time units: yahr = 5 gahrtahvotee = 25 pahrtahvotee = 125 tahvotee = 3125 gorahntee = 78125 prorahntee.
    pro = int(frac * 78125)
    gahr, rem = divmod(pro, 15625)
    pahr, rem = divmod(rem, 3125)
    tahvo, rem = divmod(rem, 625)
    gorahn, prorahn = divmod(rem, 25)
    vailee = yahr_idx // YAHRTEE_PER_VAILEE
    return {
        "hahr": EPOCH_HAHR + hahr_off, "vailee": vailee + 1, "vailee_name": VAILEETEE[vailee],
        "yahr": yahr_idx % YAHRTEE_PER_VAILEE + 1,
        "gahrtahvo": gahr, "pahrtahvo": pahr, "tahvo": tahvo, "gorahn": gorahn, "prorahn": prorahn,
        "bell": gahr * 5 + pahr + 1,  # 1..25 bells in a yahr
        "fraction": frac,
    }


def from_dni(hahr: int, vailee: int, yahr: int, gahrtahvo: int = 0, pahrtahvo: int = 0, tahvo: int = 0,
             gorahn: int = 0, prorahn: int = 0) -> datetime:
    """D'ni date (vailee and yahr 1-based) -> UTC datetime."""
    if not 1 <= vailee <= 10 or not 1 <= yahr <= YAHRTEE_PER_VAILEE:
        raise ValueError("vailee must be 1-10 and yahr 1-29")
    pro = (((gahrtahvo * 5 + pahrtahvo) * 5 + tahvo) * 25 + gorahn) * 25 + prorahn
    secs = ((hahr - EPOCH_HAHR) * HAHR_SECONDS + ((vailee - 1) * YAHRTEE_PER_VAILEE + yahr - 1) * YAHR_SECONDS
            + pro / 78125 * YAHR_SECONDS)
    return EPOCH + timedelta(seconds=secs)


def format_dni(d: dict) -> str:
    return (f"{d['vailee_name']} {d['yahr']}, {d['hahr']} DE · "
            f"{d['gahrtahvo']}:{d['pahrtahvo']:02d}:{d['tahvo']:02d}:{d['gorahn']:02d}")


def year_to_dni(year: int) -> int:
    """Hahr that is current on July 21 of a Gregorian year (astronomical: 1 BCE = 0)."""
    return year + EPOCH_HAHR - 1998


# --------------------------------------------------------------------------------------------
# Script: transcription -> D'ni font keystrokes
# --------------------------------------------------------------------------------------------
# Old Transcription Standard digraphs, longest first. Single letters not listed map to themselves.
_DIGRAPHS = [
    ("sh", "S"), ("kh", "k"), ("th", "T"), ("dh", "d"), ("ch", "c"), ("ts", "x"),
    ("ah", "a"), ("ee", "E"), ("eh", "e"), ("ai", "A"), ("oy", "O"), ("uh", "u"), ("oo", "U"), ("í", "I"),
]
_SINGLE = {"k": "K", "d": "D", "a": "a", "e": "e", "i": "i", "o": "o", "u": "u", "'": "'", "’": "'"}
_ALLOWED = set("vbtsSjgykKaIfpiEeArmTdDhoOcwuUxlzn.-' ")


def transcribe(text: str) -> str:
    """Turn transcribed D'ni ("shorah b'shehm") into font keystrokes ("Sora b'Sem")."""
    out = []
    s = text.lower()
    i = 0
    while i < len(s):
        for src, key in _DIGRAPHS:
            if s.startswith(src, i):
                out.append(key)
                i += len(src)
                break
        else:
            ch = s[i]
            key = _SINGLE.get(ch, ch)
            out.append(key if key in _ALLOWED else "")
            i += 1
    return re.sub(r" +", " ", "".join(out))


ALPHABET = [
    ("v", "v", "very"), ("b", "b", "bed"), ("t", "t", "top"), ("s", "s", "sun"), ("S", "sh", "shop"),
    ("j", "j", "jam"), ("g", "g", "go"), ("y", "y", "yak"), ("k", "kh", "Bach"), ("K", "k", "kite"),
    ("a", "ah", "spa"), ("I", "í", "ice"), ("f", "f", "fun"), ("p", "p", "pen"), ("i", "i", "sit"),
    ("E", "ee", "meet"), ("e", "eh", "egg"), ("A", "ai", "rain"), ("r", "r", "red"), ("m", "m", "map"),
    ("T", "th", "thin"), ("d", "dh", "that"), ("D", "d", "dog"), ("h", "h", "hope"), ("o", "o", "note"),
    ("O", "oy", "toy"), ("c", "ch", "chin"), ("w", "w", "win"), ("u", "uh", "cup"), ("U", "oo", "moon"),
    ("x", "ts", "cats"), ("l", "l", "lamp"), ("z", "z", "zip"), ("n", "n", "nose"),
]
