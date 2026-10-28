"""A loose colour sketch of Seleshva for an image generator: natural coastlines instead of the drawn map's boxes.

python3 campaigns/flooded-archive/source/seleshva_sketch.py  ->  source/prompts/seleshva-sketch.jpg
"""
import math
import pathlib

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

W, H = 1536, 1075
S = W / 1000
OUT = pathlib.Path(__file__).parent / "prompts" / "seleshva-sketch.jpg"


def blob(cx, cy, rx, ry, rough=0.22, n=90, seed=0):
    """An irregular closed outline around (cx, cy): a coastline, not an ellipse."""
    r = np.random.default_rng(seed)
    waves = [(r.uniform(.3, 1) * rough / k, k, r.uniform(0, 6.3)) for k in (2, 3, 5, 8, 13)]
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        f = 1 + sum(a * math.sin(k * t + p) for a, k, p in waves)
        pts.append(((cx + rx * f * math.cos(t)) * S, (cy + ry * f * math.sin(t)) * S))
    return pts


def path(d, pts, fill, width):
    d.line([(x * S, y * S) for x, y in pts], fill=fill, width=int(width * S), joint="curve")


img = Image.new("RGB", (W, H), "#3a2d5c")
d = ImageDraw.Draw(img)
# shallows, then land: one tidal island with a headland and a ridge, joined by low necks of rock and sand
land = [
    blob(470, 430, 330, 210, .2, seed=1),     # main body: the reed marsh
    blob(470, 190, 170, 120, .25, seed=2),    # the ridge (camp)
    blob(830, 230, 140, 160, .28, seed=3),    # the headland (lighthouse)
    blob(700, 530, 170, 130, .3, seed=4),     # the rock shelf (tide pools)
    blob(640, 300, 160, 70, .3, seed=5),      # neck: ridge to headland
]
shallow = Image.new("L", (W, H), 0)
for b in land:
    ImageDraw.Draw(shallow).polygon(b, fill=255)
shallow = shallow.filter(ImageFilter.MaxFilter(61)).filter(ImageFilter.GaussianBlur(25))
img = Image.composite(Image.new("RGB", (W, H), "#5a5f8a"), img, shallow)
d = ImageDraw.Draw(img)
for b in land:
    d.polygon(b, fill="#4c4438")                      # dark wet rock at the shore
for b, c in zip(land, ["#6f7a52", "#7d7a50", "#6b6e4c", "#5d5a4c", "#6f7450"]):
    m = Image.new("L", (W, H), 0)
    ImageDraw.Draw(m).polygon(b, fill=255)
    m = m.filter(ImageFilter.MinFilter(15))
    img = Image.composite(Image.new("RGB", (W, H), c), img, m)
d = ImageDraw.Draw(img)
d.polygon(blob(430, 450, 210, 120, .28, seed=7), fill="#5fa79a")   # the glass reeds
d.polygon(blob(500, 170, 100, 60, .2, seed=8), fill="#8f8762")     # the ridge top
for (x, y, rx, ry) in ((640, 470, 48, 30), (705, 535, 52, 32), (760, 600, 55, 34)):  # a staircase of pools
    d.polygon(blob(x, y, rx, ry, .12, seed=x), fill="#6fa0b8")
    d.ellipse([(x - 12) * S, (y - 7) * S, (x + 12) * S, (y + 7) * S], outline="#c9a050", width=3)
# the pier: a stone jetty out into the sea from the west shore
d.polygon([(p[0] * S, p[1] * S) for p in ((95, 470), (265, 470), (265, 520), (175, 520), (175, 640), (125, 640),
                                          (125, 520), (95, 520))], fill="#8a8274")
# trodden paths: pier, through the reeds, up to the ridge, down to the pools, out to the lighthouse
for pts in ([(265, 495), (330, 480), (400, 470), (470, 430), (520, 380), (500, 260), (490, 200)],
            [(470, 430), (560, 450), (630, 470)],
            [(540, 200), (640, 260), (740, 250), (820, 260)],
            [(760, 600), (850, 470), (860, 340)]):
    path(d, pts, "#b8a57a", 7)
x, y = 830, 230
d.polygon([(x - 18) * S, (y + 20) * S, (x + 18) * S, (y + 20) * S, (x + 11) * S, (y - 90) * S, (x - 11) * S,
           (y - 90) * S], fill="#efe8da")                              # the lighthouse
d.rectangle([(x - 15) * S, (y - 110) * S, (x + 15) * S, (y - 88) * S], fill="#f3cf7a")
d.polygon([(470 * S, 170 * S), (500 * S, 125 * S), (530 * S, 170 * S)], fill="#8a6a44")                                              # the lean-to
img = img.filter(ImageFilter.GaussianBlur(1.2))
OUT.parent.mkdir(exist_ok=True)
img.save(OUT, quality=90)
print(OUT)
