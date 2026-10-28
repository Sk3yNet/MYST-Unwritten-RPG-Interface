"""Draws the maps (via maps.py) and handouts for "The Concordance". Run: python3 art.py  (writes ../maps and ../handouts).

Everything is generated so the glyphs, constellations and tones stay consistent across the campaign. Edit the
tables at the top, re-run, and every map and handout follows.
"""
from __future__ import annotations

import math
from xml.sax.saxutils import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INK = "#3a2816"
BRASS = "#8c6a2c"
PAPER = "#e8d6ae"
FONT = "IM Fell English, Georgia, serif"

# ---------------------------------------------------------------------------------------------------------------
# The campaign's symbolic language
# ---------------------------------------------------------------------------------------------------------------
# Glyphs in a 100x100 box. Fire/Water and Air/Earth are mirror images of each other; Ice is symmetric.
# Fire: a flame leaning right. Water, its mirror: a drop leaning left.
FLAME = "M40 92 C18 84 16 58 32 40 C42 28 44 16 62 6 C58 26 76 34 80 54 C84 76 66 94 40 92 Z M44 80 C36 72 40 60 50 54"
SPIRAL = "M50 50 C50 44 58 44 58 50 C58 60 44 62 42 50 C40 34 62 30 68 48 C74 68 50 80 36 70 C22 60 22 34 40 24"
ICE = ("M50 10 V90 M15.4 30 L84.6 70 M15.4 70 L84.6 30 M42 16 L50 24 L58 16 M42 84 L50 76 L58 84 "
       "M17 40 L26 36 L22 27 M83 60 L74 64 L78 73 M17 60 L26 64 L22 73 M83 40 L74 36 L78 27")
GLYPHS = {"ice": (ICE, False), "fire": (FLAME, False), "water": (FLAME, True), "air": (SPIRAL, False),
          "earth": (SPIRAL, True)}
OPPOSITE = {"ice": "ice", "fire": "water", "water": "fire", "air": "earth", "earth": "air"}

# Constellations: star offsets (x, y) around a center, and the lines of the figure.
STARS = {
    "lantern": ([(0, -34), (-16, -14), (16, -14), (-16, 18), (16, 18), (0, 36)],
                [(0, 1), (0, 2), (1, 3), (2, 4), (3, 5), (4, 5), (1, 2)]),
    "anvil": ([(-38, -6), (38, -6), (-18, 8), (18, 8), (-14, 30), (14, 30)],
              [(0, 1), (0, 2), (1, 3), (2, 4), (3, 5), (4, 5)]),
    "kite": ([(0, -38), (-22, -4), (22, -4), (0, 18), (6, 30), (-4, 40)],
             [(0, 1), (0, 2), (1, 3), (2, 3), (3, 4), (4, 5)]),
    "seed": ([(0, -36), (-14, -8), (14, -8), (-8, 18), (8, 18), (0, 38)],
             [(0, 1), (0, 2), (1, 3), (2, 4), (3, 5), (4, 5), (1, 2)]),
    "heron": ([(-34, -26), (-14, -34), (-2, -10), (8, 14), (30, 22), (-6, 40)],
              [(0, 1), (1, 2), (2, 3), (3, 4), (3, 5)]),
}
CONSTELLATION_NAME = {"lantern": "The Lantern", "anvil": "The Anvil", "kite": "The Kite", "seed": "The Seed",
                      "heron": "The Heron"}

# The five Ages, in the order their Books open. ring 1 is the innermost ring of the Concordance.
AGES = [
    # element, constellation, tone, ring, target glyph shown after activation
    ("ice", "lantern", "E", 1, "ice"),
    ("fire", "anvil", "C", 2, "water"),
    ("air", "kite", "G", 3, "earth"),
    ("earth", "seed", "D", 4, "fire"),
    ("water", "heron", "A", 5, "air"),
]
# Positions of the five figures painted around the Sanctuary dome (degrees, 0 = top), deliberately not in ring order.
DOME_ANGLE = {"heron": -90, "lantern": -18, "seed": 54, "anvil": 126, "kite": 198}


