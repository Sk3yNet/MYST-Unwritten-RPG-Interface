"""Adventure modules: campaigns written ahead of play, loaded from CAMPAIGNS_DIR.

Each module is a folder holding `campaign.yaml` plus its maps and handouts (see campaigns/README.md). Modules are
GM material: nothing in them reaches a player's browser except areas that have been revealed and handouts that have
been pushed, and map SVGs are filtered on the server so hidden areas are never sent at all.
"""
from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

import yaml

SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")

MEDIA_TYPES = {".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
               ".gif": "image/gif", ".webp": "image/webp", ".mp4": "video/mp4", ".webm": "video/webm"}
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
    for m in raw.get("maps", []):
        if not _ID.match(str(m.get("id", ""))):
            raise ModuleError(f"map id {m.get('id')!r} must be lower-case letters, digits, - or _")
        areas = {}
        for a in m.get("areas", []):
            if not _ID.match(str(a.get("id", ""))):
                raise ModuleError(f"area id {a.get('id')!r} in map {m['id']} is not a valid id")
            a = {"name": a["id"], "teaser": "", "read_aloud": "", "gm_notes": "", "hooks": [], "secrets": [],
                 "aspects": [], "exits": [], "discover": None, "handouts": [], **a}
            a["points"] = _points(a.get("shape"))
            a["center"] = _centroid(a["points"])
            areas[a["id"]] = a
        for a in areas.values():
            for e in a["exits"]:
                if e not in areas:
                    raise ModuleError(f"area {a['id']} exits to unknown area {e!r}")
        if not mod.file(m["file"]).exists():
            raise ModuleError(f"map file {m['file']} not found")
        mod.maps[m["id"]] = {"name": m["id"], "start_revealed": [], **m, "areas": areas}
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


def render_map(mod: Module, map_id: str, revealed: set[str], gm: bool, pending: set[str] = frozenset()) -> str:
    """Inline SVG for one map. Players get only revealed areas; the GM gets everything under a thin fog."""
    mmap = mod.maps[map_id]
    tree = ET.parse(mod.file(mmap["file"]))
    root = tree.getroot()
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
    pre = f"m-{map_id}"
    defs = ET.SubElement(root, _q("defs"))
    flt = ET.SubElement(defs, _q("filter"), {"id": f"{pre}-fog", "x": "0", "y": "0", "width": "100%", "height": "100%"})
    ET.SubElement(flt, _q("feTurbulence"), {"type": "fractalNoise", "baseFrequency": "0.012", "numOctaves": "4",
                                            "seed": "7"})
    ET.SubElement(flt, _q("feColorMatrix"), {"values": "0 0 0 0 0.80  0 0 0 0 0.72  0 0 0 0 0.56  0 0 0 0.55 0.55"})
    soft = ET.SubElement(defs, _q("filter"), {"id": f"{pre}-soft"})
    ET.SubElement(soft, _q("feGaussianBlur"), {"stdDeviation": "9"})
    mask = ET.SubElement(defs, _q("mask"), {"id": f"{pre}-mask"})
    ET.SubElement(mask, _q("rect"), {"x": f"{x:g}", "y": f"{y:g}", "width": f"{w:g}", "height": f"{h:g}",
                                     "fill": "white"})
    holes = ET.SubElement(mask, _q("g"), {"filter": f"url(#{pre}-soft)"})
    for aid in revealed:
        if aid in mmap["areas"]:
            ET.SubElement(holes, _q("polygon"), {"points": mmap["areas"][aid]["points"], "fill": "black"})
    fog = ET.SubElement(root, _q("g"), {"class": "fog", "mask": f"url(#{pre}-mask)", "pointer-events": "none",
                                        "opacity": "0.55" if gm else "1"})
    ET.SubElement(fog, _q("rect"), {"x": f"{x:g}", "y": f"{y:g}", "width": f"{w:g}", "height": f"{h:g}",
                                    "fill": "#cbb68c"})
    ET.SubElement(fog, _q("rect"), {"x": f"{x:g}", "y": f"{y:g}", "width": f"{w:g}", "height": f"{h:g}",
                                    "filter": f"url(#{pre}-fog)"})
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
            t = ET.SubElement(hot, _q("text"), {"x": f"{cx:g}", "y": f"{cy:g}", "class": "frontier-mark",
                                                "text-anchor": "middle", "pointer-events": "none"})
            t.text = "?"
    root.set("class", "map-svg " + ("gm" if gm else "player"))
    root.set("data-map", map_id)
    root.attrib.pop("width", None)
    root.attrib.pop("height", None)
    return ET.tostring(root, encoding="unicode")


def player_area(a: dict) -> dict:
    """The parts of an area a player may see once it is revealed."""
    return {k: a[k] for k in ("id", "name", "read_aloud", "hooks", "aspects") if k in a}
