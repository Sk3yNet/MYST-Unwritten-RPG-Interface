import json
import re

import pytest
from fastapi.testclient import TestClient

GM = "gm@example.com"
P1 = "rosa@example.com"
P2 = "stranger@example.com"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.sqlite"))
    monkeypatch.delenv("DEV_USER", raising=False)
    from unwritten.main import app
    with TestClient(app) as c:
        yield c


def h(email, hx=True):
    out = {"X-Auth-Request-Email": email}
    if hx:
        out["HX-Request"] = "true"
    return out


def post(c, url, who, data=None):
    return c.post(url, data=data or {}, headers=h(who))


def get(c, url, who):
    return c.get(url, headers=h(who, hx=False))


def setup_table(c):
    r = post(c, "/campaigns", GM, {"name": "The Flooded Archive"})
    cid = int(r.headers["HX-Redirect"].rsplit("/", 1)[1])
    page = get(c, f"/c/{cid}/gm", GM).text
    token = re.search(r"/join/([\w-]+)", page).group(1)
    assert post(c, f"/join/{token}", P1).headers["HX-Redirect"] == f"/c/{cid}/lobby"
    r = post(c, f"/c/{cid}/characters", P1, {"name": "Rosa", "kind": "pc"})
    chid = int(r.headers["HX-Redirect"].rsplit("/", 1)[1])
    return cid, chid


def test_requires_identity_and_hx_header(client):
    assert client.get("/").status_code == 401
    assert client.post("/campaigns", data={"name": "x"}, headers={"X-Auth-Request-Email": GM}).status_code == 403
    assert get(client, "/", GM).status_code == 200


def test_invite_flow_and_privacy(client):
    cid, chid = setup_table(client)
    assert get(client, f"/c/{cid}", P1).status_code == 200
    assert get(client, f"/c/{cid}", P2).status_code == 404
    assert get(client, f"/c/{cid}/ch/{chid}", P2).status_code == 404
    assert get(client, f"/c/{cid}/gm", P1).status_code == 403
    # A fresh invite link retires the old one.
    old = re.search(r"/join/([\w-]+)", get(client, f"/c/{cid}/gm", GM).text).group(1)
    post(client, f"/c/{cid}/gm/invite", GM)
    assert get(client, f"/join/{old}", P2).status_code == 404


def test_sheet_editing_and_permissions(client):
    cid, chid = setup_table(client)
    r = post(client, f"/c/{cid}/ch/{chid}/field", P1, {"high_concept": "Cartographer", "skill.Will": "4",
                                                      "journey.0": "Reads Old D'ni"})
    assert r.status_code == 200 and "ch-%d" % chid in r.headers["HX-Trigger"]
    data = get(client, f"/c/{cid}/ch/{chid}/export", P1).json()
    assert data["high_concept"] == "Cartographer" and data["skills"] == {"Will": 4}
    assert post(client, f"/c/{cid}/ch/{chid}/field", P1, {"bogus": "1"}).status_code == 400
    # The GM can edit; a second player can't.
    post(client, f"/c/{cid}/ch/{chid}/field", GM, {"skill.Will": "0"})
    assert get(client, f"/c/{cid}/ch/{chid}/export", GM).json()["skills"] == {}
    page = get(client, f"/c/{cid}/gm", GM).text
    token = re.search(r"/join/([\w-]+)", page).group(1)
    post(client, f"/join/{token}", P2)
    assert post(client, f"/c/{cid}/ch/{chid}/field", P2, {"name": "Hijacked"}).status_code == 403
    # Stunts beyond three cost refresh.
    for _ in range(4):
        post(client, f"/c/{cid}/ch/{chid}/op", P1, {"op": "add_stunt"})
    assert "refresh <strong>2</strong>" in get(client, f"/c/{cid}/ch/{chid}/meta", P1).text