def glyph(name: str, x: float, y: float, size: float, color: str = INK, width: float = 6,
          mirrored_view: bool = False) -> str:
    """A glyph at (x, y) (top-left), size px. mirrored_view draws it as seen in a mirror."""
    path, mirrored = GLYPHS[name]
    flip = mirrored != mirrored_view
    s = size / 100
    tf = (f"translate({x + size:g} {y:g}) scale({-s:g} {s:g})" if flip else f"translate({x:g} {y:g}) scale({s:g})")
    return (f'<path d="{path}" transform="{tf}" fill="none" stroke="{color}" stroke-width="{width / s:g}" '
            f'stroke-linecap="round" stroke-linejoin="round"/>')


def constellation(key: str, cx: float, cy: float, scale: float = 1.0, lines: bool = True, color: str = INK,
                  star: str = "#f3d68e", r: float = 3.2, flip: bool = False) -> str:
    pts, edges = STARS[key]
    p = [(cx + (-x if flip else x) * scale, cy + y * scale) for x, y in pts]
    out = []
    if lines:
        out += [f'<line x1="{p[a][0]:g}" y1="{p[a][1]:g}" x2="{p[b][0]:g}" y2="{p[b][1]:g}" stroke="{color}" '
                f'stroke-width="1.2" stroke-dasharray="3 3" opacity=".7"/>' for a, b in edges]
    out += [f'<circle cx="{x:g}" cy="{y:g}" r="{r:g}" fill="{star}" stroke="{color}" stroke-width="1"/>' for x, y in p]
    return "".join(out)


def note_staff(tone: str, x: float, y: float, w: float = 120, color: str = INK) -> str:
    """A five-line staff with one whole note at the pitch (treble clef, middle C below the staff)."""
    steps = {"C": -2, "D": -1, "E": 0, "F": 1, "G": 2, "A": 3, "B": 4}  # 0 = bottom line (E4)
    lines = "".join(f'<line x1="{x:g}" y1="{y + i * 9:g}" x2="{x + w:g}" y2="{y + i * 9:g}" stroke="{color}" '
                    f'stroke-width="1"/>' for i in range(5))
    ny = y + 36 - steps[tone] * 4.5
    ledger = (f'<line x1="{x + w / 2 - 12:g}" y1="{y + 45:g}" x2="{x + w / 2 + 12:g}" y2="{y + 45:g}" '
              f'stroke="{color}" stroke-width="1"/>') if tone == "C" else ""
    head = (f'<ellipse cx="{x + w / 2:g}" cy="{ny:g}" rx="7" ry="4.8" fill="none" stroke="{color}" stroke-width="2.4" '
            f'transform="rotate(-20 {x + w / 2:g} {ny:g})"/>')
    return lines + ledger + head


# ---------------------------------------------------------------------------------------------------------------
# Handouts
# ---------------------------------------------------------------------------------------------------------------
def page(w, h, body, pre, tilt=-1.2, bg="#2a1d12") -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}"><defs><filter id="{pre}-age">'
            f'<feTurbulence type="fractalNoise" baseFrequency=".02" numOctaves="3" seed="11"/>'
            f'<feColorMatrix values="0 0 0 0 .45  0 0 0 0 .3  0 0 0 0 .12  0 0 0 .3 0"/>'
            f'<feComposite in2="SourceGraphic" operator="in"/></filter></defs>'
            f'<rect width="{w}" height="{h}" fill="{bg}"/>'
            f'<g transform="rotate({tilt} {w / 2} {h / 2})"><rect x="30" y="24" width="{w - 60}" height="{h - 48}" fill="#ecdcb8"/>'
            f'<rect x="30" y="24" width="{w - 60}" height="{h - 48}" fill="#000" filter="url(#{pre}-age)"/>'
            f'{body}</g></svg>\n')


def text_lines(lines, x, y, size=21, gap=31, italic=False) -> str:
    st = ' font-style="italic"' if italic else ""
    return "".join(f'<text x="{x}" y="{y + i * gap}" font-family="{FONT}" font-size="{size}" fill="{INK}"{st}>{escape(t)}</text>'
                   for i, t in enumerate(lines))


