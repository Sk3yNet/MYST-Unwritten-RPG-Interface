"""Illustrated 3/4-view maps for "The Concordance": stone platforms and walkways over themed terrain, numbered
markers, mist-colored fog. Run through art.py, which also writes each area's outline back into campaign.yaml.

Each map is a list of areas; each area draws its own structure (and the walkway that leads to it) inside a
<g data-area> group, so the server can leave unrevealed areas out of a player's copy entirely.
"""
from __future__ import annotations

import math
import random
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
W, H = 1000, 700
INK = "#21180f"
FONT = "IM Fell English, Georgia, serif"


# ---------------------------------------------------------------------------------------------------------------
# Themes
# ---------------------------------------------------------------------------------------------------------------
THEMES = {
    "hub":   {"bg": "#cdbb98", "bg2": "#a8916b", "top": "#cbb894", "side": "#86704f", "trim": "#5b4630",
              "fog": "#d8c9a6", "banner": "#3b2a1a", "accent": "#c49a45"},
    "ice":   {"bg": "#b9cddb", "bg2": "#7f9bb2", "top": "#d4e0e8", "side": "#7e95a8", "trim": "#4b6175",
              "fog": "#dfe9f0", "banner": "#1f3a55", "accent": "#bfe3f5"},
    "fire":  {"bg": "#3a1e14", "bg2": "#1c0e09", "top": "#6d5a4e", "side": "#3d2f28", "trim": "#1e1410",
              "fog": "#3b2a22", "banner": "#5e1a0e", "accent": "#ff8a2a"},
    "air":   {"bg": "#b7d0e6", "bg2": "#e7eff6", "top": "#d6cdb4", "side": "#8d7d65", "trim": "#5c4d3a",
              "fog": "#eef3f8", "banner": "#2c4a63", "accent": "#e9f2fa"},
    "earth": {"bg": "#3d5a2a", "bg2": "#253b18", "top": "#b3aa8e", "side": "#6f6650", "trim": "#3f3a2c",
              "fog": "#4a5e38", "banner": "#33461f", "accent": "#a6c96a"},
    "water": {"bg": "#14394a", "bg2": "#0a2230", "top": "#8d9ea7", "side": "#4e5f68", "trim": "#2b3940",
              "fog": "#2a4a5a", "banner": "#163f57", "accent": "#bfe0ee"},
}


