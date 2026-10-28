"""Adventure modules: campaigns written ahead of play, loaded from CAMPAIGNS_DIR.

Each module is a folder holding `campaign.yaml` plus its maps and handouts (see campaigns/README.md). Modules are
GM material: nothing in them reaches a player's browser except areas that have been revealed and handouts that have
been pushed, and map SVGs are filtered on the server so hidden areas are never sent at all.
"""
from __future__ import annotations

import hashlib
import io
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageFilter

SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")

MEDIA_TYPES = {".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
               ".gif": "image/gif", ".webp": "image/webp", ".mp4": "video/mp4", ".webm": "video/webm"}
# A map can be a drawing (SVG) or a picture: painted, generated or scanned art, fogged on the server.
RASTER_MAPS = {".png", ".jpg", ".jpeg", ".webp"}
_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,60}$")


def campaigns_dir() -> Path:
    default = Path(__file__).resolve().parents[2] / "campaigns"
    return Path(os.getenv("CAMPAIGNS_DIR", str(default)))


class ModuleError(Exception):
    pass


@dataclass
class Module:
    slug: str
    path: Path
    data: dict
    maps: dict = field(default_factory=dict)       # map id -> map dict (with "areas": {id: area})
    handouts: dict = field(default_factory=dict)   # handout id -> handout dict
    scenes: dict = field(default_factory=dict)     # scene id -> scene dict (with "chapter")
    book: dict = field(default_factory=dict)       # how it looks on the lobby shelf (see _book)

    @property
    def title(self) -> str:
        return self.data.get("title", self.slug)

    def area(self, map_id: str, area_id: str) -> dict | None:
        m = self.maps.get(map_id)
        return m["areas"].get(area_id) if m else None

    def file(self, rel: str) -> Path:
        p = (self.path / rel).resolve()
        if self.path.resolve() not in p.parents:
            raise ModuleError(f"{rel} escapes the module folder")
        return p


def _points(shape) -> str:
    """'x,y x,y …' from a polygon string or a [x, y, w, h] rectangle."""
    if isinstance(shape, (list, tuple)) and len(shape) == 4:
        x, y, w, h = (float(v) for v in shape)
        return f"{x:g},{y:g} {x + w:g},{y:g} {x + w:g},{y + h:g} {x:g},{y + h:g}"
    if isinstance(shape, str) and re.fullmatch(r"\s*(-?[\d.]+,-?[\d.]+\s*){3,}", shape):
        return " ".join(shape.split())
    raise ModuleError(f"bad area shape {shape!r}")


def _centroid(points: str) -> tuple[float, float]:
    pts = [tuple(float(v) for v in p.split(",")) for p in points.split()]
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


def load_module(path: Path) -> Module:
    raw = yaml.safe_load((path / "campaign.yaml").read_text(encoding="utf-8")) or {}
    mod = Module(slug=path.name, path=path, data=raw)
    mod.book = _book(mod, raw.get("book") or {})
    for m in raw.get("maps", []):
        if not _ID.match(str(m.get("id", ""))):
            raise ModuleError(f"map id {m.get('id')!r} must be lower-case letters, digits, - or _")
        areas = {}
        for num, a in enumerate(m.get("areas", []), 1):
            if not _ID.match(str(a.get("id", ""))):
                raise ModuleError(f"area id {a.get('id')!r} in map {m['id']} is not a valid id")
            a = {"name": a["id"], "teaser": "", "read_aloud": "", "gm_notes": "", "hooks": [], "secrets": [],
                 "aspects": [], "exits": [], "discover": None, "handouts": [], "number": num, **a}
            a["points"] = _points(a.get("shape"))
            a["center"] = _centroid(a["points"])
            areas[a["id"]] = a
        for a in areas.values():
            for e in a["exits"]:
                if e not in areas:
                    raise ModuleError(f"area {a['id']} exits to unknown area {e!r}")
        f = mod.file(m["file"])
        if not f.exists():
            raise ModuleError(f"map file {m['file']} not found")
        m = {"name": m["id"], "start_revealed": [], **m, "areas": areas}
        if f.suffix.lower() in RASTER_MAPS:
            # Area shapes are in the picture's own pixels, so they can be traced straight off it.
            with Image.open(f) as im:
                m["size"] = im.size
        mod.maps[m["id"]] = m
    for h in raw.get("handouts", []):
        if not _ID.match(str(h.get("id", ""))):
            raise ModuleError(f"handout id {h.get('id')!r} is not a valid id")
        f = mod.file(h["file"])
        if f.suffix.lower() not in MEDIA_TYPES or not f.exists():
            raise ModuleError(f"handout file {h['file']} missing or not an image/video")
        mod.handouts[h["id"]] = {"caption": "", "effect": "fade", "gm_notes": "", **h}
    for ch in raw.get("chapters", []):
        for s in ch.get("scenes", []):
            s = {"title": s.get("id"), "read_aloud": "", "gm_notes": "", "goal": "", "aspects": [], "npcs": [],
                 "handouts": [], "compel_ideas": [], "if_stuck": [], "ends_when": "", "map": None, "reveal": [],
                 **s, "chapter": ch.get("title", "")}
            if s["map"] and s["map"] not in mod.maps:
                raise ModuleError(f"scene {s['id']} uses unknown map {s['map']!r}")
            mod.scenes[s["id"]] = s
    return mod


