import re

import pytest
from fastapi.testclient import TestClient

import unwritten.main  # noqa: F401  (the app module registers the routers; load it first, as uvicorn does)
from unwritten import lobby, modules

from .test_web import GM, P1, P2, get, post, setup_table


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.sqlite"))
    monkeypatch.delenv("DEV_USER", raising=False)
    from unwritten.main import app
    with TestClient(app) as c:
        yield c


def test_shelf_is_stable_and_holds_every_playable_book():
    mods = [m for m in modules.available().values() if not m.data.get("error")]
    a, b = lobby.build_shelf(7, mods), lobby.build_shelf(7, mods)
    assert a == b
    live = [x for row in a for x in row if x["kind"] == "live"]
    assert sorted(x["slug"] for x in live) == sorted(m.slug for m in mods)
    assert sum(len(r) for r in a) == lobby.SHELVES * lobby.BOOKS_PER_SHELF
    assert lobby.build_shelf(8, mods) != a


def test_lobby_page_and_ready(client):
    cid, _ = setup_table(client)
    page = get(client, f"/c/{cid}/lobby", P1).text
    assert page.count('class="bk live"') == len([m for m in modules.available().values() if not m.data.get("error")])
    assert "The Concordance" in page and "Vol. II" in page and 'class="bk burned' in page
    assert get(client, f"/c/{cid}/lobby", P2).status_code == 404
    r = post(client, f"/c/{cid}/lobby/ready", P1)
    assert "lobby" in r.headers["HX-Trigger"]
    people = get(client, f"/c/{cid}/lobby/people", P1).text
    assert 'data-ready="1"' in people and "Snuff my candle" in people
    post(client, f"/c/{cid}/lobby/ready", P1)
    assert 'data-ready="0"' in get(client, f"/c/{cid}/lobby/people", P1).text


def test_launch(client):
    cid, _ = setup_table(client)
    post(client, f"/c/{cid}/lobby/ready", P1)
    assert get(client, f"/c/{cid}/lobby/launch", P1).text == ""
    assert post(client, f"/c/{cid}/lobby/launch", P1, {"slug": "concordance"}).status_code == 403
    assert post(client, f"/c/{cid}/lobby/launch", GM, {"slug": "nope"}).status_code == 400
    r = post(client, f"/c/{cid}/lobby/launch", GM, {"slug": "concordance"})
    assert "launch" in r.headers["HX-Trigger"]
    info_p = get(client, f"/c/{cid}/lobby/launch", P1).text
    info_g = get(client, f"/c/{cid}/lobby/launch", GM).text
    assert f'data-dest="/c/{cid}/me"' in info_p and f'data-dest="/c/{cid}/run"' in info_g
    assert 'data-seq="1"' in info_p and "/book/concordance/preview" in info_p
    assert 'data-ready="1"' in get(client, f"/c/{cid}/lobby/people", P1).text  # candles stay lit through the launch
    assert post(client, f"/c/{cid}/lobby/snuff", P1).status_code == 403
    post(client, f"/c/{cid}/lobby/snuff", GM)
    assert 'data-ready="0"' in get(client, f"/c/{cid}/lobby/people", P1).text
    assert "Concordance" in get(client, f"/c/{cid}/run", GM).text
    # Opening the same Book again keeps progress; the page remembers the last launch so it isn't replayed.
    post(client, f"/c/{cid}/map/reveal", GM, {"map": "sanctuary", "area": "library"})
    post(client, f"/c/{cid}/lobby/launch", GM, {"slug": "concordance"})
    st = get(client, f"/c/{cid}/run/frag/map?map=sanctuary", GM).text
    assert 'class="hot revealed" data-hot="library"' in st
    assert 'data-seen-seq="2"' in get(client, f"/c/{cid}/lobby", P1).text


def test_book_images(client):
    cid, _ = setup_table(client)
    r = get(client, f"/c/{cid}/book/concordance/cover", P1)
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg")
    assert get(client, f"/c/{cid}/book/concordance/preview", P1).status_code == 200
    assert get(client, f"/c/{cid}/book/concordance/cover", P2).status_code == 404
    assert get(client, f"/c/{cid}/book/concordance/secret", P1).status_code == 404