JOURNALS = {
    "ice": ("Memory never lies — but it never changes.",
            ["I froze this world to keep it, and it kept", "everything: the telescopes, the snow, the", "last night I looked at the stars here.",
             "The heart of the machine is the same.", "The innermost ring holds what was.", "It is already right. Do not turn it."]),
    "fire": ("To understand truth, one must allow it to change.",
             ["Nothing leaves the fire as it went in.", "The molds taught me: to cast a flame you", "must carve the tide; to cast the wind,",
              "carve the stone. Only ice comes out as", "ice. So it is with my rings: each one", "wakes as the opposite of what you set."]),
    "air": ("There are no hidden paths. Only hidden viewpoints.",
            ["The monks painted their floors for the sky", "to read. I have done the same at home:", "the answer is above the Concordance,",
             "and no one standing beside it will ever", "see the whole of it. Climb. Look down.", "Then look again."]),
    "earth": ("Nothing is solved quickly.",
              ["Each bed I tend wakes the one beside it,", "and pushes it a season on. Plant them", "all at once and the garden undoes you.",
               "Begin at the center. Set one, wake it,", "and only then set the next — outward,", "ring by ring, as roots grow."]),
    "water": ("The world is never seen directly.",
              ["What I painted on the dome is written", "backwards, as a mirror writes. Read it", "in the still pool and it shows what the",
               "rings must become. Read it directly and", "it shows what you must set — for the", "fire turns every glyph to its twin."]),
}


def journal(element: str):
    const, tone, ring, target = next((c, t, r, g) for e, c, t, r, g in AGES if e == element)
    quote, lines = JOURNALS[element]
    body = (text_lines(["from the Cartographer’s journal"], 70, 82, 24, italic=True)
            + f'<line x1="70" y1="96" x2="560" y2="96" stroke="{BRASS}"/>'
            + text_lines([f"“{quote}”"], 70, 140, 22, italic=True)
            + text_lines(lines, 70, 190, 20, 30)
            + glyph(element, 80, 400, 110, INK, 7)
            + text_lines([f"the {element} glyph"], 82, 540, 15, italic=True)
            + f'<rect x="230" y="395" width="170" height="150" fill="#1d2440" rx="6"/>'
            + constellation(const, 315, 470, 1.4, True, "#c9d1f0")
            + text_lines([CONSTELLATION_NAME[const]], 255, 565, 16, italic=True)
            + note_staff(tone, 430, 440, 120)
            + text_lines([f"its voice: {tone}"], 445, 530, 15, italic=True)
            + text_lines(["— E."], 500, 620, 22, italic=True))
    (ROOT / "handouts" / f"journal-{element}.svg").write_text(page(620, 680, body, f"j{element}"), encoding="utf-8")


def ice_mirrors():
    body = (text_lines(["Notes on the mirror terrace"], 70, 80, 24, italic=True)
            + '<circle cx="110" cy="190" r="26" fill="#f3d68e" stroke="#3a2816"/>'
            + text_lines(["sun (east, low)"], 70, 240, 15, italic=True)
            + "".join(f'<g transform="translate({x} {y}) rotate({a})"><rect x="-30" y="-6" width="60" height="12" '
                      f'fill="#cfe6f2" stroke="{INK}" stroke-width="2"/></g><text x="{x - 6}" y="{y + 34}" '
                      f'font-family="{FONT}" font-size="20">{n}</text>' for x, y, a, n in
                      [(250, 190, 30, "A"), (420, 300, -20, "B"), (260, 420, 60, "C")])
            + text_lines(["A takes the sun. B looks to the Hall,", "or up to the Dome. C looks down, to the dam.",
                          "A moment of light melts a wall. Too long,", "and it melts the floor beneath, and the hall",
                          "drowns. Light it, then let it go dark."], 70, 500, 19, 28))
    (ROOT / "handouts" / "ice-mirrors.svg").write_text(page(560, 680, body, "im"), encoding="utf-8")


def fire_molds():
    body = (text_lines(["The five molds of the Bell Foundry"], 70, 80, 24, italic=True)
            + "".join(f'<rect x="{70 + i * 96}" y="120" width="80" height="80" fill="#b08a55" stroke="{INK}" '
                      f'stroke-width="2"/>' + glyph(e, 80 + i * 96, 130, 60, "#f3ead2", 5) for i, (e, *_r) in enumerate(AGES))
            + text_lines(["Cast in the mold, the bronze comes out", "carved the other way: what the mold holds",
                          "as a hollow, the bell wears as a shape."], 70, 250, 19, 28)
            + text_lines(["“To cast the flame, carve the tide.”"], 70, 370, 21, italic=True)
            + glyph("water", 120, 410, 90, INK, 6) + '<text x="235" y="470" font-size="40" font-family="serif">→</text>'
            + glyph("fire", 300, 410, 90, INK, 6)
            + text_lines(["Mold  →  bell"], 160, 540, 17, italic=True)
            + text_lines(["The anvil above the crucible bears the", "flame. Only a flame bell will wake it."], 70, 590, 19, 28))
    (ROOT / "handouts" / "fire-molds.svg").write_text(page(600, 680, body, "fm"), encoding="utf-8")