_cache: dict[Path, tuple[float, Module]] = {}


def _stamp(p: Path) -> float:
    """Newest modification time of anything in the module folder, so edits are picked up without a restart."""
    return max((f.stat().st_mtime for f in p.rglob("*") if f.is_file()), default=0.0)


BOOK_IMAGES = {".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp"}
_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def _book(mod: Module, b: dict) -> dict:
    """Lobby-shelf look: spine identifier, volume, leather color, cover logo and linking-panel preview (both optional)."""
    out = {"spine": str(b.get("spine") or mod.data.get("title") or mod.slug), "volume": str(b.get("volume") or ""),
           "color": b.get("color") if _COLOR.match(str(b.get("color", ""))) else "#5b3518",
           "cover": None, "preview": None}
    for kind in ("cover", "preview"):
        rel = b.get(kind)
        if rel:
            f = mod.file(rel)
            if f.suffix.lower() not in BOOK_IMAGES or not f.exists():
                raise ModuleError(f"book {kind} {rel} missing or not an image")
            out[kind] = rel
    return out


def available() -> dict[str, Module]:
    """Every loadable module, keyed by folder name. Broken modules are reported, not fatal."""
    out = {}
    root = campaigns_dir()
    if not root.is_dir():
        return out
    for p in sorted(root.iterdir()):
        if not (p / "campaign.yaml").is_file():
            continue
        stamp = _stamp(p)
        hit = _cache.get(p)
        if hit and hit[0] == stamp:
            out[p.name] = hit[1]
            continue
        try:
            mod = load_module(p)
        except (ModuleError, KeyError, TypeError, yaml.YAMLError) as e:
            mod = Module(slug=p.name, path=p, data={"title": p.name, "error": str(e)})
        _cache[p] = (stamp, mod)
        out[p.name] = mod
    return out


def get(slug: str | None) -> Module | None:
    if not slug:
        return None
    m = available().get(slug)
    return m if m and not m.data.get("error") else None


# ---------------------------------------------------------------------------------------------
# Map rendering with fog of war
# ---------------------------------------------------------------------------------------------
def _q(tag: str) -> str:
    return f"{{{SVG_NS}}}{tag}"


def frontier(mmap: dict, revealed: set[str]) -> list[str]:
    """Hidden areas next to a revealed one: what players can see the edge of and ask to inspect."""
    out = []
    for aid, a in mmap["areas"].items():
        if aid in revealed:
            continue
        if any(aid in mmap["areas"][r]["exits"] or r in a["exits"] for r in revealed if r in mmap["areas"]):
            out.append(aid)
    return out


def is_raster(mmap: dict) -> bool:
    return "size" in mmap


def map_picture(mod: Module, map_id: str, revealed: set[str] | None) -> tuple[bytes, str]:
    """A picture map as an image. With revealed=None (the GM) it is the original; for players every area not yet
    revealed is painted over in the fog color before it leaves the server, so the URL shows nothing extra."""
    mmap = mod.maps[map_id]
    path = mod.file(mmap["file"])
    if revealed is None:
        return path.read_bytes(), MEDIA_TYPES[path.suffix.lower()]
    key = (str(path), path.stat().st_mtime, map_id, frozenset(a for a in revealed if a in mmap["areas"]))
    if key not in _pictures:
        with Image.open(path) as im:
            im = im.convert("RGB")
        w, h = im.size
        mask = Image.new("L", im.size, 255)
        draw = ImageDraw.Draw(mask)
        for aid in key[3]:
            pts = [tuple(float(v) for v in p.split(",")) for p in mmap["areas"][aid]["points"].split()]
            draw.polygon(pts, fill=0)
        # Soft edges, as in the drawn maps, but the fog stays solid well inside hidden areas.
        mask = mask.filter(ImageFilter.GaussianBlur(max(w, h) / 110))
        fog = Image.new("RGB", im.size, mmap.get("fog") or "#cbb68c")
        out = io.BytesIO()
        Image.composite(fog, im, mask).save(out, "JPEG", quality=86)
        if len(_pictures) > 64:
            _pictures.clear()
        _pictures[key] = out.getvalue()
    return _pictures[key], "image/jpeg"


