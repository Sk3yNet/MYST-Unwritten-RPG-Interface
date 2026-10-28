"""Adventure play: the player screen, the GM screen, maps with fog of war, inspect requests and handouts.

Players only ever receive what has been revealed or pushed to them: map SVGs are filtered server-side, area details
come from `modules.player_area`, and media is served only after it has been shown to that player.
"""
from __future__ import annotations

import mimetypes
import secrets
import time
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, Response

from . import modules, rules, suggest
from .main import (HTTPError, _int, _party, _roll_character, _txt, camp_ctx, changed, form, page, redirect)

router = APIRouter()

UPLOAD_TYPES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".webm"}
MAX_UPLOAD = 20 * 1024 * 1024
EFFECTS = {"fade": "Fade in", "link": "Linking (ripple and glow)", "reveal": "Slow reveal (blur to sharp)",
           "flash": "Flash", "none": "Instant"}


# =============================================================================================
# helpers
# =============================================================================================
def _mod(ctx) -> modules.Module | None:
    return modules.get(ctx.camp["state"].get("module"))


def _revealed(state: dict, map_id: str) -> set[str]:
    return set(state["revealed"].get(map_id, []))


def _reveal(state: dict, map_id: str, area_id: str) -> bool:
    lst = state["revealed"].setdefault(map_id, [])
    if area_id in lst:
        return False
    lst.append(area_id)
    state["here"][map_id] = area_id
    return True


def _uploads_dir(request: Request, cid: int) -> Path:
    base = Path(request.app.state.settings.db_path).resolve().parent / "uploads" / str(cid)
    base.mkdir(parents=True, exist_ok=True)
    return base


def _handout(ctx, key: str) -> dict | None:
    """key is 'm:<module handout id>' or 'u:<upload id>'. Returns {key, caption, effect, type, path, inline}."""
    if key.startswith("m:"):
        mod = _mod(ctx)
        h = mod.handouts.get(key[2:]) if mod else None
        if not h:
            return None
        path = mod.file(h["file"])
        return {"key": key, "caption": h["caption"], "effect": h["effect"], "gm_notes": h.get("gm_notes", ""),
                "type": modules.MEDIA_TYPES[path.suffix.lower()], "path": path, "name": h["id"]}
    if key.startswith("u:"):
        u = next((u for u in ctx.camp["state"]["uploads"] if u["id"] == key[2:]), None)
        if not u:
            return None
        path = _uploads_dir(ctx.request, ctx.cid) / u["file"]
        return {"key": key, "caption": u["caption"], "effect": "fade", "gm_notes": "", "type": u["type"],
                "path": path, "name": u["caption"] or u["file"]}
    return None


def _may_see(ctx, key: str) -> bool:
    if ctx.is_gm:
        return True
    who = ctx.camp["state"]["shown"].get(key, [])
    return "all" in who or ctx.email in who


def _all_handouts(ctx) -> list[dict]:
    out = []
    mod = _mod(ctx)
    if mod:
        out += [h for h in (_handout(ctx, "m:" + k) for k in mod.handouts) if h]
    out += [h for h in (_handout(ctx, "u:" + u["id"]) for u in ctx.camp["state"]["uploads"]) if h]
    return out


def _inline_svg(h: dict) -> str | None:
    """Module SVG handouts are trusted (written with the adventure) and inlined so page fonts apply."""
    if h["key"].startswith("m:") and h["type"] == "image/svg+xml":
        return h["path"].read_text(encoding="utf-8")
    return None


def _my_pcs(ctx, party) -> list[dict]:
    return [c for c in party["pcs"] if c["owner_email"] == ctx.email]


def _open_rolls_for(state: dict, ch: dict | None) -> list[dict]:
    if not ch:
        return []
    return [r for r in state["requests"] if r["status"] == "roll" and (r.get("char_id") in (None, ch["id"]))]