def air_map_handout():
    # The monks' map is drawn with south at the top; the wheel marks read correctly only when turned over.
    inner = (f'<g transform="rotate(180 280 330)">'
             + text_lines(["Of the wheels and their towers"], 120, 140, 20, italic=True)
             + "".join(f'<circle cx="{150 + i * 110}" cy="230" r="22" fill="#c9b285" stroke="{INK}" stroke-width="2"/>'
                       f'<text x="{150 + i * 110}" y="237" font-size="18" text-anchor="middle" font-family="{FONT}">{n}</text>'
                       for i, n in enumerate(["I", "II", "III"]))
             + "".join(f'<line x1="{150 + i * 110}" y1="254" x2="{x2}" y2="{y2}" stroke="{INK}" stroke-width="1.5" '
                       f'stroke-dasharray="4 4"/>' for i, (x2, y2) in enumerate([(380, 420), (160, 420), (270, 520)]))
             + f'<text x="380" y="445" text-anchor="middle" font-family="{FONT}" font-size="18">North ●●</text>'
             + f'<text x="160" y="445" text-anchor="middle" font-family="{FONT}" font-size="18">South ●●●</text>'
             + f'<text x="270" y="545" text-anchor="middle" font-family="{FONT}" font-size="18">East ●</text>'
             + text_lines(["Turn each as many times as it has stars,", "then sit in the listening seat."], 110, 600, 17, 26)
             + "</g>")
    body = inner + text_lines(["(a monk’s map, found face-down)"], 60, 650, 14, italic=True)
    (ROOT / "handouts" / "air-map.svg").write_text(page(560, 680, body, "am", 0.8), encoding="utf-8")


def earth_calendar():
    seasons = ["Rain", "Sun", "Rain & Sun", "Growth", "Rest"]
    body = (text_lines(["The Calendar Stone (rubbing)"], 70, 80, 24, italic=True)
            + "".join(f'<circle cx="300" cy="310" r="{r}" fill="none" stroke="{INK}" stroke-width="2"/>'
                      for r in (40, 75, 110, 145, 180))
            + "".join(f'<text x="{300 + 160 * math.cos(math.radians(-90 + i * 72)):.0f}" '
                      f'y="{315 + 160 * math.sin(math.radians(-90 + i * 72)):.0f}" text-anchor="middle" '
                      f'font-family="{FONT}" font-size="16">{escape(s)}</text>' for i, s in enumerate(seasons))
            + '<circle cx="300" cy="310" r="10" fill="#7a5a36"/>'
            + text_lines(["Each wheel, turned, turns the one outside it", "a season on. The tree wakes only when all",
                          "five show Rest. Begin at the heart."], 70, 540, 19, 28)
            + text_lines(["Rain, then Sun, then both: so the beds grow."], 70, 640, 17, italic=True))
    (ROOT / "handouts" / "earth-calendar.svg").write_text(page(600, 700, body, "ec"), encoding="utf-8")