_pictures: dict[tuple, bytes] = {}


def picture_version(mod: Module, map_id: str, revealed: set[str] | None) -> str:
    """A short tag for the picture URL, so browsers fetch a new one when the fog changes."""
    mmap = mod.maps[map_id]
    seen = "gm" if revealed is None else ",".join(sorted(a for a in revealed if a in mmap["areas"]))
    return hashlib.sha1(f"{mod.file(mmap['file']).stat().st_mtime}|{seen}".encode()).hexdigest()[:10]


def _picture_root(mmap: dict, image_url: str) -> ET.Element:
    w, h = mmap["size"]
    root = ET.Element(_q("svg"), {"viewBox": f"0 0 {w} {h}"})
    if mmap.get("fog"):
        root.set("data-fog", mmap["fog"])
    if mmap.get("legend"):
        root.set("data-legend", "on")
    ET.SubElement(root, _q("image"), {"href": image_url, "x": "0", "y": "0", "width": str(w), "height": str(h),
                                      "preserveAspectRatio": "none"})
    return root


def render_map(mod: Module, map_id: str, revealed: set[str], gm: bool, pending: set[str] = frozenset(),
               image_url: str = "") -> str:
    """Inline SVG for one map. Players get only revealed areas; the GM gets everything under a thin fog.
    Picture maps are wrapped in the same SVG, pointing at image_url (see map_picture)."""
    mmap = mod.maps[map_id]
    if is_raster(mmap):
        root = _picture_root(mmap, image_url)
    else:
        root = ET.parse(mod.file(mmap["file"])).getroot()
    # Drop hidden areas' drawings (players), so nothing about them is ever sent.
    if not gm:
        def prune(parent):
            for child in list(parent):
                aid = child.get("data-area")
                if aid is not None and aid not in revealed:
                    parent.remove(child)
                else:
                    prune(child)
        prune(root)
    vb = (root.get("viewBox") or "0 0 1000 700").split()
    x, y, w, h = (float(v) for v in vb)
    k = w / 1000  # sizes below are tuned for a 1000-wide map
    pre = f"m-{map_id}"
    defs = ET.SubElement(root, _q("defs"))
    flt = ET.SubElement(defs, _q("filter"), {"id": f"{pre}-fog", "x": "0", "y": "0", "width": "100%", "height": "100%"})
    ET.SubElement(flt, _q("feTurbulence"), {"type": "fractalNoise", "baseFrequency": f"{0.012 / k:.5g}", "numOctaves": "4",
                                            "seed": "7"})
    # Drifting mist: pale noise over the map's fog color.
    ET.SubElement(flt, _q("feColorMatrix"), {"values": "0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 0.9 -0.2"})
    soft = ET.SubElement(defs, _q("filter"), {"id": f"{pre}-soft"})
    ET.SubElement(soft, _q("feGaussianBlur"), {"stdDeviation": f"{9 * k:g}"})
    mask = ET.SubElement(defs, _q("mask"), {"id": f"{pre}-mask"})
    ET.SubElement(mask, _q("rect"), {"x": f"{x:g}", "y": f"{y:g}", "width": f"{w:g}", "height": f"{h:g}",
                                     "fill": "white"})
    holes = ET.SubElement(mask, _q("g"), {"filter": f"url(#{pre}-soft)"})
    for aid in revealed:
        if aid in mmap["areas"]:
            ET.SubElement(holes, _q("polygon"), {"points": mmap["areas"][aid]["points"], "fill": "black"})
    fog = ET.SubElement(root, _q("g"), {"class": "fog", "mask": f"url(#{pre}-mask)", "pointer-events": "none",
                                        "opacity": "0.4" if gm else "1"})
    # A map may choose its mist color (an icy blue, smoke over lava…); parchment otherwise.
    fog_color = root.get("data-fog") or "#cbb68c"
    ET.SubElement(fog, _q("rect"), {"x": f"{x:g}", "y": f"{y:g}", "width": f"{w:g}", "height": f"{h:g}",
                                    "fill": fog_color})
    ET.SubElement(fog, _q("rect"), {"x": f"{x:g}", "y": f"{y:g}", "width": f"{w:g}", "height": f"{h:g}",
                                    "filter": f"url(#{pre}-fog)"})
    # Titles, frames and compass roses marked data-above-fog stay readable over the mist.
    for el in [e for e in root.iter() if e.get("data-above-fog") == "on"]:
        parent = next(p for p in root.iter() if el in list(p))
        parent.remove(el)
        root.append(el)
    if is_raster(mmap) and mmap.get("markers"):
        _markers(root, mmap, revealed, gm, k)
    if root.get("data-legend") == "on":
        _legend(root, mmap, revealed, gm, x, y, h)
    # Hotspots: the GM can click any area; players the revealed ones and the frontier.
    hot = ET.SubElement(root, _q("g"), {"class": "hotspots"})
    edge = set(frontier(mmap, revealed))
    for aid, a in mmap["areas"].items():
        state = "revealed" if aid in revealed else ("frontier" if aid in edge else "fogged")
        if not gm and state == "fogged":
            continue
        if state == "revealed" or gm:
            label = a["name"]
        else:
            label = a["teaser"] or "Unexplored"
        cls = f"hot {state}" + (" pending" if aid in pending else "")
        poly = ET.SubElement(hot, _q("polygon"), {"points": a["points"], "class": cls, "data-hot": aid,
                                                  "tabindex": "0"})
        ET.SubElement(poly, _q("title")).text = label
        if state == "frontier" and not gm:
            cx, cy = a["center"]
            t = ET.SubElement(hot, _q("text"), {"x": f"{cx:g}", "y": f"{cy:g}", "class": "frontier-mark", "font-size": f"{46 * k:g}",
                                                "text-anchor": "middle", "pointer-events": "none"})
            t.text = "?"
    root.set("class", "map-svg " + ("gm" if gm else "player"))
    root.set("data-map", map_id)
    root.attrib.pop("width", None)
    root.attrib.pop("height", None)
    return ET.tostring(root, encoding="unicode")