# =============================================================================================
# module selection & scenes (GM)
# =============================================================================================
@router.post("/c/{cid}/module")
async def load_module(request: Request, cid: int):
    ctx = await camp_ctx(request, cid)
    ctx.require_gm()
    slug = _txt((await form(request)).get("slug"), 80)
    state = ctx.camp["state"]
    if not slug:
        state.update(module=None, scene_id=None, map_id=None, revealed={}, here={}, requests=[], handout=None)
        await ctx.db.save_state(cid, state)
        return redirect(f"/c/{cid}/gm")
    await activate_module(ctx, slug)
    return redirect(f"/c/{cid}/run")


async def activate_module(ctx, slug: str) -> modules.Module:
    """Make `slug` this table's adventure: fresh fog and requests, its NPCs added as hidden sheets."""
    mod = modules.get(slug)
    if not mod:
        raise HTTPError(400, "That adventure can't be loaded; check its campaign.yaml.")
    cid, state = ctx.cid, ctx.camp["state"]
    state.update(module=slug, scene_id=None, map_id=None, revealed={}, here={}, requests=[], handout=None, shown={})
    for mid, m in mod.maps.items():
        for aid in m.get("start_revealed", []):
            _reveal(state, mid, aid)
    await ctx.db.save_state(cid, state)
    have = {c["data"]["name"] for c in await ctx.db.characters(cid, "npc")}
    for n in mod.data.get("npcs", []):
        if n.get("name") in have:
            continue
        d = rules.blank_character(n["name"])
        d.update(high_concept=n.get("high_concept", ""), notes=n.get("gm_notes", ""), hidden=True,
                 skills={k: int(v) for k, v in (n.get("skills") or {}).items()},
                 consequences=[{"severity": "minor", "text": "", "recovering": False}])
        asp = list(n.get("aspects", []))[:4]
        d["journey"] = asp + [""] * (4 - len(asp))
        d["stunts"] = [{"name": s.get("name", ""), "text": s.get("text", "")} if isinstance(s, dict)
                       else {"name": str(s), "text": ""} for s in n.get("stunts", [])]
        await ctx.db.create_character(cid, ctx.email, "npc", d)
    await ctx.db.add_log(cid, ctx.email, "note", {"system": True, "text": f"The GM opens a new adventure: {mod.title}."})
    ctx.hub.publish(cid, "party", "log", "map", "state")
    return mod


@router.post("/c/{cid}/run/scene")
async def start_scene(request: Request, cid: int):
    ctx = await camp_ctx(request, cid)
    ctx.require_gm()
    mod = _mod(ctx)
    sid = _txt((await form(request)).get("scene_id"), 80)
    s = mod.scenes.get(sid) if mod else None
    if not s:
        raise HTTPError(400, "Pick a scene from the loaded adventure.")
    state, scene = ctx.camp["state"], ctx.camp["scene"]
    state["scene_id"] = sid
    if s["map"]:
        state["map_id"] = s["map"]
        for aid in s["reveal"]:
            _reveal(state, s["map"], aid)
    keep = [a for a in scene["aspects"] if a.get("tag") in ("fact", "truth")]
    scene.update(name=s["title"], notes=s.get("goal", ""), boosts=[], aspects=keep)
    for text in s["aspects"]:
        scene["aspects"].append({"id": scene.get("next_id", 1), "text": text, "free": 0, "on": "", "tag": "",
                                 "by": "GM"})
        scene["next_id"] = scene.get("next_id", 1) + 1
    await ctx.db.save_state(cid, state)
    await ctx.db.save_scene(cid, scene)
    await ctx.db.add_log(cid, ctx.email, "note", {"system": True, "text": f"Scene: {s['title']}. {s['read_aloud']}".strip()})
    return changed(ctx, "state", "scene", "map", "log")