def test_roll_invoke_and_fate_points(client):
    cid, chid = setup_table(client)
    post(client, f"/c/{cid}/ch/{chid}/field", P1, {"skill.Research": "4", "high_concept": "Cartographer"})
    r = post(client, f"/c/{cid}/roll", P1, {"character_id": chid, "skill": "Research", "action": "discover",
                                            "opposition": "2", "intent": "Read the ledgers"})
    assert r.status_code == 200
    log = get(client, f"/c/{cid}/frag/log", P1).text
    assert "Read the ledgers" in log and "Discover" in log
    lid = int(re.search(r"/log/(\d+)/invoke", log).group(1))
    assert post(client, f"/c/{cid}/log/{lid}/invoke", P1, {"source": "fp", "effect": "plus2",
                                                          "aspect": "Cartographer"}).status_code == 200
    assert get(client, f"/c/{cid}/ch/{chid}/export", P1).json()["fate_points"] == 2
    # Same aspect twice with fate points on one roll is not allowed.
    assert post(client, f"/c/{cid}/log/{lid}/invoke", P1, {"source": "fp", "aspect": "Cartographer"}).status_code == 400
    # Free invoke from the scene board.
    post(client, f"/c/{cid}/scene/aspect", P1, {"text": "Slick with Lake Spray", "free": "1"})
    post(client, f"/c/{cid}/log/{lid}/invoke", P1, {"source": "free:1", "effect": "reroll"})
    assert "pip on" not in get(client, f"/c/{cid}/frag/scene", P1).text
    assert post(client, f"/c/{cid}/log/{lid}/invoke", P1, {"source": "free:1"}).status_code == 400
    # Players can't roll for nobody; only the GM rolls custom.
    assert post(client, f"/c/{cid}/roll", P1, {"skill_value": "5"}).status_code == 400
    assert post(client, f"/c/{cid}/roll", GM, {"who": "Curator", "skill": "Provoke", "skill_value": "4"}).status_code == 200


def test_compel_accept_and_refuse(client):
    cid, chid = setup_table(client)
    post(client, f"/c/{cid}/compel", GM, {"character_id": chid, "aspect": "Cartographer", "text": "The door hums"})
    lid = int(re.search(r"/log/(\d+)/compel", get(client, f"/c/{cid}/frag/log", P1).text).group(1))
    assert post(client, f"/c/{cid}/log/{lid}/compel", P1, {"op": "accept"}).status_code == 200
    assert get(client, f"/c/{cid}/ch/{chid}/export", P1).json()["fate_points"] == 4
    assert post(client, f"/c/{cid}/log/{lid}/compel", P1, {"op": "refuse"}).status_code == 400


def test_consequences_sacrifice_and_overwhelm(client):
    cid, chid = setup_table(client)
    url = f"/c/{cid}/ch/{chid}/op"
    post(client, url, P1, {"op": "sacrifice", "severity": "moderate", "text": "Twisted Ankle"})
    d = get(client, f"/c/{cid}/ch/{chid}/export", P1).json()
    assert d["fate_points"] == 5 and d["consequences"][1]["text"] == "Twisted Ankle"
    assert post(client, url, P1, {"op": "sacrifice", "severity": "moderate", "text": "Again"}).status_code == 400
    post(client, url, P1, {"op": "take", "severity": "minor", "text": "Winded"})
    post(client, url, P1, {"op": "take", "severity": "minor", "text": "Bruised"})  # rolls up to severe
    post(client, url, P1, {"op": "take", "severity": "minor", "text": "Dizzy"})
    assert "overwhelmed" in get(client, f"/c/{cid}/frag/log", P1).text
    post(client, url, P1, {"op": "recover", "i": "0"})
    post(client, f"/c/{cid}/scene/end", GM)
    d = get(client, f"/c/{cid}/ch/{chid}/export", P1).json()
    assert d["consequences"][0]["text"] == "" and d["consequences"][2]["text"] == "Bruised"


