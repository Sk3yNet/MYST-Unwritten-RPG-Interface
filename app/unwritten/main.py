"""FastAPI app: pages, htmx fragments, and the live (SSE) stream per campaign.

State-changing requests come from htmx, answer with an empty body plus an HX-Trigger header naming the fragments
to refresh, and publish the same topics to everyone else at the table through the SSE hub.
"""
from __future__ import annotations

import asyncio
import json
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import dni, rules
from .config import Settings
from .db import DB
from .hub import Hub
from .version import CHANGES, VERSION

HERE = Path(__file__).parent
templates = Jinja2Templates(directory=str(HERE / "templates"))
templates.env.globals.update(rules=rules, dni=dni, VERSION=VERSION, ladder=rules.ladder)


def _dni_stamp(ts: float) -> str:
    d = dni.to_dni(datetime.fromtimestamp(ts, timezone.utc))
    return f"{d['vailee_name']} {d['yahr']} · bell {d['bell']}"


def _local_stamp(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


templates.env.filters["dni_stamp"] = _dni_stamp
templates.env.filters["utc_stamp"] = _local_stamp


class HTTPError(Exception):
    def __init__(self, status: int, msg: str):
        self.status, self.msg = status, msg


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.settings = Settings()
    app.state.db = DB(app.state.settings.db_path)
    await app.state.db.open()
    app.state.hub = Hub()
    yield
    await app.state.db.close()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")


_CAMP_PATH = re.compile(r"^/c/(\d+)/")
_camp_locks: dict[int, asyncio.Lock] = {}


@app.middleware("http")
async def one_change_at_a_time(request: Request, call_next):
    """Scenes and sheets are read-modify-write JSON records: run a campaign's changes one at a time (single worker)."""
    m = _CAMP_PATH.match(request.url.path)
    if request.method == "GET" or not m:
        return await call_next(request)
    async with _camp_locks.setdefault(int(m.group(1)), asyncio.Lock()):
        return await call_next(request)


@app.exception_handler(HTTPError)
async def _http_error(request: Request, exc: HTTPError):
    return PlainTextResponse(exc.msg, status_code=exc.status)


# =============================================================================================
# auth & access
# =============================================================================================
def current_user(request: Request) -> str:
    s: Settings = request.app.state.settings
    email = (request.headers.get(s.auth_header) or "").strip().lower()
    if not email and s.dev_user:
        email = s.dev_user
    if not email:
        raise HTTPError(401, "Not signed in (no identity header from the auth proxy).")
    if not s.may_sign_in(email):
        raise HTTPError(403, f"{email} is not on this table's guest list. Ask the host to add you.")
    if request.method not in ("GET", "HEAD") and not request.headers.get("hx-request"):
        # Every change comes from htmx; a cross-site form can't set this header.
        raise HTTPError(403, "Missing HX-Request header.")
    return email


class Ctx:
    """Who is asking, about which campaign, in which role."""

    def __init__(self, request: Request, email: str, user: dict, camp: dict | None = None, role: str | None = None):
        self.request, self.email, self.user, self.camp, self.role = request, email, user, camp, role

    @property
    def db(self) -> DB:
        return self.request.app.state.db

    @property
    def hub(self) -> Hub:
        return self.request.app.state.hub

    @property
    def is_gm(self) -> bool:
        return self.role == "gm"

    @property
    def cid(self) -> int:
        return self.camp["id"]

    def require_gm(self) -> None:
        if not self.is_gm:
            raise HTTPError(403, "Only the GM can do that.")

    def can_edit(self, ch: dict) -> bool:
        return self.is_gm or ch["owner_email"] == self.email

    def can_see(self, ch: dict) -> bool:
        return self.is_gm or not (ch["kind"] == "npc" and ch["data"].get("hidden"))


async def user_ctx(request: Request) -> Ctx:
    email = current_user(request)
    user = await request.app.state.db.ensure_user(email)
    return Ctx(request, email, user)


async def camp_ctx(request: Request, cid: int) -> Ctx:
    ctx = await user_ctx(request)
    camp = await ctx.db.campaign(cid)
    role = await ctx.db.role(cid, ctx.email) if camp else None
    if not camp or not role:
        raise HTTPError(404, "No such campaign, or you haven't joined it. Ask your GM for the invite link.")
    ctx.camp, ctx.role = camp, role
    return ctx


async def char_ctx(request: Request, cid: int, chid: int, edit: bool = False) -> tuple[Ctx, dict]:
    ctx = await camp_ctx(request, cid)
    ch = await ctx.db.character(chid)
    if not ch or ch["campaign_id"] != cid or not ctx.can_see(ch):
        raise HTTPError(404, "No such character.")
    if edit and not ctx.can_edit(ch):
        raise HTTPError(403, "That's not your character.")
    ch["data"] = rules.normalize_character(ch["data"])
    return ctx, ch


def changed(ctx: Ctx, *topics: str, status: int = 200) -> Response:
    """Tell everyone (others via SSE, the caller via HX-Trigger) which fragments to refresh."""
    ctx.hub.publish(ctx.cid, *topics)
    return Response(status_code=status, headers={"HX-Trigger": json.dumps({t: True for t in topics})})


def redirect(url: str) -> Response:
    return Response(status_code=200, headers={"HX-Redirect": url})


def page(request: Request, name: str, ctx: Ctx | None = None, **kw) -> HTMLResponse:
    return templates.TemplateResponse(request, name, {"ctx": ctx, **kw})


def _txt(v, limit: int = 300) -> str:
    return str(v or "").strip()[:limit]


def _int(v, default: int = 0, lo: int = -99, hi: int = 99) -> int:
    try:
        return max(lo, min(hi, int(str(v).strip())))
    except (TypeError, ValueError):
        return default


async def form(request: Request) -> dict:
    return dict(await request.form())


# =============================================================================================
# home, profile, campaigns, invites
# =============================================================================================
@app.get("/healthz")
async def healthz():
    return PlainTextResponse("ok")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    ctx = await user_ctx(request)
    camps = await ctx.db.campaigns_for(ctx.email)
    return page(request, "home.html", ctx, camps=camps, may_create=request.app.state.settings.may_create(ctx.email),
                changes=CHANGES)


@app.post("/profile")
async def profile(request: Request):
    ctx = await user_ctx(request)
    f = await form(request)
    await ctx.db.set_user_name(ctx.email, _txt(f.get("name"), 60) or ctx.email.split("@")[0])
    return redirect("/")


@app.post("/campaigns")
async def create_campaign(request: Request):
    ctx = await user_ctx(request)
    if not request.app.state.settings.may_create(ctx.email):
        raise HTTPError(403, "This server only lets its listed GMs start campaigns.")
    name = _txt((await form(request)).get("name"), 80) or "Untitled Journey"
    cid = await ctx.db.create_campaign(name, ctx.email)
    return redirect(f"/c/{cid}")


@app.get("/join/{token}", response_class=HTMLResponse)
async def join_page(request: Request, token: str):
    ctx = await user_ctx(request)
    camp = await ctx.db.campaign_by_invite(token)
    if not camp:
        raise HTTPError(404, "This invite link is no longer valid. Ask your GM for a fresh one.")
    role = await ctx.db.role(camp["id"], ctx.email)
    gm = (await ctx.db.user_names([camp["gm_email"]])).get(camp["gm_email"], camp["gm_email"])
    return page(request, "join.html", ctx, camp=camp, role=role, token=token, gm_name=gm)


@app.post("/join/{token}")
async def join(request: Request, token: str):
    ctx = await user_ctx(request)
    camp = await ctx.db.campaign_by_invite(token)
    if not camp:
        raise HTTPError(404, "This invite link is no longer valid.")
    await ctx.db.add_member(camp["id"], ctx.email, "player")
    ctx.hub.publish(camp["id"], "party")
    await ctx.db.add_log(camp["id"], ctx.email, "note", {"text": f"{ctx.user['name']} joined the table."})
    ctx.hub.publish(camp["id"], "log")
    return redirect(f"/c/{camp['id']}")


# =============================================================================================
# campaign pages
# =============================================================================================
async def _party(ctx: Ctx) -> dict:
    chars = [c for c in await ctx.db.characters(ctx.cid) if ctx.can_see(c)]
    for c in chars:
        c["data"] = rules.normalize_character(c["data"])
    names = await ctx.db.user_names({c["owner_email"] for c in chars})
    return {"pcs": [c for c in chars if c["kind"] == "pc"], "npcs": [c for c in chars if c["kind"] == "npc"],
            "names": names}


def _my_chars(ctx: Ctx, party: dict) -> list[dict]:
    if ctx.is_gm:
        return party["pcs"] + party["npcs"]
    return [c for c in party["pcs"] if c["owner_email"] == ctx.email]


@app.get("/c/{cid}", response_class=HTMLResponse)
async def table(request: Request, cid: int):
    ctx = await camp_ctx(request, cid)
    party = await _party(ctx)
    return page(request, "table.html", ctx, tab="table", party=party, mine=_my_chars(ctx, party),
                log=await ctx.db.recent_log(cid), scene=ctx.camp["scene"], roll_char=None)


@app.get("/c/{cid}/frag/{name}", response_class=HTMLResponse)
async def fragment(request: Request, cid: int, name: str):
    ctx = await camp_ctx(request, cid)
    if name == "scene":
        return page(request, "partials/scene.html", ctx, scene=ctx.camp["scene"])
    if name == "log":
        return page(request, "partials/log.html", ctx, log=await ctx.db.recent_log(cid))
    if name == "party":
        return page(request, "partials/party.html", ctx, party=await _party(ctx))
    if name == "roller":
        party = await _party(ctx)
        mine = _my_chars(ctx, party)
        chid = _int(request.query_params.get("character_id"), 0, 0, 10**9)
        sel = next((c for c in mine if c["id"] == chid), None)
        return page(request, "partials/roller.html", ctx, mine=mine, roll_char=sel, scene=ctx.camp["scene"])
    raise HTTPError(404, "No such fragment.")


@app.get("/live/c/{cid}")
async def live(request: Request, cid: int):
    ctx = await camp_ctx(request, cid)
    q = ctx.hub.subscribe(cid)

    async def gen():
        try:
            yield "retry: 4000\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    topic = await asyncio.wait_for(q.get(), timeout=20)
                    yield f"event: {topic}\ndata: 1\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            ctx.hub.unsubscribe(cid, q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# =============================================================================================
# rolls, invokes, compels, notes
# =============================================================================================
async def _roll_character(ctx: Ctx, chid) -> dict | None:
    chid = _int(chid, 0, 0, 10**9)
    if not chid:
        return None
    ch = await ctx.db.character(chid)
    if not ch or ch["campaign_id"] != ctx.cid or not ctx.can_edit(ch):
        raise HTTPError(403, "You can only roll for your own characters.")
    ch["data"] = rules.normalize_character(ch["data"])
    return ch


@app.post("/c/{cid}/roll")
async def roll(request: Request, cid: int):
    ctx = await camp_ctx(request, cid)
    f = await form(request)
    ch = await _roll_character(ctx, f.get("character_id"))
    action = f.get("action") if f.get("action") in rules.ACTIONS else "overcome"
    skill = _txt(f.get("skill"), 40)
    if ch:
        value = ch["data"]["skills"].get(skill, 0) if skill else 0
    else:
        if not ctx.is_gm:
            raise HTTPError(400, "Pick one of your characters to roll for.")
        value = _int(f.get("skill_value"), 0, -2, 12)
    opp = f.get("opposition", "")
    r = rules.Roll(action=action, skill=skill or "Mediocre", skill_value=value, dice=rules.roll_fate_dice(),
                   opposition=None if str(opp).strip() == "" else _int(opp, 0, -4, 12),
                   stunt_bonus=_int(f.get("stunt_bonus"), 0, -4, 6), teamwork=_int(f.get("teamwork"), 0, 0, 6),
                   dangerous=bool(f.get("dangerous")))
    data = {"roll": r.to_dict(), "character_id": ch["id"] if ch else None,
            "who": ch["data"]["name"] if ch else (_txt(f.get("who"), 60) or "GM"),
            "intent": _txt(f.get("intent"), 200), "questions_used": 0, "rerolls": []}
    await ctx.db.add_log(cid, ctx.email, "roll", data)
    return changed(ctx, "log")


def _invoke_options(ch: dict | None, scene: dict) -> list[str]:
    opts = []
    if ch:
        d = ch["data"]
        opts += [a for a in [d["high_concept"], *d["journey"]] if a]
        opts += [s["text"] for s in d["consequences"] if s["text"]]
    opts += [a["text"] for a in scene["aspects"]]
    return opts


@app.post("/c/{cid}/log/{lid}/invoke")
async def invoke(request: Request, cid: int, lid: int):
    ctx = await camp_ctx(request, cid)
    entry = await ctx.db.log_entry(lid)
    if not entry or entry["campaign_id"] != cid or entry["kind"] != "roll":
        raise HTTPError(404, "No such roll.")
    data = entry["data"]
    ch = await ctx.db.character(data["character_id"]) if data.get("character_id") else None
    if not (ctx.is_gm or entry["email"] == ctx.email):
        raise HTTPError(403, "Only the roller or the GM can invoke on this roll.")
    f = await form(request)
    source, effect = f.get("source", ""), f.get("effect", "plus2")
    scene = ctx.camp["scene"]
    r = rules.Roll.from_dict(data["roll"])
    topics = ["log"]
    if source == "fp":
        label = _txt(f.get("aspect"), 120)
        if not label:
            raise HTTPError(400, "Name the aspect you invoke.")
        if any(m.kind == "invoke" and m.label == label for m in r.modifiers) or \
                any(x.get("source") == "fp" and x.get("label") == label for x in data["rerolls"]):
            raise HTTPError(400, "Each aspect can be invoked with a fate point only once per roll.")
        if ch:
            cd = rules.normalize_character(ch["data"])
            if cd["fate_points"] < 1:
                raise HTTPError(400, f"{cd['name']} has no fate points left. (Out of points? Consider a sacrifice.)")
            cd["fate_points"] -= 1
            await ctx.db.save_character(ch["id"], cd)
            topics += ["party", f"ch-{ch['id']}"]
        kind = "invoke"
    elif source.startswith("free:"):
        a = next((a for a in scene["aspects"] if str(a["id"]) == source[5:]), None)
        if not a or a["free"] < 1:
            raise HTTPError(400, "That aspect has no free invokes left.")
        a["free"] -= 1
        label, kind = a["text"], "free"
        await ctx.db.save_scene(cid, scene)
        topics.append("scene")
    elif source.startswith("boost:"):
        b = next((b for b in scene["boosts"] if str(b["id"]) == source[6:]), None)
        if not b:
            raise HTTPError(400, "That boost is gone.")
        scene["boosts"].remove(b)
        label, kind = b["text"] or "boost", "boost"
        await ctx.db.save_scene(cid, scene)
        topics.append("scene")
    else:
        raise HTTPError(400, "Pick what you're spending: a fate point, a free invoke or a boost.")
    if effect == "reroll":
        data["rerolls"].append({"source": "fp" if kind == "invoke" else kind, "label": label, "from": r.dice})
        r.dice = rules.roll_fate_dice()
    else:
        r.modifiers.append(rules.Modifier(kind=kind, label=label, value=2))
    data["roll"] = r.to_dict()
    await ctx.db.save_log(lid, data)
    return changed(ctx, *topics)


@app.post("/c/{cid}/log/{lid}/question")
async def use_question(request: Request, cid: int, lid: int):
    ctx = await camp_ctx(request, cid)
    entry = await ctx.db.log_entry(lid)
    if not entry or entry["campaign_id"] != cid or entry["kind"] != "roll":
        raise HTTPError(404, "No such roll.")
    d = entry["data"]
    total = rules.Roll.from_dict(d["roll"]).summary()["questions"]
    delta = 1 if (await form(request)).get("op") != "undo" else -1
    d["questions_used"] = max(0, min(total, d.get("questions_used", 0) + delta))
    await ctx.db.save_log(lid, d)
    return changed(ctx, "log")


@app.post("/c/{cid}/compel")
async def propose_compel(request: Request, cid: int):
    ctx = await camp_ctx(request, cid)
    f = await form(request)
    ch = await ctx.db.character(_int(f.get("character_id"), 0, 0, 10**9))
    if not ch or ch["campaign_id"] != cid or ch["kind"] != "pc":
        raise HTTPError(400, "Pick a player character to compel.")
    aspect = _txt(f.get("aspect"), 120)
    if not aspect:
        raise HTTPError(400, "Which aspect is being compelled?")
    await ctx.db.add_log(cid, ctx.email, "compel", {"character_id": ch["id"], "who": ch["data"]["name"],
                                                   "aspect": aspect, "text": _txt(f.get("text"), 300),
                                                   "status": "pending"})
    return changed(ctx, "log")


@app.post("/c/{cid}/log/{lid}/compel")
async def resolve_compel(request: Request, cid: int, lid: int):
    ctx = await camp_ctx(request, cid)
    entry = await ctx.db.log_entry(lid)
    if not entry or entry["campaign_id"] != cid or entry["kind"] != "compel":
        raise HTTPError(404, "No such compel.")
    d = entry["data"]
    if d["status"] != "pending":
        raise HTTPError(400, "That compel is already settled.")
    ch = await ctx.db.character(d["character_id"])
    if not ch:
        raise HTTPError(404, "That character is gone.")
    if not ctx.can_edit(ch):
        raise HTTPError(403, "Only the character's player (or the GM) decides on a compel.")
    cd = rules.normalize_character(ch["data"])
    op = (await form(request)).get("op")
    if op == "accept":
        cd["fate_points"] += 1
        d["status"] = "accepted"
    elif op == "refuse":
        if cd["fate_points"] < 1:
            raise HTTPError(400, "Buying off a compel costs a fate point, and there are none left.")
        cd["fate_points"] -= 1
        d["status"] = "refused"
    elif op == "withdraw" and (ctx.is_gm or entry["email"] == ctx.email):
        d["status"] = "withdrawn"
    else:
        raise HTTPError(400, "Accept or buy off.")
    await ctx.db.save_character(ch["id"], cd)
    await ctx.db.save_log(lid, d)
    return changed(ctx, "log", "party", f"ch-{ch['id']}")


@app.post("/c/{cid}/note")
async def note(request: Request, cid: int):
    ctx = await camp_ctx(request, cid)
    text = _txt((await form(request)).get("text"), 1000)
    if text:
        await ctx.db.add_log(cid, ctx.email, "note", {"text": text, "by": ctx.user["name"]})
    return changed(ctx, "log")


# =============================================================================================
# scene board
# =============================================================================================
def _next_id(scene: dict) -> int:
    scene["next_id"] = scene.get("next_id", 1) + 1
    return scene["next_id"] - 1


@app.post("/c/{cid}/scene/{op}")
async def scene_op(request: Request, cid: int, op: str):
    ctx = await camp_ctx(request, cid)
    f = await form(request)
    scene = ctx.camp["scene"]
    topics = ["scene"]
    if op == "aspect":
        text = _txt(f.get("text"), 120)
        if not text:
            raise HTTPError(400, "An aspect needs a name.")
        scene["aspects"].append({"id": _next_id(scene), "text": text, "free": _int(f.get("free"), 0, 0, 9),
                                 "on": _txt(f.get("on"), 60), "tag": _txt(f.get("tag"), 20), "by": ctx.user["name"]})
    elif op in ("inc", "dec", "remove"):
        a = next((a for a in scene["aspects"] if a["id"] == _int(f.get("id"))), None)
        if not a:
            raise HTTPError(404, "That aspect is gone.")
        if op == "remove":
            scene["aspects"].remove(a)
        else:
            a["free"] = max(0, min(9, a["free"] + (1 if op == "inc" else -1)))
    elif op == "boost":
        scene["boosts"].append({"id": _next_id(scene), "text": _txt(f.get("text"), 120),
                                "holder": _txt(f.get("holder"), 60)})
    elif op == "unboost":
        scene["boosts"] = [b for b in scene["boosts"] if b["id"] != _int(f.get("id"))]
    elif op == "promote":
        b = next((b for b in scene["boosts"] if b["id"] == _int(f.get("id"))), None)
        if b:
            scene["boosts"].remove(b)
            scene["aspects"].append({"id": _next_id(scene), "text": b["text"] or "Promoted boost", "free": 1,
                                     "on": b["holder"], "tag": "", "by": ctx.user["name"]})
    elif op == "meta":
        ctx.require_gm()
        scene["name"] = _txt(f.get("name"), 120)
        scene["notes"] = _txt(f.get("notes"), 2000)
    elif op in ("end", "session", "chapter"):
        ctx.require_gm()
        fn = {"end": rules.end_scene, "session": rules.start_session, "chapter": rules.start_chapter}[op]
        for ch in await ctx.db.characters(cid, "pc"):
            await ctx.db.save_character(ch["id"], fn(rules.normalize_character(ch["data"])))
            topics.append(f"ch-{ch['id']}")
        msg = {"end": "Scene ended: boosts cleared, recovering minor consequences healed.",
               "session": "New session: fate points refilled to refresh (extras kept); recovering minor and moderate "
                          "consequences healed.",
               "chapter": "New chapter: fate points reset to refresh; all recovering consequences healed."}[op]
        if op == "end":
            scene["boosts"] = []
            if f.get("clear"):
                scene["aspects"] = [a for a in scene["aspects"] if a.get("tag") == "keep"]
        await ctx.db.add_log(cid, ctx.email, "note", {"text": msg, "system": True})
        topics += ["party", "log"]
    else:
        raise HTTPError(404, "Unknown scene action.")
    await ctx.db.save_scene(cid, scene)
    return changed(ctx, *topics)


@app.post("/c/{cid}/milestone")
async def milestone(request: Request, cid: int):
    ctx = await camp_ctx(request, cid)
    ctx.require_gm()
    level = (await form(request)).get("level")
    if level not in rules.MILESTONES:
        raise HTTPError(400, "Pick a milestone level.")
    if level in ("significant", "major"):
        for ch in await ctx.db.characters(cid, "pc"):
            d = rules.normalize_character(ch["data"])
            d["skill_points_banked"] += 1
            await ctx.db.save_character(ch["id"], d)
    await ctx.db.add_log(cid, ctx.email, "milestone", {"level": level})
    return changed(ctx, "log", "party")


# =============================================================================================
# characters
# =============================================================================================
@app.get("/c/{cid}/party", response_class=HTMLResponse)
async def party_page(request: Request, cid: int):
    ctx = await camp_ctx(request, cid)
    return page(request, "party.html", ctx, tab="party", party=await _party(ctx))


@app.post("/c/{cid}/characters")
async def create_character(request: Request, cid: int):
    ctx = await camp_ctx(request, cid)
    f = await form(request)
    kind = "npc" if f.get("kind") == "npc" else "pc"
    if kind == "npc":
        ctx.require_gm()
    data = rules.blank_character(_txt(f.get("name"), 80) or ("New NPC" if kind == "npc" else "New Explorer"))
    if kind == "npc":
        data["hidden"] = True
        data["consequences"] = [{"severity": "minor", "text": "", "recovering": False}]
    chid = await ctx.db.create_character(cid, ctx.email, kind, data)
    ctx.hub.publish(cid, "party")
    return redirect(f"/c/{cid}/ch/{chid}")


@app.post("/c/{cid}/characters/import")
async def import_character(request: Request, cid: int):
    ctx = await camp_ctx(request, cid)
    raw = (await form(request)).get("json", "")
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError
        data = rules.normalize_character({k: v for k, v in data.items() if k in rules.blank_character()})
    except (ValueError, TypeError, AttributeError):
        raise HTTPError(400, "That isn't a character export (paste the JSON from a sheet's Export button).")
    chid = await ctx.db.create_character(cid, ctx.email, "pc", data)
    ctx.hub.publish(cid, "party")
    return redirect(f"/c/{cid}/ch/{chid}")


@app.get("/c/{cid}/ch/{chid}", response_class=HTMLResponse)
async def sheet_page(request: Request, cid: int, chid: int):
    ctx, ch = await char_ctx(request, cid, chid)
    names = await ctx.db.user_names([ch["owner_email"]])
    return page(request, "sheet.html", ctx, tab="party", ch=ch, owner=names.get(ch["owner_email"], ""),
                editable=ctx.can_edit(ch))


@app.get("/c/{cid}/ch/{chid}/frag", response_class=HTMLResponse)
async def sheet_frag(request: Request, cid: int, chid: int):
    ctx, ch = await char_ctx(request, cid, chid)
    return page(request, "partials/sheet_body.html", ctx, ch=ch, editable=ctx.can_edit(ch))


@app.get("/c/{cid}/ch/{chid}/export")
async def sheet_export(request: Request, cid: int, chid: int):
    _, ch = await char_ctx(request, cid, chid)
    fn = re.sub(r"[^A-Za-z0-9_-]+", "_", ch["data"]["name"]) or "character"
    return JSONResponse(ch["data"], headers={"Content-Disposition": f'attachment; filename="{fn}.json"'})


_FIELD = re.compile(r"^(name|high_concept|notes|refresh_base|fate_points|skill_points_banked)$|"
                    r"^journey\.(\d)$|^skill\.([A-Za-z ]{1,30})$|^(stunts|resources)\.(\d{1,2})\.(name|text)$|"
                    r"^consequences\.(\d{1,2})\.text$")


def apply_field(d: dict, key: str, value: str) -> None:
    m = _FIELD.match(key)
    if not m:
        raise HTTPError(400, f"Unknown field {key!r}.")
    if m.group(1):
        k = m.group(1)
        if k in ("refresh_base", "fate_points", "skill_points_banked"):
            d[k] = _int(value, d[k], 0 if k != "refresh_base" else 1, 20)
        else:
            d[k] = _txt(value, 4000 if k == "notes" else 120)
    elif m.group(2):
        d["journey"][int(m.group(2))] = _txt(value, 120)
    elif m.group(3):
        skill = m.group(3)
        v = _int(value, 0, 0, 8)
        if v:
            d["skills"][skill] = v
        else:
            d["skills"].pop(skill, None)
    elif m.group(4):
        lst, i, part = d[m.group(4)], int(m.group(5)), m.group(6)
        if i >= len(lst):
            raise HTTPError(400, "That entry is gone.")
        lst[i][part] = _txt(value, 120 if part == "name" else 600)
    elif m.group(7):
        i = int(m.group(7))
        if i >= len(d["consequences"]):
            raise HTTPError(400, "That slot is gone.")
        d["consequences"][i]["text"] = _txt(value, 120)
        if not d["consequences"][i]["text"]:
            d["consequences"][i]["recovering"] = False


@app.post("/c/{cid}/ch/{chid}/field")
async def sheet_field(request: Request, cid: int, chid: int):
    ctx, ch = await char_ctx(request, cid, chid, edit=True)
    f = await form(request)
    d = ch["data"]
    for k, v in f.items():
        apply_field(d, k, v)
    await ctx.db.save_character(chid, d)
    return changed(ctx, "party", f"ch-{chid}")


@app.get("/c/{cid}/ch/{chid}/meta", response_class=HTMLResponse)
async def sheet_meta(request: Request, cid: int, chid: int):
    ctx, ch = await char_ctx(request, cid, chid)
    return page(request, "partials/sheet_meta.html", ctx, ch=ch, editable=ctx.can_edit(ch))


@app.post("/c/{cid}/ch/{chid}/op")
async def sheet_op(request: Request, cid: int, chid: int):
    ctx, ch = await char_ctx(request, cid, chid, edit=True)
    f = await form(request)
    d = ch["data"]
    op, i = f.get("op", ""), _int(f.get("i"), -1, -1, 99)
    topics = ["party", f"ch-{chid}"]
    if op in ("add_stunt", "add_resource"):
        d["stunts" if op == "add_stunt" else "resources"].append({"name": "", "text": ""})
    elif op in ("del_stunt", "del_resource"):
        lst = d["stunts" if op == "del_stunt" else "resources"]
        if 0 <= i < len(lst):
            lst.pop(i)
    elif op == "add_slot":
        sev = f.get("severity") if f.get("severity") in rules.CONSEQUENCES else "minor"
        d["consequences"].append({"severity": sev, "text": "", "recovering": False})
        d["consequences"].sort(key=lambda s: rules.CONSEQUENCE_ORDER.index(s["severity"]))
    elif op == "del_slot":
        if 0 <= i < len(d["consequences"]):
            d["consequences"].pop(i)
    elif op == "recover":
        if 0 <= i < len(d["consequences"]) and d["consequences"][i]["text"]:
            d["consequences"][i]["recovering"] = not d["consequences"][i]["recovering"]
    elif op == "clear":
        if 0 <= i < len(d["consequences"]):
            d["consequences"][i].update(text="", recovering=False)
    elif op == "fp":
        d["fate_points"] = max(0, min(20, d["fate_points"] + _int(f.get("delta"), 0, -1, 1)))
    elif op in ("take", "sacrifice"):
        sev = f.get("severity") if f.get("severity") in rules.CONSEQUENCES else "minor"
        text = _txt(f.get("text"), 120)
        if not text:
            raise HTTPError(400, "Name the consequence.")
        if op == "sacrifice":
            idx = next((k for k, s in enumerate(d["consequences"]) if s["severity"] == sev and not s["text"]), None)
            if idx is None:
                raise HTTPError(400, f"No open {sev} slot to sacrifice into.")
            gain = rules.CONSEQUENCES[sev]["sacrifice"]
            d["fate_points"] += gain
            msg = f"{d['name']} makes a sacrifice: {text} ({sev}), gaining {gain} fate point(s). The GM gets a free invoke."
        else:
            idx = rules.open_slot_for(d, sev)
            if idx is None:
                msg = f"{d['name']} would take {text} ({sev}) but has no open slot: overwhelmed!"
            else:
                msg = f"{d['name']} takes a consequence: {text} ({d['consequences'][idx]['severity']})."
        if idx is not None:
            d["consequences"][idx].update(text=text, recovering=False)
        await ctx.db.add_log(cid, ctx.email, "note", {"text": msg, "system": True})
        topics.append("log")
    elif op == "hide" and ch["kind"] == "npc":
        ctx.require_gm()
        d["hidden"] = not d.get("hidden")
    elif op == "delete":
        await ctx.db.delete_character(chid)
        ctx.hub.publish(cid, "party")
        return redirect(f"/c/{cid}/party")
    else:
        raise HTTPError(400, "Unknown sheet action.")
    await ctx.db.save_character(chid, d)
    return changed(ctx, *topics)


# =============================================================================================
# deductions
# =============================================================================================
@app.get("/c/{cid}/deduction", response_class=HTMLResponse)
async def deduction_page(request: Request, cid: int):
    ctx = await camp_ctx(request, cid)
    party = await _party(ctx)
    return page(request, "deduction.html", ctx, tab="deduction", ded=await ctx.db.open_deduction(cid),
                past=await ctx.db.past_deductions(cid), mine=_my_chars(ctx, party))


@app.get("/c/{cid}/deduction/frag", response_class=HTMLResponse)
async def deduction_frag(request: Request, cid: int):
    ctx = await camp_ctx(request, cid)
    party = await _party(ctx)
    return page(request, "partials/deduction_body.html", ctx, ded=await ctx.db.open_deduction(cid),
                past=await ctx.db.past_deductions(cid), mine=_my_chars(ctx, party))


@app.post("/c/{cid}/deduction/{op}")
async def deduction_op(request: Request, cid: int, op: str):
    ctx = await camp_ctx(request, cid)
    f = await form(request)
    ded = await ctx.db.open_deduction(cid)
    topics = ["deduction"]
    if op == "start":
        ctx.require_gm()
        if ded:
            raise HTTPError(400, "A deduction is already under way.")
        q = _txt(f.get("question"), 300)
        if not q:
            raise HTTPError(400, "Frame the question first.")
        await ctx.db.create_deduction(cid, {"question": q, "participants": [], "stage": "join", "round": 0,
                                            "opposition": rules.DEDUCTION_START_OPPOSITION, "progress": 0,
                                            "rolls": {}, "history": [], "facts": []})
        await ctx.db.add_log(cid, ctx.email, "note", {"text": f"Deduction framed: “{q}”", "system": True})
        return changed(ctx, "deduction", "log")
    if not ded:
        raise HTTPError(400, "No deduction is under way.")
    d = ded["data"]
    scene = ctx.camp["scene"]
    if op == "join":
        ch = await _roll_character(ctx, f.get("character_id"))
        if not ch or d["stage"] != "join":
            raise HTTPError(400, "Pick your character; joining is only open before the first round.")
        if any(p["char_id"] == ch["id"] for p in d["participants"]):
            raise HTTPError(400, "Already taking part.")
        d["participants"].append({"char_id": ch["id"], "name": ch["data"]["name"], "reason": _txt(f.get("reason"), 160),
                                  "owner": ch["owner_email"]})
    elif op == "begin":
        ctx.require_gm()
        if not d["participants"]:
            raise HTTPError(400, "Nobody has joined yet.")
        d.update(stage="round", round=1, rolls={})
    elif op == "roll":
        if d["stage"] not in ("round", "reveal"):
            raise HTTPError(400, "Not rolling right now.")
        ch = await _roll_character(ctx, f.get("character_id"))
        if not ch or not any(p["char_id"] == ch["id"] for p in d["participants"]):
            raise HTTPError(400, "That character isn't part of this deduction.")
        if str(ch["id"]) in d["rolls"]:
            raise HTTPError(400, "Already rolled this round.")
        skill = _txt(f.get("skill"), 40)
        dice = rules.roll_fate_dice()
        val = ch["data"]["skills"].get(skill, 0)
        d["rolls"][str(ch["id"])] = {"name": ch["data"]["name"], "skill": skill or "Mediocre", "value": val,
                                     "dice": dice, "total": sum(dice) + val}
    elif op == "boost":
        # Add +2 to a roll this round (invoke paid at the table / free invoke tracked on the scene board).
        key = str(_int(f.get("character_id"), 0, 0, 10**9))
        if key not in d["rolls"]:
            raise HTTPError(400, "No roll to improve.")
        ch = await _roll_character(ctx, key)
        if f.get("source") == "fp":
            cd = ch["data"]
            if cd["fate_points"] < 1:
                raise HTTPError(400, "No fate points left.")
            cd["fate_points"] -= 1
            await ctx.db.save_character(ch["id"], cd)
            topics += ["party", f"ch-{ch['id']}"]
        d["rolls"][key]["total"] += 2
        d["rolls"][key]["bonus"] = d["rolls"][key].get("bonus", 0) + 2
    elif op == "close":
        ctx.require_gm()
        results = [{"who": k, "total": v["total"]} for k, v in d["rolls"].items()]
        if d["stage"] == "round":
            res = rules.deduction_round(results, d["opposition"])
            d["progress"] += res["progress"]
            d["history"].append({"round": d["round"], "opposition": d["opposition"], "rolls": d["rolls"],
                                 "winners": res["winners"], "progress": res["progress"], "cost": res["cost"],
                                 "facts_due": res["winners"][:]})
            d["opposition"] = res["next_opposition"]
            d["rolls"] = {}
            if d["round"] < 3:
                d["round"] += 1
            else:
                d["stage"] = "reveal" if d["progress"] >= 3 else "failed"
                if d["stage"] == "failed":
                    _drop_facts(scene, d)
                    await ctx.db.save_scene(cid, scene)
                    await ctx.db.add_log(cid, ctx.email, "note", {"system": True, "text":
                                         f"Deduction unresolved ({d['progress']} progress). The facts stay true but "
                                         "are no longer aspects."})
                    topics += ["scene", "log"]
        elif d["stage"] == "reveal":
            if not results:
                raise HTTPError(400, "Everyone rolls once more first.")
            best = max(r["total"] for r in results)
            d["revealer"] = [r["who"] for r in results if r["total"] == best]
            d["reveal_rolls"] = d["rolls"]
            d["rolls"] = {}
            d["stage"] = "truth"
    elif op == "fact":
        text = _txt(f.get("text"), 120)
        who = str(_int(f.get("character_id"), 0, 0, 10**9))
        h = next((h for h in reversed(d["history"]) if who in h.get("facts_due", [])), None)
        if not text or not h:
            raise HTTPError(400, "Only a round's winner declares a fact.")
        await _roll_character(ctx, who)
        h["facts_due"].remove(who)
        aid = _next_id(scene)
        scene["aspects"].append({"id": aid, "text": text, "free": 0, "on": "", "tag": "fact", "by": ctx.user["name"]})
        d["facts"].append(aid)
        h.setdefault("facts", []).append(text)
        await ctx.db.save_scene(cid, scene)
        topics.append("scene")
    elif op == "truth":
        who = str(_int(f.get("character_id"), 0, 0, 10**9))
        text = _txt(f.get("text"), 160)
        if d["stage"] != "truth" or who not in d.get("revealer", []) or not text:
            raise HTTPError(400, "Only the reveal's winner declares the truth.")
        await _roll_character(ctx, who)
        _drop_facts(scene, d)
        free = rules.deduction_free_invokes(d["progress"]) or 0
        scene["aspects"].append({"id": _next_id(scene), "text": text, "free": free, "on": "", "tag": "truth",
                                 "by": ctx.user["name"]})
        d.update(stage="done", truth=text)
        await ctx.db.save_scene(cid, scene)
        await ctx.db.add_log(cid, ctx.email, "note", {"system": True, "text":
                             f"Deduction solved: “{d['question']}” → {text} ({free} free invoke(s))."})
        await ctx.db.save_deduction(ded["id"], d, is_open=False)
        return changed(ctx, "deduction", "scene", "log")
    elif op in ("cancel", "archive"):
        ctx.require_gm()
        if op == "cancel":
            _drop_facts(scene, d)
            await ctx.db.save_scene(cid, scene)
            topics.append("scene")
        d["stage"] = "cancelled" if op == "cancel" else d["stage"]
        await ctx.db.save_deduction(ded["id"], d, is_open=False)
        return changed(ctx, *topics)
    else:
        raise HTTPError(404, "Unknown deduction step.")
    await ctx.db.save_deduction(ded["id"], d)
    return changed(ctx, *topics)


def _drop_facts(scene: dict, d: dict) -> None:
    scene["aspects"] = [a for a in scene["aspects"] if a["id"] not in d["facts"]]


# =============================================================================================
# D'ni tools, timeline, rules, GM settings
# =============================================================================================
@app.get("/dni", response_class=HTMLResponse)
async def dni_page(request: Request):
    ctx = await user_ctx(request)
    return page(request, "dni.html", ctx, tab="dni", timeline=None)


@app.get("/c/{cid}/dni", response_class=HTMLResponse)
async def camp_dni(request: Request, cid: int):
    ctx = await camp_ctx(request, cid)
    return page(request, "dni.html", ctx, tab="dni", timeline=await _timeline(ctx))


async def _timeline(ctx: Ctx) -> list[dict]:
    rows = await ctx.db.timeline(ctx.cid, ctx.is_gm)
    for r in rows:
        try:
            r["dni"] = dni.to_dni(datetime.fromisoformat(r["greg"] + "T19:00:00+00:00"))
        except ValueError:
            r["dni"] = None
    return rows


@app.get("/c/{cid}/timeline/frag", response_class=HTMLResponse)
async def timeline_frag(request: Request, cid: int):
    ctx = await camp_ctx(request, cid)
    return page(request, "partials/timeline.html", ctx, timeline=await _timeline(ctx))


@app.post("/c/{cid}/timeline")
async def timeline_add(request: Request, cid: int):
    ctx = await camp_ctx(request, cid)
    ctx.require_gm()
    f = await form(request)
    greg = _txt(f.get("greg"), 10)
    try:
        datetime.fromisoformat(greg)
    except ValueError:
        raise HTTPError(400, "Use a date like 2003-01-15.")
    title = _txt(f.get("title"), 160)
    if not title:
        raise HTTPError(400, "Give the event a title.")
    await ctx.db.add_timeline(cid, greg, title, _txt(f.get("body"), 2000), bool(f.get("gm_only")))
    return changed(ctx, "timeline")


@app.post("/c/{cid}/timeline/{tid}/delete")
async def timeline_delete(request: Request, cid: int, tid: int):
    ctx = await camp_ctx(request, cid)
    ctx.require_gm()
    await ctx.db.delete_timeline(cid, tid)
    return changed(ctx, "timeline")


@app.get("/rules", response_class=HTMLResponse)
async def rules_page(request: Request):
    ctx = await user_ctx(request)
    return page(request, "rules.html", ctx, tab="rules")


@app.get("/c/{cid}/rules", response_class=HTMLResponse)
async def camp_rules(request: Request, cid: int):
    ctx = await camp_ctx(request, cid)
    return page(request, "rules.html", ctx, tab="rules")


@app.get("/c/{cid}/gm", response_class=HTMLResponse)
async def gm_page(request: Request, cid: int):
    ctx = await camp_ctx(request, cid)
    ctx.require_gm()
    base = str(request.base_url).rstrip("/")
    proto = request.headers.get("x-forwarded-proto")
    if proto == "https" and base.startswith("http://"):
        base = "https://" + base[len("http://"):]
    return page(request, "gm.html", ctx, tab="gm", members=await ctx.db.members(cid),
                invite_url=f"{base}/join/{ctx.camp['invite']}")


@app.post("/c/{cid}/gm/{op}")
async def gm_op(request: Request, cid: int, op: str):
    ctx = await camp_ctx(request, cid)
    ctx.require_gm()
    f = await form(request)
    if op == "rename":
        await ctx.db.rename_campaign(cid, _txt(f.get("name"), 80) or ctx.camp["name"])
    elif op == "invite":
        await ctx.db.new_invite(cid)
    elif op == "kick":
        await ctx.db.remove_member(cid, _txt(f.get("email"), 200).lower())
        ctx.hub.publish(cid, "party")
    elif op == "delete":
        if _txt(f.get("confirm"), 80) != ctx.camp["name"]:
            raise HTTPError(400, "Type the campaign's exact name to delete it.")
        await ctx.db.delete_campaign(cid)
        return redirect("/")
    else:
        raise HTTPError(404, "Unknown GM action.")
    return redirect(f"/c/{cid}/gm")