# =============================================================================================
# maps: reveal, show, inspect requests, roll calls
# =============================================================================================
@router.post("/c/{cid}/map/{op}")
async def map_op(request: Request, cid: int, op: str):
    ctx = await camp_ctx(request, cid)
    mod = _mod(ctx)
    if not mod:
        raise HTTPError(400, "No adventure is loaded.")
    f = await form(request)
    map_id, area_id = _txt(f.get("map"), 60), _txt(f.get("area"), 60)
    if map_id not in mod.maps or (area_id and area_id not in mod.maps[map_id]["areas"]):
        raise HTTPError(404, "No such map or area.")
    state = ctx.camp["state"]
    topics = ["map"]
    if op == "show":
        ctx.require_gm()
        state["map_id"] = map_id
    elif op in ("reveal", "hide", "here"):
        ctx.require_gm()
        a = mod.area(map_id, area_id)
        if op == "reveal":
            if _reveal(state, map_id, area_id):
                await ctx.db.add_log(cid, ctx.email, "note", {"system": True, "text": f"Discovered: {a['name']}."})
                topics.append("log")
            _close_requests(state, map_id, area_id, "done")
            topics.append("requests")
        elif op == "hide":
            state["revealed"][map_id] = [x for x in state["revealed"].get(map_id, []) if x != area_id]
            if state["here"].get(map_id) == area_id:
                state["here"].pop(map_id)
        else:
            if area_id not in _revealed(state, map_id):
                raise HTTPError(400, "Reveal the area first.")
            state["here"][map_id] = area_id
    elif op == "request":
        ch = await _roll_character(ctx, f.get("character_id"))
        if not ch or ch["kind"] != "pc":
            raise HTTPError(400, "Pick your explorer.")
        if area_id not in modules.frontier(mod.maps[map_id], _revealed(state, map_id)):
            raise HTTPError(400, "You can only ask about an unexplored area next to one you've found.")
        if any(r for r in state["requests"] if r["area"] == area_id and r["map"] == map_id
               and r["status"] in ("pending", "roll")):
            raise HTTPError(400, "Someone has already asked about that area.")
        a = mod.area(map_id, area_id)
        state["requests"].append({"id": state["next_req"], "map": map_id, "area": area_id, "char_id": ch["id"],
                                  "who": ch["data"]["name"], "email": ctx.email, "status": "pending",
                                  "label": a["teaser"] or "an unexplored area", "ts": time.time()})
        state["next_req"] += 1
        topics.append("requests")
    elif op == "call":
        ctx.require_gm()
        a = mod.area(map_id, area_id)
        _close_requests(state, map_id, area_id, "superseded")
        req = {"id": state["next_req"], "map": map_id, "area": area_id, "char_id": None, "who": "", "email": "",
               "label": a["teaser"] or a["name"], "ts": time.time()}
        state["next_req"] += 1
        _set_roll(req, f, a)
        tgt = _int(f.get("character_id"), 0, 0, 10**9)
        if tgt:
            req["char_id"] = tgt
        state["requests"].append(req)
        topics.append("requests")
    else:
        raise HTTPError(404, "Unknown map action.")
    await ctx.db.save_state(cid, state)
    return changed(ctx, *topics)


def _close_requests(state: dict, map_id: str, area_id: str, status: str) -> None:
    for r in state["requests"]:
        if r["map"] == map_id and r["area"] == area_id and r["status"] in ("pending", "roll"):
            r["status"] = status


def _set_roll(req: dict, f: dict, area: dict) -> None:
    disc = area.get("discover") or {}
    skills = [s.strip() for s in _txt(f.get("skills"), 120).split(",") if s.strip()] or list(disc.get("skills", []))
    action = f.get("action") if f.get("action") in rules.ACTIONS else disc.get("action", "discover")
    if action == "advantage":
        action = "create"
    req.update(status="roll", difficulty=_int(f.get("difficulty"), disc.get("difficulty", 2), -2, 8),
               skills=[s for s in skills if s in rules.SKILLS], action=action)


