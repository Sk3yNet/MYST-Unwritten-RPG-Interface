from datetime import datetime, timezone

import pytest

from unwritten import dni


def test_base25_examples():
    assert dni.to_base25(326) == [13, 1] and dni.to_font(326) == "#1"
    assert dni.to_font(708) == "138"
    assert dni.to_base25(10544) == [16, 21, 19]
    assert dni.from_font("%4") == 379 and dni.from_font("6%") == 165 and dni.from_font("52") == 127
    assert dni.to_font(25) == "10" and dni.to_font(0) == "0"
    for n in (0, 1, 24, 25, 624, 625, 99999):
        assert dni.from_base25(dni.to_base25(n)) == n


def test_epoch_is_leefo_one():
    d = dni.to_dni(dni.EPOCH)
    assert (d["hahr"], d["vailee"], d["yahr"], d["bell"]) == (9654, 1, 1, 1)


@pytest.mark.parametrize("greg,expected", [
    ("2002-07-20", (9658, 3, 14)), ("1997-10-31", (9653, 6, 9)), ("1995-11-02", (9651, 6, 10)),
    ("2002-03-21", (9657, 10, 5)), ("2002-09-06", (9658, 4, 24)), ("2003-01-15", (9658, 8, 12)),
])
def test_matches_published_dates_within_a_yahr(greg, expected):
    d = dni.to_dni(datetime.fromisoformat(greg + "T12:00:00-07:00"))
    assert (d["hahr"], d["vailee"]) == expected[:2]
    assert abs(d["yahr"] - expected[2]) <= 1


def test_round_trip():
    t = datetime(2026, 10, 18, 20, 30, tzinfo=timezone.utc)
    d = dni.to_dni(t)
    back = dni.from_dni(d["hahr"], d["vailee"], d["yahr"], d["gahrtahvo"], d["pahrtahvo"], d["tahvo"],
                        d["gorahn"], d["prorahn"])
    assert abs((back - t).total_seconds()) < 2


def test_transcribe():
    assert dni.transcribe("shorah b'shehm") == "Sora b'Sem"
    assert dni.transcribe("kehshtahv") == "KeStav"
    assert dni.transcribe("tahgehmah b’zoo") == "tagema b'zU"
