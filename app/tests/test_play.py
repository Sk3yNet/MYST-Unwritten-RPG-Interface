import re

import pytest
from fastapi.testclient import TestClient

from unwritten import modules, rules, suggest

from .test_web import GM, P1, P2, get, h, post, setup_table


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.sqlite"))
    monkeypatch.delenv("DEV_USER", raising=False)
    from unwritten.main import app
    with TestClient(app) as c:
        yield c


def loaded(c):
    cid, chid = setup_table(c)
    post(c, f"/c/{cid}/ch/{chid}/field", P1, {"skill.Notice": "4", "skill.Research": "2", "high_concept": "Cartographer"})
    r = post(c, f"/c/{cid}/module", GM, {"slug": "flooded-archive"})
    assert r.headers["HX-Redirect"] == f"/c/{cid}/run"
    post(c, f"/c/{cid}/run/scene", GM, {"scene_id": "arrival"})
    return cid, chid


def test_bundled_module_is_valid():
    m = modules.get("flooded-archive")
    assert m and not m.data.get("error")
    assert set(m.maps) == {"archive", "seleshva"} and len(m.scenes) == 5
    for mp in m.maps.values():
        svg = m.file(mp["file"]).read_text()
        for aid in mp["areas"]:
            assert f'data-area="{aid}"' in svg, (mp["id"], aid)
    for s in m.scenes.values():
        for hid in s["handouts"]:
            assert hid in m.handouts


def test_player_map_never_contains_hidden_areas():
    m = modules.get("flooded-archive")
    svg = modules.render_map(m, "archive", {"landing"}, gm=False)
    assert "Flooded Landing" in svg
    for hidden in ("Reading Hall", "Pump Room", "Sealed Vault", "Linking Alcove", "Curator"):
        assert hidden not in svg
    assert 'data-hot="hall"' in svg and 'data-hot="vault"' not in svg  # frontier only
    assert "A wide, dark hall" in svg  # the teaser, not the name
    gm = modules.render_map(m, "archive", {"landing"}, gm=True)
    assert "Sealed Vault" in gm and 'data-hot="vault"' in gm


def test_frontier():
    m = modules.get("flooded-archive").maps["archive"]
    assert sorted(modules.frontier(m, {"landing"})) == ["hall", "pump"]
    assert "vault" in modules.frontier(m, {"landing", "hall", "study"})


def test_broken_module_is_reported(tmp_path, monkeypatch):
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "campaign.yaml").write_text("title: Bad\nmaps:\n  - {id: Bad Id, file: x.svg}\n")
    monkeypatch.setenv("CAMPAIGNS_DIR", str(tmp_path))
    assert "error" in modules.available()["bad"].data
    assert modules.get("bad") is None


def test_load_and_start_scene(client):
    cid, chid = loaded(client)
    scene = get(client, f"/c/{cid}/frag/scene", P1).text
    assert "Knee-Deep and Rising" in scene and "The Flooded Landing" in scene
    party = get(client, f"/c/{cid}/frag/party", GM).text
    assert "Ilse Varga" in party and "Ilse Varga" not in get(client, f"/c/{cid}/frag/party", P1).text
    assert get(client, f"/c/{cid}/run", P1).status_code == 403
    page = get(client, f"/c/{cid}/run", GM).text
    assert "Read aloud" in page and "Ilse" in page


def test_player_pages_hold_no_spoilers(client):
    cid, chid = loaded(client)
    me = get(client, f"/c/{cid}/me", P1).text
    mp = get(client, f"/c/{cid}/me/frag/map", P1).text
    sg = get(client, f"/c/{cid}/me/frag/suggest", P1).text
    blob = me + mp + sg
    for spoiler in ("6177", "Ilse's initials", "hand's width", "Pump Room", "Sealed Vault", "gm_notes",
                    "Teshan sealed"):
        assert spoiler not in blob, spoiler
    assert "Follow the rope" in sg  # the revealed area's hooks become suggestions
    assert get(client, f"/c/{cid}/me/area/archive/vault", P1).status_code == 404
    assert get(client, f"/c/{cid}/run/area/archive/vault", P1).status_code == 403
    assert get(client, f"/c/{cid}/media/m:journal", P1).status_code == 404


def test_inspect_request_roll_reveals(client, monkeypatch):
    cid, chid = loaded(client)
    assert post(client, f"/c/{cid}/map/request", P1, {"map": "archive", "area": "vault",
                                                      "character_id": chid}).status_code == 400
    assert post(client, f"/c/{cid}/map/request", P1, {"map": "archive", "area": "pump",
                                                      "character_id": chid}).status_code == 200
    assert post(client, f"/c/{cid}/map/request", P1, {"map": "archive", "area": "pump",
                                                      "character_id": chid}).status_code == 400  # already asked
    reqs = get(client, f"/c/{cid}/run/frag/requests", GM).text
    rid = int(re.search(r"/request/(\d+)", reqs).group(1))
    post(client, f"/c/{cid}/request/{rid}", GM, {"op": "roll"})
    sg = get(client, f"/c/{cid}/me/frag/suggest", P1).text
    assert "calls for a roll" in sg and 'name="request_id"' in sg
    monkeypatch.setattr(rules, "roll_fate_dice", lambda rng=None: [1, 0, 0, 0])
    post(client, f"/c/{cid}/roll", P1, {"character_id": chid, "skill": "Notice", "action": "discover",
                                        "opposition": "1", "request_id": rid})
    mp = get(client, f"/c/{cid}/me/frag/map", P1).text
    assert "Pump Room" in mp
    assert "discovered The Pump Room" in get(client, f"/c/{cid}/frag/log", P1).text