@router.post("/c/{cid}/request/{rid}")
async def resolve_request(request: Request, cid: int, rid: int):
    ctx = await camp_ctx(request, cid)
    ctx.require_gm()
    mod = _mod(ctx)
    state = ctx.camp["state"]
    req = next((r for r in state["requests"] if r["id"] == rid), None)
    if not req or not mod:
        raise HTTPError(404, "That request is gone.")
    f = await form(request)
    op = f.get("op")
    topics = ["requests", "map"]
    if op == "reveal":
        a = mod.area(req["map"], req["area"])
        if _reveal(state, req["map"], req["area"]):
            await ctx.db.add_log(cid, ctx.email, "note", {"system": True, "text": f"Discovered: {a['name']}."})
            topics.append("log")
        _close_requests(state, req["map"], req["area"], "done")
    elif op == "roll":
        _set_roll(req, f, mod.area(req["map"], req["area"]))
    elif op in ("deny", "dismiss"):
        req["status"] = "denied" if op == "deny" else "dismissed"
    else:
        raise HTTPError(400, "Reveal, call for a roll, or not yet.")
    await ctx.db.save_state(cid, state)
    return changed(ctx, *topics)


async def after_roll(ctx, f: dict, r: rules.Roll, ch: dict | None, data: dict) -> list[str]:
    """Called by the roll endpoint: a roll answering a roll call reveals its area on a success."""
    rid = _int(f.get("request_id"), 0, 0, 10**9)
    if not rid:
        return []
    state = ctx.camp["state"]
    req = next((x for x in state["requests"] if x["id"] == rid and x["status"] == "roll"), None)
    if not req or (req.get("char_id") and ch and req["char_id"] != ch["id"]):
        return []
    mod = _mod(ctx)
    a = mod.area(req["map"], req["area"]) if mod else None
    if not a:
        return []
    data["request"] = {"id": rid, "label": req["label"]}
    if r.outcome in ("succeed", "excel"):
        _reveal(state, req["map"], req["area"])
        _close_requests(state, req["map"], req["area"], "done")
        note = f"{data['who']} explores {req['label']}: discovered {a['name']}."
    else:
        req["status"] = "failed"
        req["result"] = r.outcome
        note = (f"{data['who']} tried to explore {req['label']} but didn't get through "
                f"({r.outcome}). The GM may still reveal it at a cost.")
    await ctx.db.save_state(ctx.cid, state)
    await ctx.db.add_log(ctx.cid, ctx.email, "note", {"system": True, "text": note})
    return ["map", "requests"]


# =============================================================================================
# handouts: push, clear, upload, serve
# =============================================================================================
@router.post("/c/{cid}/handout/{op}")
async def handout_op(request: Request, cid: int, op: str):
    ctx = await camp_ctx(request, cid)
    ctx.require_gm()
    state = ctx.camp["state"]
    if op == "push":
        f = await form(request)
        h = _handout(ctx, _txt(f.get("key"), 120))
        if not h:
            raise HTTPError(404, "No such handout.")
        to = _txt(f.get("to"), 200).lower() or "all"
        effect = f.get("effect") if f.get("effect") in EFFECTS else h["effect"]
        state["handout_seq"] += 1
        state["handout"] = {"key": h["key"], "to": to, "effect": effect,
                            "caption": _txt(f.get("caption"), 200) or h["caption"], "seq": state["handout_seq"]}
        seen = state["shown"].setdefault(h["key"], [])
        if to not in seen:
            seen.append(to)
    elif op == "clear":
        state["handout"] = None
    elif op == "upload":
        f = await request.form()
        up = f.get("file")
        if not up or not getattr(up, "filename", ""):
            raise HTTPError(400, "Choose a file.")
        ext = Path(up.filename).suffix.lower()
        if ext not in UPLOAD_TYPES:
            raise HTTPError(400, "Images (PNG, JPG, GIF, WebP) or video (MP4, WebM) only.")
        data = await up.read()
        if len(data) > MAX_UPLOAD:
            raise HTTPError(400, "That file is over 20 MB.")
        uid = secrets.token_hex(8)
        (_uploads_dir(request, cid) / f"{uid}{ext}").write_bytes(data)
        state["uploads"].append({"id": uid, "file": f"{uid}{ext}", "caption": _txt(f.get("caption"), 200),
                                 "type": modules.MEDIA_TYPES.get(ext) or mimetypes.guess_type(up.filename)[0]})
    elif op == "delete":
        uid = _txt((await form(request)).get("id"), 40)
        u = next((u for u in state["uploads"] if u["id"] == uid), None)
        if u:
            (_uploads_dir(request, cid) / u["file"]).unlink(missing_ok=True)
            state["uploads"].remove(u)
            state["shown"].pop("u:" + uid, None)
            if state["handout"] and state["handout"]["key"] == "u:" + uid:
                state["handout"] = None
    else:
        raise HTTPError(404, "Unknown handout action.")
    await ctx.db.save_state(cid, state)
    return changed(ctx, "handout", "handouts")