def _markers(root, mmap: dict, revealed: set[str], gm: bool, k: float) -> None:
    """Numbered medallions over a picture map (painted art rarely has the right numbers on it)."""
    g = ET.SubElement(root, _q("g"), {"class": "map-markers", "pointer-events": "none"})
    for a in mmap["areas"].values():
        if not gm and a["id"] not in revealed:
            continue
        cx, cy = a.get("marker") or a["center"]
        m = ET.SubElement(g, _q("g"), {"transform": f"translate({cx:g} {cy:g}) scale({k:g})",
                                       "opacity": "1" if a["id"] in revealed else ".55"})
        ET.SubElement(m, _q("circle"), {"r": "17", "fill": "#f1e8d4", "stroke": "#3a2816", "stroke-width": "3"})
        ET.SubElement(m, _q("circle"), {"r": "13", "fill": "none", "stroke": "#8c6a2c", "stroke-width": "1.2"})
        t = ET.SubElement(m, _q("text"), {"y": "6.5", "text-anchor": "middle", "font-size": "19", "fill": "#2b1d10",
                                          "font-family": "IM Fell English, Georgia, serif"})
        t.text = str(a["number"])


def _legend(root, mmap: dict, revealed: set[str], gm: bool, x: float, y: float, h: float) -> None:
    """A numbered key in the corner, like a printed map's. Players see only what they've discovered."""
    rows = [a for a in sorted(mmap["areas"].values(), key=lambda a: a["number"]) if gm or a["id"] in revealed]
    if not rows:
        return
    lh, pad, width = 24, 12, 250
    height = pad * 2 + lh * len(rows)
    k = h / 700  # legends are laid out for a 700-high map; picture maps scale them to their own size
    lx, ly = x + 22 * k, y + h - (22 + height) * k
    g = ET.SubElement(root, _q("g"), {"class": "map-legend-box", "pointer-events": "none",
                                      "transform": f"translate({lx:g} {ly:g}) scale({k:g})"})
    lx = ly = 0
    ET.SubElement(g, _q("rect"), {"x": f"{lx:g}", "y": f"{ly:g}", "width": f"{width}", "height": f"{height}", "rx": "6",
                                  "fill": "#f1e8d4", "fill-opacity": ".93", "stroke": "#3a2816", "stroke-width": "2"})
    for i, a in enumerate(rows):
        t = ET.SubElement(g, _q("text"), {"x": f"{lx + 14:g}", "y": f"{ly + pad + lh * i + 17:g}", "font-size": "17",
                                          "font-family": "IM Fell English, Georgia, serif", "fill": "#2b1d10",
                                          "opacity": "1" if a["id"] in revealed else ".45"})
        t.text = f"{a['number']}. {a['name']}"


def player_area(a: dict) -> dict:
    """The parts of an area a player may see once it is revealed."""
    return {k: a[k] for k in ("id", "name", "read_aloud", "hooks", "aspects") if k in a}