def test_failed_roll_leaves_fog_and_gm_reveal(client, monkeypatch):
    cid, chid = loaded(client)
    post(client, f"/c/{cid}/map/call", GM, {"map": "archive", "area": "hall", "difficulty": "4",
                                            "skills": "Notice", "action": "discover"})
    rid = int(re.search(r'name="request_id" value="(\d+)"', get(client, f"/c/{cid}/me/frag/suggest", P1).text).group(1))
    monkeypatch.setattr(rules, "roll_fate_dice", lambda rng=None: [-1, -1, 0, 0])
    post(client, f"/c/{cid}/roll", P1, {"character_id": chid, "skill": "Notice", "action": "discover",
                                        "opposition": "4", "request_id": rid})
    assert "Reading Hall" not in get(client, f"/c/{cid}/me/frag/map", P1).text
    assert "Reveal (at a cost)" in get(client, f"/c/{cid}/run/frag/requests", GM).text
    post(client, f"/c/{cid}/map/reveal", GM, {"map": "archive", "area": "hall"})
    assert "Reading Hall" in get(client, f"/c/{cid}/me/frag/map", P1).text
    assert post(client, f"/c/{cid}/map/reveal", P1, {"map": "archive", "area": "stacks"}).status_code == 403


def test_handout_push_and_access(client):
    cid, chid = loaded(client)
    token = re.search(r"/join/([\w-]+)", get(client, f"/c/{cid}/gm", GM).text).group(1)
    post(client, f"/join/{token}", P2)
    post(client, f"/c/{cid}/handout/push", GM, {"key": "m:journal", "to": P1, "effect": "reveal"})
    ov = get(client, f"/c/{cid}/handout/current", P1).text
    assert "fx-reveal" in ov and "Teshan" in ov
    assert get(client, f"/c/{cid}/handout/current", P2).text == ""
    assert get(client, f"/c/{cid}/media/m:journal", P1).status_code == 200
    assert get(client, f"/c/{cid}/media/m:journal", P2).status_code == 404
    assert "Teshan" in get(client, f"/c/{cid}/handouts", P1).text
    post(client, f"/c/{cid}/handout/clear", GM)
    assert get(client, f"/c/{cid}/handout/current", P1).text == ""


def test_upload_handout(client):
    cid, _ = loaded(client)
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
    r = client.post(f"/c/{cid}/handout/upload", headers=h(GM), files={"file": ("door.png", png, "image/png")},
                    data={"caption": "The door"})
    assert r.status_code == 200
    bad = client.post(f"/c/{cid}/handout/upload", headers=h(GM), files={"file": ("x.svg", b"<svg/>", "image/svg+xml")})
    assert bad.status_code == 400
    assert client.post(f"/c/{cid}/handout/upload", headers=h(P1),
                       files={"file": ("door.png", png, "image/png")}).status_code == 403
    key = re.search(r'name="key" value="(u:[0-9a-f]+)"', get(client, f"/c/{cid}/run/frag/handouts", GM).text).group(1)
    assert get(client, f"/c/{cid}/media/{key}", P1).status_code == 404
    post(client, f"/c/{cid}/handout/push", GM, {"key": key})
    r = get(client, f"/c/{cid}/media/{key}", P1)
    assert r.status_code == 200 and r.content == png and r.headers["content-type"] == "image/png"


def test_suggestions_rules():
    ch = {"id": 1, "data": rules.normalize_character({**rules.blank_character("A"), "skills": {"Notice": 4},
                                                     "high_concept": "Cartographer", "fate_points": 0})}
    ch["data"]["consequences"][0]["text"] = "Twisted Ankle"
    scene = {"aspects": [{"text": "Slick", "free": 1}]}
    area = {"hooks": [{"text": "Look up", "skill": "Notice", "action": "discover"}]}
    out = suggest.for_player(ch, scene, area, ["A dark stair"])
    kinds = [o["kind"] for o in out]
    assert kinds[:4] == ["area", "invoke", "explore", "heal"] and "fp" in kinds
    assert any("out of fate points" in o["title"] for o in out)
    assert suggest.compel_ideas([ch]) == [{"who": "A", "char_id": 1, "aspect": "Cartographer"}]


def test_guide_and_pages_render(client):
    cid, chid = loaded(client)
    for url, who in [("/guide", P1), (f"/c/{cid}/guide", GM), (f"/c/{cid}/me", GM), (f"/c/{cid}/run?map=seleshva", GM),
                     (f"/c/{cid}/run/area/archive/vault", GM), (f"/c/{cid}/run/frag/compels", GM),
                     (f"/c/{cid}/gm", GM), (f"/c/{cid}/handouts", P1)]:
        assert get(client, url, who).status_code == 200, url


def test_gm_map_before_any_scene_and_bad_map_param(client):
    cid, _ = setup_table(client)
    post(client, f"/c/{cid}/module", GM, {"slug": "flooded-archive"})
    for url in (f"/c/{cid}/run/frag/map", f"/c/{cid}/run/frag/map?map=None", f"/c/{cid}/run?map=nope"):
        assert 'data-hot="vault"' in get(client, url, GM).text, url
    assert 'data-map="seleshva"' in get(client, f"/c/{cid}/run/frag/map?map=seleshva", GM).text