@router.get("/c/{cid}/media/{key}")
async def media(request: Request, cid: int, key: str):
    ctx = await camp_ctx(request, cid)
    h = _handout(ctx, key)
    if not h or not _may_see(ctx, key) or not h["path"].exists():
        raise HTTPError(404, "Nothing to see here yet.")
    return FileResponse(h["path"], media_type=h["type"],
                        headers={"Cache-Control": "private, max-age=300", "Content-Security-Policy": "sandbox"})


@router.get("/c/{cid}/handout/current", response_class=HTMLResponse)
async def current_handout(request: Request, cid: int):
    ctx = await camp_ctx(request, cid)
    cur = ctx.camp["state"].get("handout")
    # The GM sees what's showing on the GM Screen; ?preview shows it to them full-screen too.
    if ctx.is_gm and "preview" not in request.query_params:
        return HTMLResponse("")
    if not cur or not (ctx.is_gm or cur["to"] in ("all", ctx.email)):
        return HTMLResponse("")
    h = _handout(ctx, cur["key"])
    if not h:
        return HTMLResponse("")
    return page(request, "partials/handout_overlay.html", ctx, cur=cur, h=h, inline=_inline_svg(h))


@router.get("/c/{cid}/handouts", response_class=HTMLResponse)
async def gallery(request: Request, cid: int):
    ctx = await camp_ctx(request, cid)
    items = [h for h in _all_handouts(ctx) if _may_see(ctx, h["key"]) and
             (ctx.is_gm or h["key"] in ctx.camp["state"]["shown"])]
    for h in items:
        h["inline"] = _inline_svg(h)
    return page(request, "gallery.html", ctx, tab="me", items=items)


# =============================================================================================
# the player screen
# =============================================================================================
async def _me_context(ctx, chid: int | None = None) -> dict:
    party = await _party(ctx)
    mine = _my_pcs(ctx, party)
    if ctx.is_gm:
        mine = party["pcs"]
    ch = next((c for c in mine if c["id"] == chid), mine[0] if mine else None)
    state = ctx.camp["state"]
    mod = _mod(ctx)
    map_id = state.get("map_id") if mod and state.get("map_id") in (mod.maps if mod else {}) else None
    area = None
    teasers = []
    if map_id:
        here = state["here"].get(map_id)
        if here and here in _revealed(state, map_id):
            area = modules.player_area(mod.area(map_id, here))
        mmap = mod.maps[map_id]
        teasers = [mmap["areas"][a]["teaser"] or "an unexplored area"
                   for a in modules.frontier(mmap, _revealed(state, map_id))]
    rolls = _open_rolls_for(state, ch)
    sugg = suggest.for_player(ch, ctx.camp["scene"], area, teasers,
                              {"label": rolls[0]["label"], "action": rolls[0]["action"],
                               "difficulty": rolls[0]["difficulty"], "skills": rolls[0]["skills"]} if rolls else None
                              ) if ch else []
    return {"party": party, "mine": mine, "ch": ch, "mod": mod, "map_id": map_id, "area": area, "rolls": rolls,
            "sugg": sugg, "scene": ctx.camp["scene"], "state": state}