def test_npcs_hidden_from_players(client):
    cid, _ = setup_table(client)
    r = post(client, f"/c/{cid}/characters", GM, {"name": "The Curator", "kind": "npc"})
    npc = int(r.headers["HX-Redirect"].rsplit("/", 1)[1])
    assert "Curator" not in get(client, f"/c/{cid}/frag/party", P1).text
    assert get(client, f"/c/{cid}/ch/{npc}", P1).status_code == 404
    assert post(client, f"/c/{cid}/characters", P1, {"name": "Sneaky", "kind": "npc"}).status_code == 403
    post(client, f"/c/{cid}/ch/{npc}/op", GM, {"op": "hide"})
    assert get(client, f"/c/{cid}/ch/{npc}", P1).status_code == 200


def test_deduction_full_run(client, monkeypatch):
    from unwritten import rules
    cid, chid = setup_table(client)
    post(client, f"/c/{cid}/ch/{chid}/field", P1, {"skill.Research": "5"})
    base = f"/c/{cid}/deduction"
    assert post(client, f"{base}/start", P1, {"question": "x"}).status_code == 403
    post(client, f"{base}/start", GM, {"question": "Who sealed the library?"})
    post(client, f"{base}/join", P1, {"character_id": chid, "reason": "Reads Old D'ni"})
    post(client, f"{base}/begin", GM)
    monkeypatch.setattr(rules, "roll_fate_dice", lambda rng=None: [1, 1, 0, 0])  # always +2
    for rnd in range(3):
        assert post(client, f"{base}/roll", P1, {"character_id": chid, "skill": "Research"}).status_code == 200
        post(client, f"{base}/close", GM)
        assert post(client, f"{base}/fact", P1, {"character_id": chid, "text": f"Fact {rnd}"}).status_code == 200
    # Round 1: 7 vs 3 -> +2; rounds 2 and 3: 7 vs 7 -> tie, +1 each = 4 progress.
    post(client, f"{base}/roll", P1, {"character_id": chid, "skill": "Research"})
    post(client, f"{base}/close", GM)
    assert post(client, f"{base}/truth", P1, {"character_id": chid, "text": "A Forbidden Book"}).status_code == 200
    scene = get(client, f"/c/{cid}/frag/scene", P1).text
    assert "A Forbidden Book" in scene and "Fact 0" not in scene and scene.count("pip on") == 1


def test_timeline_and_pages(client):
    cid, chid = setup_table(client)
    post(client, f"/c/{cid}/timeline", GM, {"greg": "2002-07-20", "title": "First link", "gm_only": "1"})
    assert "Leesahn" in get(client, f"/c/{cid}/timeline/frag", GM).text
    assert "First link" not in get(client, f"/c/{cid}/timeline/frag", P1).text
    for url in ("/rules", "/dni", f"/c/{cid}/rules", f"/c/{cid}/dni", f"/c/{cid}/party", f"/c/{cid}/deduction",
                f"/c/{cid}/frag/roller", f"/c/{cid}/ch/{chid}", f"/c/{cid}/ch/{chid}/frag", "/static/fonts/DniFont.ttf",
                "/healthz"):
        assert get(client, url, P1).status_code == 200, url


def test_allowed_emails_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "g.sqlite"))
    monkeypatch.setenv("ALLOWED_EMAILS", GM)
    monkeypatch.setenv("GM_EMAILS", GM)
    from unwritten.main import app
    with TestClient(app) as c:
        assert get(c, "/", P2).status_code == 403
        assert get(c, "/", GM).status_code == 200


def test_concurrent_scene_edits_are_not_lost(tmp_path, monkeypatch):
    import asyncio
    import httpx
    monkeypatch.setenv("DB_PATH", str(tmp_path / "c.sqlite"))
    from unwritten.main import app

    async def run():
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
                r = await c.post("/campaigns", data={"name": "x"}, headers=h(GM))
                cid = r.headers["HX-Redirect"].rsplit("/", 1)[1]
                await asyncio.gather(*[c.post(f"/c/{cid}/scene/aspect", data={"text": f"A{i}"}, headers=h(GM))
                                       for i in range(20)])
                page = (await c.get(f"/c/{cid}/frag/scene", headers=h(GM, hx=False))).text
                return sum(f"A{i}<" in page or f"A{i}\n" in page or f">A{i}" in page for i in range(20))

    assert asyncio.run(run()) == 20
