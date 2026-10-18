"""The lobby: a theater-curtained bookshelf of burned books, where only playable adventures survive.

Players light their candle (ready); the GM picks a book; every screen at the table plays the same launch: the book
leaves the shelf, opens to its Linking page, the preview plays in the panel, the link sounds, and everyone arrives.
"""
from __future__ import annotations

import random
import time

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse

from . import modules
from .main import HTTPError, _txt, camp_ctx, changed, page
from .play import activate_module

router = APIRouter()

SHELVES = 4
BOOKS_PER_SHELF = 30
BURNED_HUES = ["#2a1d14", "#24170f", "#30221a", "#1f1611", "#332419", "#2b2320", "#1d1814"]


def _jagged(rng: random.Random, burn: float) -> str:
    """A clip-path whose top edge is eaten away, so the book looks burned down from the top."""
    pts = ["0% 100%", "100% 100%"]
    top = []
    steps = rng.randint(3, 6)
    for i in range(steps + 1):
        x = 100 - i * 100 / steps
        y = max(0.0, min(60.0, burn * 100 + rng.uniform(-9, 9)))
        top.append(f"{x:.0f}% {y:.0f}%")
    return "polygon(" + ", ".join(pts + top) + ")"


def build_shelf(seed: int, mods: list[modules.Module]) -> list[list[dict]]:
    """Rows of books. Burned ones are decoration; each playable module is one intact book placed among them."""
    rng = random.Random(seed)
    rows: list[list[dict]] = []
    for _ in range(SHELVES):
        row = []
        for _ in range(BOOKS_PER_SHELF):
            burn = rng.choice([0.0, 0.05, 0.12, 0.2, 0.3, 0.42, 0.55])
            row.append({"kind": "burned", "w": rng.randint(20, 40), "h": rng.randint(58, 90),
                        "hue": rng.choice(BURNED_HUES), "lean": rng.choice([0, 0, 0, 0, -3, 3, -6]),
                        "clip": _jagged(rng, burn), "ember": rng.random() < 0.18,
                        "band": rng.random() < 0.5})
        rows.append(row)
    # Intact books go on the two middle shelves, at eye level, spread apart.
    # Shelves are centered and clip at the sides on narrow screens, so intact books sit near the middle first.
    mid = BOOKS_PER_SHELF // 2
    cols = sorted(range(2, BOOKS_PER_SHELF - 2, 3), key=lambda c: abs(c - mid))
    slots = [(r, c) for r in (1, 2, 0, 3) for c in cols]
    head = slots[:4]
    rng.shuffle(head)
    slots = head + slots[4:]
    for mod, (r, c) in zip(mods, slots):
        rows[r][c] = {"kind": "live", "slug": mod.slug, "title": mod.title, "book": mod.book, "w": 50, "h": 97,
                      "lean": 0, "summary": mod.data.get("summary", ""), "players": mod.data.get("players", "")}
    return rows


def _playable() -> list[modules.Module]:
    return [m for m in modules.available().values() if not m.data.get("error")]


async def _people(ctx) -> list[dict]:
    ready = set(ctx.camp["state"].get("ready", []))
    return [{**m, "ready": m["email"] in ready} for m in await ctx.db.members(ctx.cid)]


@router.get("/c/{cid}/lobby", response_class=HTMLResponse)
async def lobby(request: Request, cid: int):
    ctx = await camp_ctx(request, cid)
    mods = _playable()
    state = ctx.camp["state"]
    return page(request, "lobby.html", ctx, tab="lobby", shelf=build_shelf(cid, mods), mods={m.slug: m for m in mods},
                people=await _people(ctx), launch=state.get("launch"), current=modules.get(state.get("module")))


@router.get("/c/{cid}/lobby/people", response_class=HTMLResponse)
async def lobby_people(request: Request, cid: int):
    ctx = await camp_ctx(request, cid)
    return page(request, "partials/lobby_people.html", ctx, people=await _people(ctx))


@router.post("/c/{cid}/lobby/ready")
async def lobby_ready(request: Request, cid: int):
    ctx = await camp_ctx(request, cid)
    state = ctx.camp["state"]
    ready = state.setdefault("ready", [])
    if ctx.email in ready:
        ready.remove(ctx.email)
    else:
        ready.append(ctx.email)
    await ctx.db.save_state(cid, state)
    return changed(ctx, "lobby")


@router.post("/c/{cid}/lobby/launch")
async def lobby_launch(request: Request, cid: int):
    ctx = await camp_ctx(request, cid)
    ctx.require_gm()
    slug = _txt((await request.form()).get("slug"), 80)
    mod = modules.get(slug)
    if not mod:
        raise HTTPError(400, "That book can't be opened.")
    state = ctx.camp["state"]
    if state.get("module") != slug:  # picking the adventure already under way keeps its progress
        await activate_module(ctx, slug)
        state = ctx.camp["state"]
    state["launch_seq"] = state.get("launch_seq", 0) + 1
    state["launch"] = {"slug": slug, "seq": state["launch_seq"], "at": time.time()}
    await ctx.db.save_state(cid, state)
    return changed(ctx, "launch")


@router.post("/c/{cid}/lobby/snuff")
async def lobby_snuff(request: Request, cid: int):
    ctx = await camp_ctx(request, cid)
    ctx.require_gm()
    ctx.camp["state"]["ready"] = []
    await ctx.db.save_state(cid, ctx.camp["state"])
    return changed(ctx, "lobby")


@router.get("/c/{cid}/lobby/launch", response_class=HTMLResponse)
async def lobby_launch_info(request: Request, cid: int):
    """What the launch animation needs: which book, and where this viewer goes afterwards."""
    ctx = await camp_ctx(request, cid)
    launch = ctx.camp["state"].get("launch")
    mod = modules.get(launch["slug"]) if launch else None
    if not mod:
        return HTMLResponse("")
    dest = f"/c/{cid}/run" if ctx.is_gm else f"/c/{cid}/me"
    return page(request, "partials/lobby_launch.html", ctx, launch=launch, mod=mod, dest=dest)


@router.get("/c/{cid}/book/{slug}/{kind}")
async def book_image(request: Request, cid: int, slug: str, kind: str):
    """A shelf book's cover logo or linking-panel preview. Not spoilers, but still only for this table."""
    await camp_ctx(request, cid)
    mod = modules.get(slug)
    if not mod or kind not in ("cover", "preview") or not mod.book.get(kind):
        raise HTTPError(404, "No such picture.")
    f = mod.file(mod.book[kind])
    return FileResponse(f, media_type=modules.MEDIA_TYPES.get(f.suffix.lower(), "application/octet-stream"),
                        headers={"Cache-Control": "private, max-age=600", "Content-Security-Policy": "sandbox"})