@router.get("/c/{cid}/me", response_class=HTMLResponse)
async def me(request: Request, cid: int):
    ctx = await camp_ctx(request, cid)
    data = await _me_context(ctx, _int(request.query_params.get("ch"), 0, 0, 10**9))
    return page(request, "me.html", ctx, tab="me", **data)


@router.get("/c/{cid}/me/frag/{name}", response_class=HTMLResponse)
async def me_frag(request: Request, cid: int, name: str):
    ctx = await camp_ctx(request, cid)
    data = await _me_context(ctx, _int(request.query_params.get("ch"), 0, 0, 10**9))
    if name not in ("char", "suggest", "map", "scene"):
        raise HTTPError(404, "No such fragment.")
    if name == "map":
        data["svg"] = _player_svg(ctx, data["mod"], data["map_id"])
    return page(request, f"partials/me_{name}.html", ctx, **data)


def _picture_url(ctx, mod, map_id, gm: bool) -> str:
    if not modules.is_raster(mod.maps[map_id]):
        return ""
    seen = None if gm else _revealed(ctx.camp["state"], map_id)
    return f"/c/{ctx.camp['id']}/mapimg/{map_id}?v={modules.picture_version(mod, map_id, seen)}"


def _player_svg(ctx, mod, map_id) -> str:
    if not mod or not map_id:
        return ""
    state = ctx.camp["state"]
    mine = {r["area"] for r in state["requests"] if r["map"] == map_id and r["status"] in ("pending", "roll")}
    return modules.render_map(mod, map_id, _revealed(state, map_id), gm=False, pending=mine,
                              image_url=_picture_url(ctx, mod, map_id, gm=False))


@router.get("/c/{cid}/mapimg/{map_id}")
async def map_image(request: Request, cid: int, map_id: str):
    """A picture map. Players get it with every unrevealed area fogged on the server; the GM gets the original."""
    ctx = await camp_ctx(request, cid)
    mod = _mod(ctx)
    if not mod or map_id not in mod.maps or not modules.is_raster(mod.maps[map_id]):
        raise HTTPError(404, "No such map.")
    seen = None if ctx.is_gm else _revealed(ctx.camp["state"], map_id)
    body, kind = modules.map_picture(mod, map_id, seen)
    return Response(body, media_type=kind, headers={"Cache-Control": "private, max-age=86400"})


@router.get("/c/{cid}/me/area/{map_id}/{area_id}", response_class=HTMLResponse)
async def me_area(request: Request, cid: int, map_id: str, area_id: str):
    ctx = await camp_ctx(request, cid)
    mod = _mod(ctx)
    a = mod.area(map_id, area_id) if mod else None
    if not a or area_id not in _revealed(ctx.camp["state"], map_id):
        raise HTTPError(404, "Unexplored.")
    return page(request, "partials/me_area.html", ctx, area=modules.player_area(a), map_id=map_id)


# =============================================================================================
# the GM screen
# =============================================================================================
async def _run_context(ctx) -> dict:
    mod = _mod(ctx)
    state = ctx.camp["state"]
    party = await _party(ctx)
    scene = mod.scenes.get(state.get("scene_id")) if mod else None
    npcs = []
    if scene:
        names = set(scene.get("npcs", []))
        npcs = [c for c in party["npcs"] if c["data"]["name"] in names]
    return {"mod": mod, "state": state, "party": party, "mscene": scene, "npcs": npcs,
            "compels": suggest.compel_ideas(party["pcs"]), "tips": suggest.GM_TIPS,
            "handouts": _all_handouts(ctx), "effects": EFFECTS, "available": modules.available()}