class Map:
    def __init__(self, map_id: str, theme: str, title: str, subtitle: str, seed: int):
        self.id, self.t, self.title, self.subtitle = map_id, THEMES[theme], title, subtitle
        self.theme = theme
        self.p = f"cm{map_id[:3]}"
        self.rng = random.Random(seed)
        self.base: list[str] = []
        self.areas: dict[str, list[str]] = {}
        self.shapes: dict[str, str] = {}
        self.numbers: dict[str, int] = {}

    # -- structures ---------------------------------------------------------------------------------------------
    def shadow_ellipse(self, cx, cy, rx, ry, op=.45):
        return (f'<ellipse cx="{cx + 12:g}" cy="{cy + 14:g}" rx="{rx:g}" ry="{ry:g}" fill="#000" opacity="{op}" '
                f'filter="url(#{self.p}-blur)"/>')

    def disc(self, cx, cy, rx, ry, h, top=None, side=None, tiles=True, rings=1):
        """A round stone platform seen from above and in front: top ellipse, banded side, rim."""
        t = self.t
        top, side = top or t["top"], side or t["side"]
        out = [self.shadow_ellipse(cx, cy + h, rx, ry)]
        out.append(f'<path d="M{cx - rx:g} {cy:g} L{cx - rx:g} {cy + h:g} A{rx:g} {ry:g} 0 0 0 {cx + rx:g} {cy + h:g} '
                   f'L{cx + rx:g} {cy:g} Z" fill="{side}" stroke="{INK}" stroke-width="2"/>')
        # block joints on the side
        for i in range(1, 14):
            a = math.pi * i / 14
            x = cx - rx * math.cos(a)
            yb = cy + ry * math.sin(a)
            out.append(f'<line x1="{x:g}" y1="{yb:g}" x2="{x:g}" y2="{yb + h:g}" stroke="{INK}" stroke-width=".8" opacity=".45"/>')
        out.append(f'<path d="M{cx - rx:g} {cy + h * .5:g} A{rx:g} {ry:g} 0 0 0 {cx + rx:g} {cy + h * .5:g}" fill="none" '
                   f'stroke="{INK}" stroke-width=".8" opacity=".4"/>')
        out.append(f'<ellipse cx="{cx:g}" cy="{cy:g}" rx="{rx:g}" ry="{ry:g}" fill="{top}" stroke="{INK}" stroke-width="2.5"/>')
        if tiles:
            out.append(f'<ellipse cx="{cx:g}" cy="{cy:g}" rx="{rx:g}" ry="{ry:g}" fill="url(#{self.p}-tiles)" opacity=".55"/>')
        for k in range(1, rings + 1):
            f = 1 - k * .18
            out.append(f'<ellipse cx="{cx:g}" cy="{cy:g}" rx="{rx * f:g}" ry="{ry * f:g}" fill="none" stroke="{INK}" '
                       f'stroke-width="1.3" opacity=".5"/>')
        out.append(f'<ellipse cx="{cx:g}" cy="{cy - 1:g}" rx="{rx - 3:g}" ry="{ry - 2:g}" fill="none" stroke="#fff" '
                   f'stroke-width="1.5" opacity=".25"/>')
        return "".join(out)

    def slab(self, x, y, w, d, h, top=None, side=None, tiles=True):
        """A rectangular stone terrace: top face, front face, a lit edge."""
        t = self.t
        top, side = top or t["top"], side or t["side"]
        return (f'<rect x="{x + 12:g}" y="{y + 16:g}" width="{w:g}" height="{d + h:g}" fill="#000" opacity=".4" '
                f'filter="url(#{self.p}-blur)"/>'
                f'<rect x="{x:g}" y="{y + d:g}" width="{w:g}" height="{h:g}" fill="{side}" stroke="{INK}" stroke-width="2"/>'
                + "".join(f'<line x1="{x + i * w / 9:g}" y1="{y + d:g}" x2="{x + i * w / 9:g}" y2="{y + d + h:g}" '
                          f'stroke="{INK}" stroke-width=".8" opacity=".45"/>' for i in range(1, 9))
                + f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{d:g}" fill="{top}" stroke="{INK}" stroke-width="2.5"/>'
                + (f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{d:g}" fill="url(#{self.p}-tiles)" opacity=".55"/>' if tiles else "")
                + f'<line x1="{x + 2:g}" y1="{y + 2:g}" x2="{x + w - 2:g}" y2="{y + 2:g}" stroke="#fff" stroke-width="1.5" opacity=".3"/>')

    def walls(self, x, y, w, d, hgt=16):
        """Low parapet walls around a slab's back and sides, with corner posts."""
        t = self.t
        out = [f'<rect x="{x:g}" y="{y - hgt:g}" width="{w:g}" height="{hgt:g}" fill="{t["side"]}" stroke="{INK}" stroke-width="1.5"/>',
               f'<rect x="{x:g}" y="{y - hgt - 4:g}" width="{w:g}" height="5" fill="{t["top"]}" stroke="{INK}" stroke-width="1.2"/>']
        for px in (x, x + w):
            for py in (y, y + d):
                out.append(self.post(px, py))
        return "".join(out)

    def post(self, x, y, r=7, hgt=22):
        t = self.t
        return (f'<rect x="{x - r:g}" y="{y - hgt:g}" width="{2 * r:g}" height="{hgt:g}" fill="{t["side"]}" stroke="{INK}" stroke-width="1.5"/>'
                f'<rect x="{x - r - 2:g}" y="{y - hgt - 5:g}" width="{2 * r + 4:g}" height="6" fill="{t["top"]}" stroke="{INK}" stroke-width="1.2"/>')

    def tower(self, cx, base, r, hgt, roof=None, cone=1.3):
        """A round tower: body, banded courses, windows, conical roof with a finial."""
        t = self.t
        roof = roof or t["trim"]
        top = base - hgt
        out = [self.shadow_ellipse(cx + 18, base, r * 1.6, r * .5, .35),
               f'<path d="M{cx - r:g} {top:g} L{cx - r:g} {base:g} A{r:g} {r * .4:g} 0 0 0 {cx + r:g} {base:g} L{cx + r:g} {top:g} Z" '
               f'fill="{t["side"]}" stroke="{INK}" stroke-width="2"/>',
               f'<path d="M{cx - r:g} {top:g} L{cx - r:g} {base:g} A{r:g} {r * .4:g} 0 0 0 {cx - r * .2:g} {base + r * .39:g} '
               f'L{cx - r * .2:g} {top + r * .39:g} Z" fill="#fff" opacity=".12"/>']
        for k in range(1, int(hgt // 22) + 1):
            yk = top + k * 22
            if yk < base - 4:
                out.append(f'<path d="M{cx - r:g} {yk:g} A{r:g} {r * .4:g} 0 0 0 {cx + r:g} {yk:g}" fill="none" stroke="{INK}" '
                           f'stroke-width=".8" opacity=".5"/>')
        for k in range(int(hgt // 34)):
            wy = top + 14 + k * 34
            out.append(f'<rect x="{cx - 3:g}" y="{wy:g}" width="6" height="11" rx="3" fill="#1a1410"/>'
                       f'<rect x="{cx - 1.5:g}" y="{wy + 2:g}" width="3" height="6" rx="1.5" fill="#f3c46a" opacity=".85"/>')
        out.append(f'<ellipse cx="{cx:g}" cy="{top:g}" rx="{r + 3:g}" ry="{(r + 3) * .4:g}" fill="{t["top"]}" stroke="{INK}" stroke-width="2"/>')
        out.append(f'<path d="M{cx - r - 4:g} {top:g} L{cx:g} {top - r * cone * 1.6:g} L{cx + r + 4:g} {top:g} '
                   f'A{r + 4:g} {(r + 4) * .4:g} 0 0 1 {cx - r - 4:g} {top:g} Z" fill="{roof}" stroke="{INK}" stroke-width="2"/>')
        out.append(f'<path d="M{cx - r * .2:g} {top - 2:g} L{cx:g} {top - r * cone * 1.6:g} L{cx - r - 4:g} {top:g} Z" fill="#fff" opacity=".18"/>')
        out.append(f'<line x1="{cx:g}" y1="{top - r * cone * 1.6:g}" x2="{cx:g}" y2="{top - r * cone * 1.6 - 12:g}" stroke="{INK}" stroke-width="2"/>'
                   f'<circle cx="{cx:g}" cy="{top - r * cone * 1.6 - 13:g}" r="3" fill="{t["accent"]}" stroke="{INK}"/>')
        return "".join(out)

    def walk(self, pts, width=22, rope=False):
        """A walkway or bridge along points: shadow, edge, deck, planks or flagstones, rails."""
        t = self.t
        d = "M" + " L".join(f"{x:g} {y:g}" for x, y in pts)
        if rope and len(pts) == 2:
            (x1, y1), (x2, y2) = pts
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2 + 26
            d = f"M{x1:g} {y1:g} Q{mx:g} {my:g} {x2:g} {y2:g}"
        deck = "#9a7a52" if rope else t["top"]
        out = [f'<path d="{d}" fill="none" stroke="#000" stroke-width="{width + 6}" opacity=".35" '
               f'transform="translate(10 16)" filter="url(#{self.p}-blur)" stroke-linecap="round"/>',
               f'<path d="{d}" fill="none" stroke="{INK}" stroke-width="{width + 5}" stroke-linecap="round" stroke-linejoin="round"/>',
               f'<path d="{d}" fill="none" stroke="{deck}" stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round"/>',
               f'<path d="{d}" fill="none" stroke="{INK}" stroke-width="{width}" stroke-dasharray="1.2 {7 if rope else 13}" '
               f'opacity=".55" stroke-linejoin="round"/>']
        if rope:
            out.append(f'<path d="{d}" fill="none" stroke="#3b2a1a" stroke-width="{width + 9}" stroke-dasharray="2 18" opacity=".7"/>')
        else:
            out.append(f'<path d="{d}" fill="none" stroke="#fff" stroke-width="{width - 10}" opacity=".12" stroke-linejoin="round"/>')
        return "".join(out)

    def marker(self, n, x, y):
        return (f'<g class="map-marker"><circle cx="{x:g}" cy="{y + 2:g}" r="19" fill="#000" opacity=".35"/>'
                f'<circle cx="{x:g}" cy="{y:g}" r="18" fill="#f6efe0" stroke="{INK}" stroke-width="3"/>'
                f'<circle cx="{x:g}" cy="{y:g}" r="13.5" fill="none" stroke="{INK}" stroke-width="1"/>'
                f'<text x="{x:g}" y="{y + 7:g}" text-anchor="middle" font-family="Georgia, serif" font-weight="bold" '
                f'font-size="20" fill="{INK}">{n}</text></g>')

    # -- areas --------------------------------------------------------------------------------------------------
    def area(self, aid: str, shape: str, body: str, marker: tuple[float, float]):
        self.areas[aid] = [body, self.marker(self.numbers[aid], *marker)]
        self.shapes[aid] = shape

    # -- output -------------------------------------------------------------------------------------------------
    def defs(self) -> str:
        t, p = self.t, self.p
        return (f'<defs>'
                f'<filter id="{p}-blur" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="7"/></filter>'
                f'<filter id="{p}-glow" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="5"/></filter>'
                f'<filter id="{p}-tex" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" '
                f'baseFrequency=".9" numOctaves="2" seed="4"/><feColorMatrix values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 .55 -.18"/></filter>'
                f'<filter id="{p}-clouds" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" '
                f'baseFrequency=".008 .014" numOctaves="4" seed="{self.rng.randint(1, 99)}"/>'
                f'<feColorMatrix values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 1.6 -.75"/></filter>'
                f'<pattern id="{p}-tiles" width="26" height="14" patternUnits="userSpaceOnUse">'
                f'<path d="M0 13.5 H26 M13 0 V14" stroke="{INK}" stroke-width=".7" opacity=".55"/></pattern>'
                f'<pattern id="{p}-ripples" width="60" height="22" patternUnits="userSpaceOnUse">'
                f'<path d="M0 11 q15 -7 30 0 t30 0" fill="none" stroke="#bfe0ee" stroke-width="1" opacity=".25"/></pattern>'
                f'<radialGradient id="{p}-vig" cx=".5" cy=".5" r=".75"><stop offset=".55" stop-color="#000" stop-opacity="0"/>'
                f'<stop offset="1" stop-color="#000" stop-opacity=".55"/></radialGradient>'
                f'<linearGradient id="{p}-sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{t["bg"]}"/>'
                f'<stop offset="1" stop-color="{t["bg2"]}"/></linearGradient>'
                f'</defs>')

    def banner(self) -> str:
        t = self.t
        return (f'<g class="map-banner" data-above-fog="on"><rect x="0" y="0" width="{W}" height="74" fill="{t["banner"]}"/>'
                f'<rect x="0" y="74" width="{W}" height="4" fill="#c49a45"/>'
                f'<text x="{W / 2}" y="38" text-anchor="middle" font-family="IM Fell English SC, {FONT}" font-size="30" '
                f'fill="#f6ecd6" letter-spacing="1">{self.title}</text>'
                f'<text x="{W / 2}" y="62" text-anchor="middle" font-family="{FONT}" font-size="17" font-style="italic" '
                f'fill="#e9dcc0">{self.subtitle}</text></g>'
                f'<g transform="translate(944,640)" stroke="#f1e8d4" fill="none" stroke-width="1.5" opacity=".85" data-above-fog="on">'
                f'<circle r="24" fill="#000" fill-opacity=".25"/><path d="M0 -32 L6 0 L0 32 L-6 0 Z" fill="#c49a45"/>'
                f'<text y="-36" text-anchor="middle" font-size="13" fill="#f1e8d4" stroke="none" font-family="Georgia,serif">N</text></g>'
                f'<rect x="1.5" y="1.5" width="{W - 3}" height="{H - 3}" fill="none" stroke="#2a1d10" stroke-width="3" data-above-fog="on"/>')

    def svg(self) -> str:
        parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" data-fog="{self.t["fog"]}" data-legend="on">',
                 self.defs(), "".join(self.base),
                 f'<rect width="{W}" height="{H}" fill="url(#{self.p}-vig)"/>']
        for aid, (body, marker) in self.areas.items():
            parts.append(f'<g data-area="{aid}">{body}{marker}</g>')
        parts.append(self.banner())
        parts.append("</svg>")
        return "\n".join(parts) + "\n"


def ellipse_pts(cx, cy, rx, ry, n=14):
    return " ".join(f"{cx + rx * math.cos(2 * math.pi * i / n):.0f},{cy + ry * math.sin(2 * math.pi * i / n):.0f}"
                    for i in range(n))


def rect_pts(x, y, w, h):
    return f"{x:.0f},{y:.0f} {x + w:.0f},{y:.0f} {x + w:.0f},{y + h:.0f} {x:.0f},{y + h:.0f}"


# ---------------------------------------------------------------------------------------------------------------
# Terrain
# ---------------------------------------------------------------------------------------------------------------
def ice_terrain(m: Map):
    r, t = m.rng, m.t
    m.base.append(f'<rect width="{W}" height="{H}" fill="url(#{m.p}-sky)"/>')
    m.base.append(f'<rect width="{W}" height="{H}" filter="url(#{m.p}-tex)" opacity=".35"/>')
    for _ in range(70):  # ice crags
        x, y, s = r.uniform(-20, W), r.uniform(70, H), r.uniform(18, 60)
        m.base.append(f'<path d="M{x:.0f} {y:.0f} L{x + s * .45:.0f} {y - s * 1.1:.0f} L{x + s:.0f} {y:.0f} Z" fill="#e9f1f6" '
                      f'stroke="#5d778c" stroke-width="1.2"/><path d="M{x + s * .45:.0f} {y - s * 1.1:.0f} L{x + s:.0f} {y:.0f} '
                      f'L{x + s * .55:.0f} {y:.0f} Z" fill="#8fa9bd"/>')
    for _ in range(140):
        m.base.append(f'<circle cx="{r.uniform(0, W):.0f}" cy="{r.uniform(80, H):.0f}" r="{r.uniform(.8, 2):.1f}" fill="#fff" opacity=".8"/>')


def fire_terrain(m: Map):
    r = m.rng
    m.base.append(f'<rect width="{W}" height="{H}" fill="url(#{m.p}-sky)"/>')
    m.base.append(f'<rect width="{W}" height="{H}" filter="url(#{m.p}-tex)" opacity=".6"/>')
    rivers = ["M-20 300 C 150 340, 260 250, 420 330 S 640 470, 760 420 S 930 520, 1020 500",
              "M120 700 C 180 600, 300 640, 330 560 S 520 500, 600 560 S 700 690, 760 700",
              "M600 80 C 620 160, 560 200, 640 240"]
    for d in rivers:
        m.base.append(f'<path d="{d}" fill="none" stroke="#ff6a14" stroke-width="34" opacity=".55" filter="url(#{m.p}-glow)"/>'
                      f'<path d="{d}" fill="none" stroke="#ff8a2a" stroke-width="16"/>'
                      f'<path d="{d}" fill="none" stroke="#ffd27a" stroke-width="5" opacity=".9"/>')
    for _ in range(60):  # basalt boulders
        x, y, s = r.uniform(0, W), r.uniform(80, H), r.uniform(10, 34)
        m.base.append(f'<ellipse cx="{x:.0f}" cy="{y:.0f}" rx="{s:.0f}" ry="{s * .6:.0f}" fill="#2a1a14" stroke="#120a07"/>')
    for _ in range(40):
        m.base.append(f'<circle cx="{r.uniform(0, W):.0f}" cy="{r.uniform(80, H):.0f}" r="{r.uniform(1, 2.5):.1f}" fill="#ffb35c" opacity=".7"/>')


def air_terrain(m: Map):
    r = m.rng
    m.base.append(f'<rect width="{W}" height="{H}" fill="url(#{m.p}-sky)"/>')
    m.base.append(f'<rect width="{W}" height="{H}" filter="url(#{m.p}-clouds)" opacity=".9"/>')
    for _ in range(9):  # distant islands
        x, y, s = r.uniform(0, W), r.uniform(100, H), r.uniform(14, 30)
        m.base.append(f'<path d="M{x - s:.0f} {y:.0f} Q{x:.0f} {y + s * 1.6:.0f} {x + s:.0f} {y:.0f} Z" fill="#8a9fb3" opacity=".55"/>'
                      f'<ellipse cx="{x:.0f}" cy="{y:.0f}" rx="{s:.0f}" ry="{s * .3:.0f}" fill="#a9bccd" opacity=".6"/>')


def earth_terrain(m: Map):
    r = m.rng
    m.base.append(f'<rect width="{W}" height="{H}" fill="url(#{m.p}-sky)"/>')
    for _ in range(90):  # tree crowns: clusters of leaf masses, shaded from the top-left
        x, y, s = r.uniform(-30, W + 30), r.uniform(70, H + 30), r.uniform(26, 52)
        base, hi = r.choice([("#2f5220", "#4f7d33"), ("#3a6127", "#5f8f3c"), ("#28461b", "#46702d"), ("#36592a", "#6d9a45")])
        m.base.append(f'<circle cx="{x + 6:.0f}" cy="{y + 9:.0f}" r="{s:.0f}" fill="#10200a" opacity=".55" filter="url(#{m.p}-blur)"/>')
        for k in range(5):
            dx, dy, rr = r.uniform(-s * .5, s * .5), r.uniform(-s * .4, s * .4), s * r.uniform(.45, .7)
            m.base.append(f'<circle cx="{x + dx:.0f}" cy="{y + dy:.0f}" r="{rr:.0f}" fill="{base}" stroke="#1a2e10" stroke-width="1"/>'
                          f'<circle cx="{x + dx - rr * .25:.0f}" cy="{y + dy - rr * .3:.0f}" r="{rr * .55:.0f}" fill="{hi}" opacity=".7"/>')
    for _ in range(18):  # old ruin walls among the trees
        x, y = r.uniform(0, W), r.uniform(100, H)
        m.base.append(f'<rect x="{x:.0f}" y="{y:.0f}" width="{r.uniform(30, 70):.0f}" height="9" fill="#8f8770" stroke="#2c2a20" opacity=".75"/>')
    m.base.append(f'<rect width="{W}" height="{H}" filter="url(#{m.p}-tex)" opacity=".3"/>')


def water_terrain(m: Map):
    r = m.rng
    m.base.append(f'<rect width="{W}" height="{H}" fill="url(#{m.p}-sky)"/>')
    m.base.append(f'<rect width="{W}" height="{H}" fill="url(#{m.p}-ripples)"/>')
    m.base.append(f'<ellipse cx="820" cy="150" rx="160" ry="70" fill="#cfe6f0" opacity=".08" filter="url(#{m.p}-glow)"/>')
    for _ in range(26):  # drowned pillars
        x, y = r.uniform(0, W), r.uniform(100, H)
        m.base.append(f'<rect x="{x:.0f}" y="{y - 30:.0f}" width="12" height="30" fill="#4e5f68" stroke="#0a1a22"/>'
                      f'<ellipse cx="{x + 6:.0f}" cy="{y:.0f}" rx="14" ry="4" fill="none" stroke="#bfe0ee" opacity=".3"/>')


def hub_terrain(m: Map):
    r = m.rng
    m.base.append(f'<rect width="{W}" height="{H}" fill="url(#{m.p}-sky)"/>')
    m.base.append(f'<rect width="{W}" height="{H}" filter="url(#{m.p}-tex)" opacity=".45"/>')
    for i in range(0, W, 46):
        m.base.append(f'<line x1="{i}" y1="78" x2="{i - 120}" y2="{H}" stroke="#7a6446" stroke-width=".6" opacity=".25"/>')


# ---------------------------------------------------------------------------------------------------------------
# The six maps
# ---------------------------------------------------------------------------------------------------------------
def build_sanctuary(m: Map):
    hub_terrain(m)
    t = m.t
    # 2 library (left wing)
    m.area("library", rect_pts(205, 270, 205, 200),
           m.slab(220, 300, 170, 140, 26) + m.walls(220, 300, 170, 140)
           + "".join(f'<rect x="{236 + i * 27}" y="{318}" width="16" height="104" fill="#6b4423" stroke="{INK}"/>'
                     f'<rect x="{238 + i * 27}" y="{322}" width="12" height="96" fill="url(#{m.p}-tiles)" opacity=".8"/>'
                     for i in range(6))
           + m.walk([(390, 380), (420, 385)], 26), (305, 455))
    # 1 awakening (reading nook), below the library
    m.area("awakening", rect_pts(275, 470, 180, 175),
           m.walk([(330, 466), (330, 560)], 24)
           + m.slab(290, 560, 150, 80, 22) + m.walls(290, 560, 150, 80, 12)
           + f'<rect x="318" y="585" width="56" height="26" fill="#b08a55" stroke="{INK}" stroke-width="1.5"/>'
             f'<circle cx="400" cy="590" r="12" fill="#f3d68e" opacity=".85" filter="url(#{m.p}-glow)"/><circle cx="400" cy="590" r="4" fill="#fff3c4"/>',
           (420, 622))
    # 3 concordance (the rotunda)
    rings = "".join(f'<ellipse cx="540" cy="378" rx="{r}" ry="{r * .48:g}" fill="none" stroke="#c49a45" stroke-width="{6 - i}" />'
                    for i, r in enumerate((30, 52, 74, 96, 118)))
    spokes = "".join(f'<line x1="540" y1="378" x2="{540 + 128 * math.cos(math.radians(a)):.0f}" '
                     f'y2="{378 + 62 * math.sin(math.radians(a)):.0f}" stroke="#7a5a2a" stroke-width="5"/>' for a in range(0, 360, 45))
    m.area("concordance", ellipse_pts(540, 395, 178, 100),
           m.disc(540, 380, 162, 78, 40, rings=0)
           + f'<ellipse cx="540" cy="378" rx="136" ry="64" fill="#1c2a33" stroke="{INK}" stroke-width="2"/>'
             f'<ellipse cx="540" cy="378" rx="136" ry="64" fill="url(#{m.p}-ripples)"/>'
           + spokes + rings
           + f'<circle cx="540" cy="378" r="10" fill="#cfe6f2" stroke="{INK}"/>'
           + "".join(m.post(540 + 150 * math.cos(math.radians(a)), 380 + 72 * math.sin(math.radians(a)), 6, 26)
                     for a in range(0, 360, 30) if 20 < a < 160 or a > 200),
           (540, 470))
    # 4 gallery (right wing): five Book cases
    m.area("gallery", rect_pts(690, 270, 215, 200),
           m.walk([(700, 380), (670, 385)], 26)
           + m.slab(700, 300, 190, 140, 26) + m.walls(700, 300, 190, 140)
           + "".join(f'<rect x="{716 + i * 34}" y="330" width="26" height="62" fill="#c9b285" stroke="{INK}" stroke-width="1.5"/>'
                     f'<rect x="{720 + i * 34}" y="336" width="18" height="24" fill="#5b3518"/>'
                     f'<rect x="{716 + i * 34}" y="330" width="26" height="62" fill="#bfe0ee" opacity=".25"/>' for i in range(5)),
           (795, 455))
    # 5 balcony (upper gallery ring)
    m.area("balcony", ellipse_pts(540, 175, 175, 62),
           f'<line x1="680" y1="205" x2="660" y2="320" stroke="{INK}" stroke-width="5"/><line x1="680" y1="205" x2="660" y2="320" stroke="#c49a45" stroke-width="2"/>'
           + m.disc(540, 160, 152, 40, 20, rings=0)
           + f'<ellipse cx="540" cy="160" rx="110" ry="26" fill="{t["bg2"]}" stroke="{INK}" stroke-width="2"/>'
           + "".join(m.post(540 + 140 * math.cos(math.radians(a)), 160 + 36 * math.sin(math.radians(a)), 5, 18) for a in range(200, 345, 24))
           + f'<rect x="668" y="178" width="24" height="30" fill="{t["side"]}" stroke="{INK}"/>',
           (540, 205))
    # 6 study
    m.area("study", rect_pts(545, 555, 200, 120),
           m.walk([(600, 470), (620, 575)], 24)
           + m.slab(560, 575, 170, 80, 22) + m.walls(560, 575, 170, 80, 12)
           + f'<rect x="590" y="595" width="70" height="30" fill="#7a5a36" stroke="{INK}"/><rect x="606" y="600" width="26" height="18" fill="#efe2c2"/>'
             f'<rect x="690" y="590" width="26" height="40" fill="#3b2a1a" stroke="{INK}"/>',
           (705, 640))


def build_ice(m: Map):
    ice_terrain(m)
    t = m.t
    mirror = lambda x, y, a: (f'<g transform="translate({x} {y}) rotate({a})"><rect x="-22" y="-30" width="44" height="40" rx="4" '
                              f'fill="#cfeaf7" stroke="{INK}" stroke-width="2"/><rect x="-18" y="-26" width="18" height="32" fill="#fff" opacity=".45"/>'
                              f'</g><rect x="{x - 4}" y="{y + 8}" width="8" height="14" fill="#8c6a2c" stroke="{INK}"/>')
    m.area("arrival", ellipse_pts(360, 610, 95, 55),
           m.disc(360, 600, 74, 32, 24)
           + f'<ellipse cx="360" cy="598" rx="26" ry="11" fill="none" stroke="#bfe3f5" stroke-width="4"/>'
             f'<ellipse cx="360" cy="598" rx="26" ry="11" fill="none" stroke="#fff" stroke-width="1"/>',
           (360, 640))
    m.area("terrace", ellipse_pts(500, 425, 175, 100),
           m.walk([(385, 585), (440, 475)], 26)
           + m.disc(500, 410, 152, 72, 34, rings=2)
           + mirror(430, 400, -14) + mirror(560, 380, 18) + mirror(510, 450, 0)
           + f'<path d="M300 180 L430 395 L560 375 L512 445" fill="none" stroke="#fff3c4" stroke-width="3" stroke-dasharray="7 5" opacity=".9"/>',
           (500, 415))
    m.area("hall", rect_pts(285, 135, 260, 185),
           m.walk([(450, 345), (430, 290)], 24)
           + m.slab(300, 170, 230, 110, 28) + m.walls(300, 170, 230, 110)
           + "".join(f'<g transform="translate({340 + i * 50} 230) rotate(-32)"><rect x="-6" y="-34" width="12" height="46" rx="3" '
                     f'fill="#c9a86a" stroke="{INK}" stroke-width="1.5"/><circle cy="-34" r="7" fill="#7a5a2a" stroke="{INK}"/></g>'
                     for i in range(4))
           + f'<rect x="522" y="185" width="14" height="80" fill="#bfe3f5" stroke="#4b6175" stroke-width="2" opacity=".9"/>',
           (330, 255))
    m.area("cistern", ellipse_pts(790, 565, 125, 75),
           m.walk([(625, 455), (720, 545)], 22)
           + m.disc(790, 555, 106, 48, 28, rings=0)
           + f'<ellipse cx="790" cy="557" rx="84" ry="36" fill="#3d6a85" stroke="{INK}" stroke-width="2"/>'
             f'<ellipse cx="790" cy="557" rx="84" ry="36" fill="url(#{m.p}-ripples)"/>'
             f'<path d="M740 548 l18 -4 l10 8 Z M800 566 l22 -3 l6 9 Z" fill="#e9f1f6" stroke="#5d778c"/>',
           (790, 600))
    m.area("archive", rect_pts(625, 150, 200, 165),
           m.walk([(530, 245), (640, 245)], 22)
           + m.slab(640, 180, 170, 105, 28) + m.walls(640, 180, 170, 105)
           + "".join(f'<rect x="{656 + i * 24}" y="195" width="16" height="56" fill="#6b4423" stroke="{INK}"/>' for i in range(4))
           + f'<ellipse cx="780" cy="240" rx="18" ry="8" fill="#c49a45" stroke="{INK}"/><path d="M764 240 A16 16 0 0 1 796 240" fill="#bfe3f5" stroke="{INK}"/>',
           (725, 270))
    m.area("dome", ellipse_pts(880, 310, 92, 120),
           m.walk([(810, 235), (850, 295)], 20)
           + m.disc(880, 330, 72, 32, 26)
           + m.tower(880, 335, 40, 120, "#cfe3ee", .8)
           + f'<g transform="translate(905 255) rotate(-38)"><rect x="-8" y="-46" width="16" height="56" rx="4" fill="#c9a86a" stroke="{INK}" stroke-width="2"/></g>',
           (880, 372))


def build_fire(m: Map):
    fire_terrain(m)
    t = m.t
    gear = lambda cx, cy, r: (f'<g><circle cx="{cx}" cy="{cy}" r="{r}" fill="#a07a3a" stroke="{INK}" stroke-width="2"/>'
                              + "".join(f'<rect x="{cx - 5}" y="{cy - r - 7}" width="10" height="10" fill="#a07a3a" stroke="{INK}" '
                                        f'transform="rotate({a} {cx} {cy})"/>' for a in range(0, 360, 30))
                              + f'<circle cx="{cx}" cy="{cy}" r="{r * .55:g}" fill="none" stroke="{INK}" stroke-width="2"/>'
                                f'<circle cx="{cx}" cy="{cy}" r="{r * .2:g}" fill="#3d2f28" stroke="{INK}"/></g>')
    m.area("arrival", ellipse_pts(360, 615, 95, 52),
           m.disc(360, 605, 72, 30, 22) + f'<ellipse cx="360" cy="603" rx="24" ry="10" fill="none" stroke="#ffb35c" stroke-width="3"/>',
           (360, 642))
    m.area("valves", rect_pts(315, 385, 230, 160),
           m.walk([(385, 585), (410, 515)], 24)
           + m.slab(330, 400, 200, 110, 28) + m.walls(330, 400, 200, 110)
           + f'<g transform="scale(1 .55)">' + gear(385, 800, 24) + gear(460, 800, 24) + "</g>"
           + f'<circle cx="505" cy="430" r="14" fill="#efe2c2" stroke="{INK}" stroke-width="2"/><line x1="505" y1="430" x2="512" y2="421" stroke="{INK}" stroke-width="2"/>'
           + f'<text x="378" y="490" font-family="Georgia,serif" font-weight="bold" font-size="14" fill="#f3d68e">A</text>'
             f'<text x="453" y="490" font-family="Georgia,serif" font-weight="bold" font-size="14" fill="#f3d68e">B</text>',
           (350, 495))
    m.area("channels", rect_pts(550, 450, 240, 140),
           m.walk([(530, 470), (565, 480)], 22)
           + m.slab(560, 465, 220, 100, 22, tiles=False)
           + f'<rect x="575" y="482" width="190" height="20" fill="#ff8a2a" stroke="{INK}"/><rect x="575" y="488" width="190" height="6" fill="#ffd27a"/>'
             f'<rect x="575" y="522" width="190" height="20" fill="#ff8a2a" stroke="{INK}"/><rect x="575" y="528" width="190" height="6" fill="#ffd27a"/>'
             f'<rect x="575" y="482" width="190" height="60" fill="#ff6a14" opacity=".35" filter="url(#{m.p}-glow)"/>',
           (670, 570))
    m.area("gears", ellipse_pts(470, 245, 150, 92),
           m.walk([(430, 400), (450, 300)], 22)
           + m.disc(470, 235, 130, 62, 36, rings=0)
           + f'<g transform="scale(1 .5)">' + gear(430, 470, 46) + gear(520, 480, 34) + gear(470, 420, 22) + "</g>",
           (470, 300))
    m.area("elevator", ellipse_pts(680, 245, 62, 110),
           m.walk([(600, 240), (655, 255)], 20)
           + m.disc(680, 300, 46, 20, 18, tiles=False)
           + f'<rect x="662" y="170" width="36" height="128" fill="#3d2f28" stroke="{INK}" stroke-width="2"/>'
             f'<rect x="667" y="232" width="26" height="34" fill="none" stroke="#c49a45" stroke-width="2.5"/>'
             f'<line x1="680" y1="172" x2="680" y2="232" stroke="#c49a45" stroke-width="1.5"/>'
             f'<path d="M660 170 h40 l-6 -12 h-28 Z" fill="#6d5a4e" stroke="{INK}"/>',
           (720, 300))
    m.area("foundry", rect_pts(745, 95, 230, 175),
           m.walk([(700, 168), (760, 172)], 20)
           + m.slab(760, 120, 200, 110, 30) + m.walls(760, 120, 200, 110)
           + f'<path d="M800 200 q20 -46 44 0 Z" fill="#a0612a" stroke="{INK}" stroke-width="2"/>'
             f'<ellipse cx="822" cy="200" rx="22" ry="7" fill="#ffb35c" opacity=".8" filter="url(#{m.p}-glow)"/>'
             f'<path d="M880 190 q14 -30 30 0 Z" fill="#c49a45" stroke="{INK}" stroke-width="2"/>'
           + "".join(f'<rect x="{784 + i * 32}" y="208" width="24" height="12" fill="#7a5a36" stroke="{INK}"/>' for i in range(5)),
           (930, 210))
    m.area("shrine", ellipse_pts(860, 560, 110, 80),
           m.walk([(780, 515), (820, 545)], 20)
           + m.disc(860, 550, 86, 40, 30)
           + f'<path d="M820 540 h80 l-10 14 h-60 Z" fill="#3d2f28" stroke="{INK}" stroke-width="2"/>'
             f'<rect x="845" y="520" width="30" height="20" fill="#3d2f28" stroke="{INK}"/>'
           + "".join(f'<circle cx="{840 + (i % 3) * 20}" cy="{570 + (i // 3) * 8}" r="2.5" fill="#ffd27a"/>' for i in range(6)),
           (930, 585))


def build_air(m: Map):
    air_terrain(m)

    def island(cx, cy, rx, ry, extra=""):
        return (f'<path d="M{cx - rx:g} {cy:g} Q{cx - rx * .6:g} {cy + ry * 2.2:g} {cx - rx * .15:g} {cy + ry * 3.6:g} '
                f'L{cx + rx * .05:g} {cy + ry * 4.4:g} Q{cx + rx * .45:g} {cy + ry * 2.6:g} {cx + rx:g} {cy:g} Z" '
                f'fill="#7a6a58" stroke="{INK}" stroke-width="2"/>'
                f'<path d="M{cx - rx * .2:g} {cy + ry:g} L{cx:g} {cy + ry * 4.2:g}" stroke="{INK}" stroke-width="1" opacity=".5"/>'
                f'<path d="M{cx - rx:g} {cy:g} Q{cx - rx * .6:g} {cy + ry * 2.2:g} {cx - rx * .15:g} {cy + ry * 3.6:g} L{cx - rx * .1:g} {cy + ry:g} Z" fill="#fff" opacity=".12"/>'
                + m.disc(cx, cy - 6, rx, ry, 12, top="#a9b77f", side="#6f8150", tiles=False, rings=0)
                + m.disc(cx, cy - 16, rx * .78, ry * .78, 12, rings=1) + extra)
    m.area("arrival", ellipse_pts(330, 620, 92, 70),
           island(330, 612, 74, 26, f'<ellipse cx="330" cy="595" rx="20" ry="7" fill="none" stroke="#fff" stroke-width="3"/>'), (330, 632))
    wheels = "".join(f'<g><rect x="{430 + i * 40 - 9}" y="440" width="18" height="30" rx="4" fill="#b8742a" stroke="{INK}" stroke-width="1.5"/>'
                     f'<text x="{430 + i * 40}" y="460" text-anchor="middle" font-family="Georgia,serif" font-size="11" fill="#fff3c4">{n}</text></g>'
                     for i, n in enumerate(["I", "II", "III"]))
    m.area("wheels", ellipse_pts(470, 480, 135, 85),
           m.walk([(360, 595), (430, 495)], 14, rope=True) + island(470, 478, 112, 40, wheels), (540, 500))
    m.area("south", ellipse_pts(690, 545, 95, 115),
           m.walk([(570, 495), (640, 560)], 14, rope=True) + island(690, 575, 72, 26, m.tower(690, 570, 18, 70, "#2c4a63")), (735, 595))
    m.area("east", ellipse_pts(870, 400, 95, 115),
           m.walk([(735, 560), (820, 440)], 14, rope=True) + island(870, 430, 72, 26, m.tower(870, 425, 18, 74, "#2c4a63")), (915, 450))
    belfry = (f'<rect x="300" y="250" width="62" height="44" fill="#d6cdb4" stroke="{INK}" stroke-width="2"/>'
              f'<path d="M294 250 L331 222 L368 250 Z" fill="#2c4a63" stroke="{INK}" stroke-width="2"/>'
              + "".join(f'<line x1="{308 + i * 9}" y1="258" x2="{308 + i * 9}" y2="{272 + (i % 3) * 5}" stroke="#c49a45" stroke-width="2"/>' for i in range(6)))
    m.area("belfry", ellipse_pts(330, 300, 100, 85),
           m.walk([(430, 470), (360, 330)], 14, rope=True) + island(330, 300, 82, 30, belfry), (390, 315))
    m.area("north", ellipse_pts(540, 195, 92, 120),
           m.walk([(370, 285), (500, 220)], 14, rope=True) + island(540, 225, 70, 26, m.tower(540, 222, 20, 96, "#2c4a63")), (585, 245))
    from_art = __import__("art")
    kite = from_art.constellation("kite", 790, 205, .9, True, "#3a2816", "#fff3c4")
    shrine = (f'<path d="M760 170 h60 v36 h-60 Z" fill="#d6cdb4" stroke="{INK}" stroke-width="2"/>'
              f'<path d="M754 170 L790 140 L826 170 Z" fill="#2c4a63" stroke="{INK}" stroke-width="2"/>'
              + "".join(f'<line x1="{766 + i * 8}" y1="178" x2="{766 + i * 8}" y2="204" stroke="#8c6a2c" stroke-width="2"/>' for i in range(7)))
    m.area("summit", ellipse_pts(790, 215, 150, 95),
           m.walk([(600, 205), (680, 215)], 14, rope=True) + m.walk([(860, 360), (830, 260)], 14, rope=True)
           + island(790, 215, 128, 44, kite.replace('opacity=".7"', 'opacity=".9"') + shrine), (880, 230))


def build_earth(m: Map):
    earth_terrain(m)
    t = m.t
    m.area("arrival", ellipse_pts(370, 615, 95, 55),
           m.disc(370, 605, 72, 30, 22)
           + f'<path d="M340 600 C 330 560, 350 540, 370 560 C 390 540, 412 560, 400 600" fill="none" stroke="#5a3c22" stroke-width="9"/>'
             f'<path d="M340 600 C 330 560, 350 540, 370 560 C 390 540, 412 560, 400 600" fill="none" stroke="#7a5a36" stroke-width="4"/>',
           (425, 630))
    m.area("clearing", ellipse_pts(510, 520, 125, 75),
           m.walk([(425, 590), (450, 545)], 22)
           + m.disc(510, 510, 104, 48, 26, top="#c9c29a")
           + f'<circle cx="510" cy="500" r="40" fill="#fff6c8" opacity=".35" filter="url(#{m.p}-glow)"/>'
             f'<ellipse cx="510" cy="505" rx="18" ry="9" fill="#5c8a5a" stroke="{INK}" stroke-width="2"/><line x1="510" y1="505" x2="510" y2="478" stroke="{INK}" stroke-width="2"/>'
             f'<circle cx="510" cy="476" r="7" fill="#f3d68e" stroke="{INK}"/>',
           (585, 540))
    m.area("cisterns", rect_pts(275, 300, 210, 160),
           m.walk([(470, 360), (500, 340)], 20)
           + m.slab(290, 320, 175, 95, 26) + m.walls(290, 320, 175, 95)
           + "".join(f'<rect x="{304 + i * 52}" y="338" width="40" height="54" fill="#2f5d72" stroke="{INK}" stroke-width="1.5"/>'
                     f'<rect x="{304 + i * 52}" y="338" width="40" height="54" fill="url(#{m.p}-ripples)"/>' for i in range(3)),
           (300, 432))
    beds = [("Stairbloom", 520, 255), ("Ladder-reed", 610, 255), ("Bridgevine", 520, 315), ("Thornwall", 610, 315)]
    m.area("gardens", rect_pts(485, 210, 250, 190),
           m.walk([(515, 465), (560, 385)], 22)
           + m.slab(500, 235, 210, 130, 28) + m.walls(500, 235, 210, 130)
           + "".join(f'<rect x="{x}" y="{y}" width="80" height="48" rx="6" fill="#5a3c22" stroke="{INK}" stroke-width="1.5"/>'
                     + "".join(f'<circle cx="{x + 10 + k * 15}" cy="{y + 22 + (k % 2) * 8}" r="6" fill="#7fae4a" stroke="#2f5220"/>' for k in range(5))
                     for _, x, y in beds),
           (705, 380))
    m.area("ravine", rect_pts(735, 120, 80, 560),
           f'<path d="M745 90 C 760 200, 735 330, 760 450 S 750 620, 770 700 L 805 700 C 790 600, 805 470, 790 360 S 810 180, 800 90 Z" '
           f'fill="#0f1a0a" stroke="#1d3312" stroke-width="3"/>'
           f'<path d="M745 90 C 760 200, 735 330, 760 450 S 750 620, 770 700" fill="none" stroke="#6f6650" stroke-width="6"/>'
           + m.walk([(705, 320), (745, 330)], 18),
           (775, 400))
    m.area("calendar", ellipse_pts(880, 560, 110, 80),
           m.walk([(790, 520), (830, 545)], 18)
           + m.disc(880, 550, 92, 42, 30, rings=0)
           + "".join(f'<ellipse cx="880" cy="548" rx="{r}" ry="{r * .46:g}" fill="none" stroke="{INK}" stroke-width="2.5"/>' for r in (14, 28, 42, 56, 70)),
           (945, 600))
    tree = (f'<path d="M855 335 C 862 300, 868 260, 872 215 L 888 215 C 892 260, 898 300, 905 335 Z" fill="#6b4a2a" stroke="{INK}" stroke-width="2"/>'
            f'<path d="M855 335 q-18 4 -26 10 M905 335 q18 4 26 10 M872 250 q-20 -10 -34 -30 M888 245 q22 -12 34 -34" fill="none" stroke="#6b4a2a" stroke-width="6"/>'
            + "".join(f'<circle cx="{880 + 62 * math.cos(a):.0f}" cy="{190 + 30 * math.sin(a):.0f}" r="36" fill="{c}" stroke="#1d3312"/>'
                      f'<circle cx="{872 + 62 * math.cos(a):.0f}" cy="{180 + 30 * math.sin(a):.0f}" r="18" fill="#8fbf5a" opacity=".45"/>'
                      for a, c in zip([i * math.pi / 3.5 for i in range(7)], ["#4f7d33", "#5f8f3c", "#3f6a2a", "#6d9a45", "#4f7d33", "#5f8f3c", "#3f6a2a"]))
            + f'<circle cx="880" cy="182" r="44" fill="#5f8f3c" stroke="#1d3312"/><circle cx="868" cy="168" r="22" fill="#9fcf6a" opacity=".45"/>')
    m.area("heart", ellipse_pts(880, 270, 110, 140),
           m.walk([(880, 510), (880, 360)], 18)
           + m.disc(880, 340, 90, 40, 24, top="#9c9372") + tree,
           (950, 355))


def build_water(m: Map):
    water_terrain(m)
    t = m.t
    m.area("arrival", rect_pts(275, 570, 140, 110),
           m.slab(290, 590, 110, 70, 18)
           + "".join(f'<line x1="300" y1="{600 + i * 12}" x2="390" y2="{600 + i * 12}" stroke="{INK}" stroke-width="1.5"/>' for i in range(5)),
           (380, 640))
    pillars = "".join(m.tower(445 + (i % 4) * 70, 350 + (i // 4) * 150, 9, 60, t["trim"], .5) for i in range(8))
    m.area("nave", rect_pts(405, 290, 300, 280),
           m.walk([(345, 590), (420, 540)], 22)
           + m.slab(420, 320, 270, 220, 24)
           + f'<rect x="430" y="330" width="250" height="200" fill="#2a5a72" opacity=".55"/>'
             f'<rect x="430" y="330" width="250" height="200" fill="url(#{m.p}-ripples)"/>' + pillars,
           (555, 455))
    wheel = (f'<g transform="translate(300 290) scale(1 .5)"><circle r="40" fill="none" stroke="#c49a45" stroke-width="8"/>'
             + "".join(f'<line x1="0" y1="0" x2="{40 * math.cos(math.radians(a)):.0f}" y2="{40 * math.sin(math.radians(a)):.0f}" stroke="#c49a45" stroke-width="4"/>'
                       for a in range(0, 360, 45)) + "</g>")
    m.area("wheel", ellipse_pts(300, 300, 100, 70),
           m.walk([(420, 380), (355, 320)], 20) + m.disc(300, 295, 78, 36, 24) + wheel, (360, 330))
    bells = "".join(f'<path d="M{742 + i * 34} 515 q13 -32 26 0 Z" fill="#c49a45" stroke="{INK}" stroke-width="1.5"/>' for i in range(4))
    m.area("choir", rect_pts(715, 455, 200, 150),
           m.walk([(690, 500), (730, 505)], 20) + m.slab(730, 470, 170, 105, 24) + m.walls(730, 470, 170, 105) + bells,
           (870, 560))
    m.area("crypt", rect_pts(715, 285, 200, 150),
           m.walk([(815, 470), (815, 420)], 18)
           + m.slab(730, 305, 170, 100, 24, top="#6f8590") + m.walls(730, 305, 170, 100)
           + f'<path d="M790 380 v-36 a25 25 0 0 1 50 0 v36" fill="#0a1a22" stroke="{INK}" stroke-width="2"/>',
           (750, 390))
    m.area("moonpool", ellipse_pts(555, 180, 140, 75),
           m.walk([(555, 320), (555, 235)], 22)
           + m.disc(555, 175, 120, 50, 26, rings=0)
           + f'<ellipse cx="555" cy="175" rx="92" ry="36" fill="#9fc4d6" stroke="{INK}" stroke-width="2"/>'
             f'<ellipse cx="575" cy="168" rx="20" ry="9" fill="#f5f0e3"/><ellipse cx="575" cy="168" rx="30" ry="14" fill="#f5f0e3" opacity=".3" filter="url(#{m.p}-glow)"/>',
           (650, 210))
    apse = (f'<path d="M870 330 v-110 a45 45 0 0 1 90 0 v110 Z" fill="{t["side"]}" stroke="{INK}" stroke-width="2"/>'
            f'<path d="M895 300 v-70 a20 20 0 0 1 40 0 v70" fill="#2a5a72" stroke="{INK}" stroke-width="1.5"/>'
            f'<path d="M895 300 v-70 a20 20 0 0 1 40 0 v70" fill="#bfe0ee" opacity=".25"/>'
            f'<path d="M866 220 L915 160 L964 220 Z" fill="{t["trim"]}" stroke="{INK}" stroke-width="2"/>')
    m.area("apse", rect_pts(845, 150, 140, 240),
           m.walk([(900, 330), (905, 345)], 18) + m.slab(860, 320, 110, 50, 20) + apse,
           (915, 385))


MAPS = [
    ("sanctuary", "hub", "The Cartographer’s Sanctuary", "Hub Age · the Concordance at its heart", build_sanctuary, 11),
    ("ice", "ice", "Age One – The Frozen Observatory", "Theme: Memory • Rule: Preserve", build_ice, 21),
    ("fire", "fire", "Age Two – The Ember Forge", "Theme: Transformation • Rule: Transform", build_fire, 31),
    ("air", "air", "Age Three – The Sky Monastery", "Theme: Perspective • Rule: Observe", build_air, 41),
    ("earth", "earth", "Age Four – The Verdant Labyrinth", "Theme: Growth • Rule: Grow", build_earth, 51),
    ("water", "water", "Age Five – The Tidal Cathedral", "Theme: Reflection • Rule: Reflect", build_water, 61),
]


def render_all() -> None:
    camp = yaml.safe_load((ROOT / "campaign.yaml").read_text(encoding="utf-8"))
    files = {mp["id"]: mp["file"] for mp in camp["maps"]}
    shapes: dict[str, dict[str, str]] = {}
    for map_id, theme, title, sub, build, seed in MAPS:
        m = Map(map_id, theme, title, sub, seed)
        order = [a["id"] for mp in camp["maps"] if mp["id"] == map_id for a in mp["areas"]]
        m.numbers = {aid: i + 1 for i, aid in enumerate(order)}
        build(m)
        missing = set(order) - set(m.areas)
        assert not missing, (map_id, missing)
        # keep the campaign's area order in the SVG too
        m.areas = {aid: m.areas[aid] for aid in order}
        (ROOT / files[map_id]).write_text(m.svg(), encoding="utf-8")
        shapes[map_id] = m.shapes
    sync_shapes(shapes)


def sync_shapes(shapes: dict[str, dict[str, str]]) -> None:
    """Rewrite each area's `shape:` line in campaign.yaml to match the drawing."""
    path = ROOT / "campaign.yaml"
    lines = path.read_text(encoding="utf-8").split("\n")
    in_maps, cur_map, cur_area = False, None, None
    for i, ln in enumerate(lines):
        if ln.startswith("maps:"):
            in_maps = True
            continue
        if in_maps and re.match(r"^\S", ln) and not ln.startswith("#"):
            in_maps = False
        if not in_maps:
            continue
        mm = re.match(r"^  - id: (\S+)", ln)
        if mm:
            cur_map, cur_area = mm.group(1), None
            continue
        ma = re.match(r"^      - id: (\S+)", ln)
        if ma:
            cur_area = ma.group(1)
            continue
        if cur_map in shapes and cur_area in shapes[cur_map] and re.match(r"^        shape: ", ln):
            lines[i] = f'        shape: "{shapes[cur_map][cur_area]}"'
    path.write_text("\n".join(lines), encoding="utf-8")