def water_alphabet():
    msg = "SEE IT ONLY IN ITS REFLECTION"
    body = (text_lines(["Letters cut into the rim of the Moon Pool"], 70, 80, 22, italic=True)
            + f'<g transform="translate(560 0) scale(-1 1)"><text x="70" y="180" font-family="{FONT}" font-size="30" '
              f'letter-spacing="3" fill="{INK}">{msg}</text></g>'
            + text_lines(["The mirror-writer’s alphabet:"], 70, 260, 19, italic=True)
            + "".join(f'<g transform="translate({140 + (i % 9) * 46} {300 + (i // 9) * 56}) scale(-1 1)">'
                      f'<text x="0" y="0" font-family="{FONT}" font-size="28" fill="{INK}">{ch}</text></g>'
                      f'<text x="{122 + (i % 9) * 46}" y="{322 + (i // 9) * 56}" font-family="{FONT}" font-size="13" '
                      f'fill="#6b5236">{ch}</text>' for i, ch in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
            + text_lines(["Below the letters, two glyphs, each the", "other’s reflection:"], 70, 500, 19, 28)
            + glyph("fire", 120, 550, 80, INK, 6) + '<line x1="250" y1="540" x2="250" y2="640" stroke="#4d6f86" '
            'stroke-dasharray="4 4"/>' + glyph("water", 300, 550, 80, INK, 6))
    (ROOT / "handouts" / "water-alphabet.svg").write_text(page(560, 680, body, "wa"), encoding="utf-8")


def concordance_diagram():
    rings = "".join(f'<circle cx="400" cy="330" r="{r}" fill="none" stroke="{BRASS}" stroke-width="16"/>'
                    for r in (50, 95, 140, 185, 230))
    dots = ""
    for elem, const, tone, ring, target in AGES:
        r = 5 + ring * 45
        dots += constellation(const, 400, 330 - r, .28 + ring * .02, False, INK, "#fff3c4", 2.6)
    sockets = "".join(glyph(e, 160 + i * 110, 600, 46, INK, 5) for i, (e, *_r) in enumerate(AGES))
    body = (f'<rect width="800" height="700" fill="#1c140d"/>' + rings + dots
            + '<circle cx="400" cy="330" r="22" fill="#cfe6f2" stroke="#3a2816" stroke-width="2"/>'
            + "".join(f'<rect x="{150 + i * 110}" y="592" width="66" height="62" fill="none" stroke="{BRASS}" '
                      f'stroke-width="2"/>' for i in range(5)) + sockets.replace(INK, "#e9d8b4")
            + f'<text x="400" y="40" text-anchor="middle" font-family="{FONT}" font-size="26" fill="#e9d8b4">The Concordance</text>'
            + f'<text x="400" y="680" text-anchor="middle" font-family="{FONT}" font-size="16" font-style="italic" '
              f'fill="#c9b285">five rings, star-marked rims, five empty sockets</text>')
    (ROOT / "handouts" / "concordance.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 700">{body}</svg>\n', encoding="utf-8")


def dome(reflected: bool):
    """The dome painting. Painted mirrored; reflected=True is the view in the still pool (the true reading)."""
    cx, cy, R = 400, 360, 230
    parts = [f'<rect width="800" height="760" fill="#120e1c"/>',
             f'<circle cx="{cx}" cy="{cy}" r="300" fill="#1d2440" stroke="#8c6a2c" stroke-width="6"/>']
    by_const = {c: (e, g) for e, c, t, r, g in AGES}
    for const, ang in DOME_ANGLE.items():
        a = math.radians(ang if not reflected else 180 - ang)
        x, y = cx + R * math.cos(a), cy + R * math.sin(a)
        elem, target = by_const[const]
        parts.append(constellation(const, x, y - 18, 1.0, True, "#c9d1f0", flip=reflected))
        # Painted mirrored: directly you see the mirror image of the target (= its opposite); reflected, the target.
        parts.append(glyph(target, x - 26, y + 26, 52, "#f3d68e", 5, mirrored_view=not reflected))
    parts.append(f'<circle cx="{cx}" cy="{cy}" r="40" fill="none" stroke="#c9d1f0" stroke-dasharray="4 6"/>')
    caption = "the dome, seen in the still pool" if reflected else "the dome, seen directly from the balcony"
    parts.append(f'<text x="400" y="735" text-anchor="middle" font-family="{FONT}" font-size="20" font-style="italic" '
                 f'fill="#e9d8b4">{caption}</text>')
    (ROOT / "handouts" / f"dome-{'reflection' if reflected else 'direct'}.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 760">{"".join(parts)}</svg>\n',
        encoding="utf-8")


def letter():
    body = (text_lines(["To whoever wakes the Concordance —"], 70, 90, 23, italic=True)
            + text_lines(["If it sings, you have learned what I learned:", "to keep, to change, to look, to wait, and to",
                          "see the world in its reflection. The machine", "does not open a door. It writes one.",
                          "", "On my desk is a Book with no Age in it yet.", "The Concordance will hold any world you",
                          "write there steady, as long as all five rules", "are honored together. I could not finish it",
                          "alone; I was never patient enough.", "", "It is yours now. Write carefully.",
                          "Write together."], 70, 150, 20, 30)
            + text_lines(["— Ereva, Cartographer"], 330, 610, 22, italic=True))
    (ROOT / "handouts" / "cartographer-letter.svg").write_text(page(620, 680, body, "cl"), encoding="utf-8")


def linking(element: str, sky: tuple[str, str], sea: str, fig: str):
    """An animated Linking-panel handout for each Age."""
    body = (f'<defs><linearGradient id="lk{element}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{sky[0]}"/>'
            f'<stop offset="1" stop-color="{sky[1]}"/></linearGradient><clipPath id="lc{element}"><rect x="120" y="70" '
            f'width="400" height="280" rx="6"/></clipPath></defs>'
            f'<rect width="640" height="440" fill="#1a120b"/><path d="M40 30 Q320 60 600 30 L600 420 Q320 390 40 420 Z" '
            f'fill="#e9d8b4" stroke="#5b3518" stroke-width="6"/><line x1="320" y1="45" x2="320" y2="405" stroke="#b8925a" stroke-width="2"/>'
            f'<g clip-path="url(#lc{element})"><rect x="120" y="70" width="400" height="280" fill="url(#lk{element})"/>'
            f'<rect x="120" y="270" width="400" height="80" fill="{sea}"/>{fig}</g>'
            f'<rect x="120" y="70" width="400" height="280" rx="6" fill="none" stroke="#3a2816" stroke-width="4"/>'
            f'<rect x="120" y="70" width="400" height="280" rx="6" fill="#fff" opacity="0">'
            f'<animate attributeName="opacity" values="0;.14;0" dur="4s" repeatCount="indefinite"/></rect>')
    (ROOT / "handouts" / f"link-{element}.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 440">{body}</svg>\n', encoding="utf-8")


def all_links():
    snow = "".join(f'<circle cx="{130 + (i * 53) % 380}" cy="80" r="2" fill="#fff"><animate attributeName="cy" '
                   f'values="70;350" dur="{4 + i % 4}s" begin="{(i % 7) * .5}s" repeatCount="indefinite"/></circle>'
                   for i in range(24))
    linking("ice", ("#2e4a6a", "#bcd6e6"), "#dfeaf0",
            '<path d="M380 270 L380 190 A 50 50 0 0 1 480 190 L480 270 Z" fill="#eef4f6" stroke="#3a2816" stroke-width="2"/>'
            '<line x1="430" y1="150" x2="470" y2="110" stroke="#c9b285" stroke-width="8"/>' + snow)
    linking("fire", ("#2a0f08", "#b0461c"), "#d0602a",
            '<g fill="#3a2816"><circle cx="230" cy="220" r="40"/><circle cx="300" cy="245" r="26"/></g>'
            '<g transform="translate(230 220)"><circle r="40" fill="none" stroke="#c49a45" stroke-width="6" '
            'stroke-dasharray="10 8"><animateTransform attributeName="transform" type="rotate" values="0;360" dur="6s" '
            'repeatCount="indefinite"/></circle></g>'
            '<path d="M120 300 q 50 -12 100 0 t 100 0 t 100 0 t 100 0" stroke="#f3a14a" stroke-width="6" fill="none">'
            '<animate attributeName="opacity" values=".5;1;.5" dur="1.6s" repeatCount="indefinite"/></path>')
    linking("air", ("#8fb4d8", "#e8eef4"), "#dfe6ee",
            '<path d="M180 230 q 40 30 90 0 l -10 -20 l -70 0 Z" fill="#c9b285" stroke="#3a2816"/>'
            '<path d="M380 180 q 40 30 90 0 l -10 -20 l -70 0 Z" fill="#c9b285" stroke="#3a2816"/>'
            '<rect x="410" y="110" width="20" height="50" fill="#efe2c2" stroke="#3a2816"/>'
            '<g transform="translate(225 205)"><g><line x1="0" y1="-26" x2="0" y2="26" stroke="#3a2816" stroke-width="3"/>'
            '<line x1="-26" y1="0" x2="26" y2="0" stroke="#3a2816" stroke-width="3"/><animateTransform '
            'attributeName="transform" type="rotate" values="0;360" dur="3s" repeatCount="indefinite"/></g></g>')
    linking("earth", ("#6f8f4f", "#d9e3b0"), "#5d6f3a",
            '<path d="M320 350 C 300 280, 260 260, 280 190 C 300 140, 360 140, 360 190 C 370 260, 340 280, 330 350 Z" '
            'fill="#7a5a36" stroke="#3a2816"/><circle cx="320" cy="150" r="70" fill="#7f9f55" opacity=".85">'
            '<animate attributeName="r" values="66;72;66" dur="5s" repeatCount="indefinite"/></circle>')
    linking("water", ("#141a33", "#3d4a7a"), "#22305a",
            '<circle cx="420" cy="140" r="26" fill="#f5f0e3"/><ellipse cx="420" cy="300" rx="26" ry="8" fill="#f5f0e3" '
            'opacity=".5"><animate attributeName="rx" values="20;30;20" dur="3s" repeatCount="indefinite"/></ellipse>'
            '<path d="M180 270 L180 170 A 40 40 0 0 1 260 170 L260 270" fill="none" stroke="#c9d1f0" stroke-width="4"/>'
            '<path d="M180 270 L180 330 A 40 40 0 0 0 260 330 L260 270" fill="none" stroke="#c9d1f0" stroke-width="3" opacity=".4"/>')


# ---------------------------------------------------------------------------------------------------------------
# Lobby book: cover logo and linking-window preview
# ---------------------------------------------------------------------------------------------------------------
def cover_logo():
    """Five rings with the five glyphs around them: the Concordance, in gold leaf."""
    gold = "#f3d68e"
    parts = [f'<circle cx="100" cy="100" r="{r}" fill="none" stroke="{gold}" stroke-width="{3 if r < 70 else 4}" '
             f'opacity="{.55 + r / 300:.2f}"/>' for r in (14, 28, 42, 56, 70)]
    for i, (e, *_r) in enumerate(AGES):
        a = math.radians(-90 + i * 72)
        parts.append(glyph(e, 100 + 86 * math.cos(a) - 13, 100 + 86 * math.sin(a) - 13, 26, gold, 6))
    parts.append(f'<circle cx="100" cy="100" r="5" fill="{gold}"/>')
    (ROOT / "handouts" / "cover.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200">{"".join(parts)}</svg>\n', encoding="utf-8")


def preview():
    """The linking window: the Sanctuary's dome sky turning above the five rings, one Age-color after another."""
    rings = "".join(
        f'<g transform="translate(200 300)"><ellipse rx="{40 + i * 26}" ry="{12 + i * 8}" fill="none" stroke="#c49a45" '
        f'stroke-width="3" opacity=".85"><animateTransform attributeName="transform" type="rotate" '
        f'values="0;{360 if i % 2 else -360}" dur="{14 + i * 4}s" repeatCount="indefinite"/></ellipse></g>'
        for i in range(5))
    stars = "".join(
        constellation(c, 200 + 120 * math.cos(math.radians(a)), 120 + 60 * math.sin(math.radians(a)), .9, True,
                      "#c9d1f0") for c, a in DOME_ANGLE.items())
    hues = ";".join(["#24405e", "#5e2412", "#5a7090", "#3a5a2a", "#1c2448", "#24405e"])
    body = (f'<rect width="400" height="300" fill="#24405e"><animate attributeName="fill" values="{hues}" dur="12s" '
            f'repeatCount="indefinite"/></rect>'
            f'<radialGradient id="pv-glow"><stop offset="0" stop-color="#fff6d0" stop-opacity=".5"/>'
            f'<stop offset="1" stop-color="#fff6d0" stop-opacity="0"/></radialGradient>'
            f'<circle cx="200" cy="300" r="160" fill="url(#pv-glow)"/>'
            f'<g><animateTransform attributeName="transform" type="rotate" values="0 200 300;360 200 300" dur="60s" '
            f'repeatCount="indefinite"/>{stars}</g>{rings}')
    (ROOT / "handouts" / "preview.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300">{body}</svg>\n', encoding="utf-8")


if __name__ == "__main__":
    (ROOT / "maps").mkdir(exist_ok=True)
    (ROOT / "handouts").mkdir(exist_ok=True)
    import maps
    maps.render_all()  # illustrated maps; also syncs area outlines into campaign.yaml
    for e, *_rest in AGES:
        journal(e)
    ice_mirrors(); fire_molds(); air_map_handout(); earth_calendar(); water_alphabet()
    concordance_diagram(); dome(False); dome(True); letter(); all_links(); cover_logo(); preview()
    print("maps:", sorted(p.name for p in (ROOT / "maps").iterdir()))
    print("handouts:", sorted(p.name for p in (ROOT / "handouts").iterdir()))