@router.get("/c/{cid}/run", response_class=HTMLResponse)
async def run(request: Request, cid: int):
    ctx = await camp_ctx(request, cid)
    ctx.require_gm()
    data = await _run_context(ctx)
    data["map_id"] = _gm_map_id(request, data["mod"], ctx.camp["state"])
    data["svg"] = _gm_svg(ctx, data["mod"], data["map_id"])
    return page(request, "run.html", ctx, tab="run", **data)


def _gm_map_id(request: Request, mod, state: dict) -> str | None:
    """The map tab the GM picked, else the one players are looking at, else the adventure's first."""
    if not mod:
        return None
    for mid in (request.query_params.get("map"), state.get("map_id")):
        if mid in mod.maps:
            return mid
    return next(iter(mod.maps), None)


def _gm_svg(ctx, mod, map_id) -> str:
    if not mod or not map_id or map_id not in mod.maps:
        return ""
    state = ctx.camp["state"]
    pend = {r["area"] for r in state["requests"] if r["map"] == map_id and r["status"] in ("pending", "roll")}
    return modules.render_map(mod, map_id, _revealed(state, map_id), gm=True, pending=pend,
                              image_url=_picture_url(ctx, mod, map_id, gm=True))


@router.get("/c/{cid}/run/frag/{name}", response_class=HTMLResponse)
async def run_frag(request: Request, cid: int, name: str):
    ctx = await camp_ctx(request, cid)
    ctx.require_gm()
    if name not in ("scene", "map", "requests", "handouts", "compels"):
        raise HTTPError(404, "No such fragment.")
    data = await _run_context(ctx)
    data["map_id"] = _gm_map_id(request, data["mod"], ctx.camp["state"])
    if name == "map":
        data["svg"] = _gm_svg(ctx, data["mod"], data["map_id"])
    return page(request, f"partials/run_{name}.html", ctx, **data)


@router.get("/c/{cid}/run/area/{map_id}/{area_id}", response_class=HTMLResponse)
async def run_area(request: Request, cid: int, map_id: str, area_id: str):
    ctx = await camp_ctx(request, cid)
    ctx.require_gm()
    mod = _mod(ctx)
    a = mod.area(map_id, area_id) if mod else None
    if not a:
        raise HTTPError(404, "No such area.")
    state = ctx.camp["state"]
    hs = [h for h in (_handout(ctx, "m:" + k) for k in a.get("handouts", [])) if h]
    return page(request, "partials/run_area.html", ctx, area=a, map_id=map_id, mod=mod,
                revealed=area_id in _revealed(state, map_id), here=state["here"].get(map_id) == area_id,
                handouts=hs, effects=EFFECTS, pcs=(await _party(ctx))["pcs"])


@router.post("/c/{cid}/run/aspect")
async def place_area_aspect(request: Request, cid: int):
    """Put an area's or scene's aspect on the scene board."""
    ctx = await camp_ctx(request, cid)
    ctx.require_gm()
    text = _txt((await form(request)).get("text"), 120)
    scene = ctx.camp["scene"]
    if text and not any(a["text"] == text for a in scene["aspects"]):
        scene["aspects"].append({"id": scene.get("next_id", 1), "text": text, "free": 0, "on": "", "tag": "",
                                 "by": "GM"})
        scene["next_id"] = scene.get("next_id", 1) + 1
        await ctx.db.save_scene(cid, scene)
    return changed(ctx, "scene")


@router.get("/guide", response_class=HTMLResponse)
async def guide(request: Request):
    from .main import user_ctx
    ctx = await user_ctx(request)
    return page(request, "guide.html", ctx, tab="guide", tips=suggest.GM_TIPS)


@router.get("/c/{cid}/guide", response_class=HTMLResponse)
async def camp_guide(request: Request, cid: int):
    ctx = await camp_ctx(request, cid)
    return page(request, "guide.html", ctx, tab="guide", tips=suggest.GM_TIPS)
