"""Base images for an image generator: each map with its words, numbers, banner and frame removed.

Give one to the generator alongside the prompt in source/PROMPTS.md so the painting keeps the areas where the
campaign expects them. Run from the repository root:  python3 campaigns/tools/base_images.py concordance
"""
import json
import pathlib
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

import yaml

W, H = 1536, 1075  # the maps' 10:7, at a size image generators handle well

ROOT = pathlib.Path(__file__).resolve().parents[1]
NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)


def _drop(el) -> bool:
    """Words, numbers, banners, compass and frame: anything a generator would copy as gibberish."""
    tag = el.tag.split("}")[-1]
    return (tag in ("text", "title") or el.get("class") in ("map-marker", "map-banner")
            or el.get("data-above-fog") == "on")


def clean(svg: str) -> str:
    root = ET.fromstring(svg)
    for parent in list(root.iter()):
        for child in list(parent):
            if _drop(child):
                parent.remove(child)
    root.set("width", str(W))
    root.set("height", str(H))
    root.set("preserveAspectRatio", "none")
    return ET.tostring(root, encoding="unicode")


def main(slug: str) -> None:
    mod = ROOT / slug
    data = yaml.safe_load((mod / "campaign.yaml").read_text())
    out = mod / "source" / "prompts"
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        jobs = []
        for m in data["maps"]:
            f = mod / m["file"]
            if f.suffix != ".svg":
                continue
            page = pathlib.Path(tmp) / f"{m['id']}.svg"
            page.write_text(clean(f.read_text()))
            jobs.append((str(page), str(out / f"{f.stem}-base.jpg")))
        js = ("const {chromium}=require('playwright');(async()=>{const b=await chromium.launch();"
              f"const p=await b.newPage({{viewport:{{width:{W},height:{H}}}}});"
              f"for(const [i,o] of {json.dumps(jobs)}){{await p.goto('file://'+i);await p.screenshot({{path:o,type:'jpeg',quality:88}});}}"
              "await b.close();})();")
        subprocess.run(["node", "-e", js], check=True)
    for _, o in jobs:
        print(o)


if __name__ == "__main__":
    main(sys.argv[1])
