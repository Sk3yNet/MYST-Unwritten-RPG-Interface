from unwritten import rules


def test_outcomes():
    assert [rules.outcome_for(s) for s in (-1, 0, 1, 2, 3, 7)] == ["fumble", "tie", "succeed", "succeed", "excel", "excel"]


def test_ladder_labels():
    assert rules.ladder(3) == "Good (+3)"
    assert rules.ladder(-1) == "Poor (-1)"
    assert rules.ladder(10).startswith("Beyond")


def test_roll_totals_and_modifiers():
    r = rules.Roll(action="discover", skill="Research", skill_value=4, dice=[1, 1, 0, 0], opposition=2)
    assert r.total == 6 and r.shifts == 4 and r.outcome == "excel"
    assert r.summary()["questions"] == 4
    r.modifiers.append(rules.Modifier("invoke", "Cartographer of Forgotten Ages"))
    assert r.total == 8
    again = rules.Roll.from_dict(r.to_dict())
    assert again.total == 8 and again.modifiers[0].label == "Cartographer of Forgotten Ages"


def test_no_opposition_still_totals():
    r = rules.Roll(action="overcome", skill="Athletics", skill_value=3, dice=[-1, -1, 0, 0])
    assert r.shifts == 1 and r.summary()["has_opposition"] is False


def test_dangerous_fumble_mentions_overwhelmed():
    r = rules.Roll(action="overcome", skill="Athletics", skill_value=0, dice=[-1, -1, -1, -1], opposition=2,
                   dangerous=True)
    assert "overwhelmed" in r.summary()["lines"][0]


def test_dice_are_drama_dice():
    for _ in range(200):
        d = rules.roll_drama_dice()
        assert len(d) == 4 and set(d) <= {-1, 0, 1}


def test_refresh_and_stunts():
    c = rules.blank_character("Rosa")
    assert rules.refresh(c) == 3
    c["stunts"] = [{"name": "a", "text": ""}] * 3
    c["resources"] = [{"name": "The Workshop", "text": ""}]
    assert rules.refresh(c) == 2
    c["stunts"] = [{"name": "a", "text": ""}] * 6
    assert rules.refresh(c) == -1
    assert any(x["level"] == "warn" and "Refresh" in x["text"] for x in rules.check_character(c))


def test_pyramid_and_columns():
    c = rules.blank_character()
    c["skills"] = {"Rapport": 4, "Notice": 3, "Experiment": 3, "Will": 2, "Craft": 2, "Empathy": 2,
                   "Medicine": 1, "Athletics": 1, "Finesse": 1, "Deceive": 1}
    checks = rules.check_character(c)
    assert any(x["level"] == "ok" for x in checks)
    assert not any(x["level"] == "warn" for x in checks)
    c["skills"] = {"Survival": 3, "Notice": 3, "Will": 2, "Research": 1, "Craft": 1, "Stealth": 1}
    assert any("Skill columns" in x["text"] for x in rules.check_character(c))


def test_consequence_roll_up_and_overwhelm():
    c = rules.blank_character()
    assert rules.open_slot_for(c, "minor") == 0
    c["consequences"][0]["text"] = "Winded"
    assert rules.open_slot_for(c, "minor") == 1
    c["consequences"][1]["text"] = "Exhausted"
    c["consequences"][2]["text"] = "Compound Fracture"
    assert rules.open_slot_for(c, "minor") is None
    assert rules.recovery_difficulty("moderate") == 4 and rules.recovery_difficulty("moderate", True) == 5


def test_session_and_chapter():
    c = rules.blank_character()
    c["drama_points"] = 5
    c["consequences"][0].update(text="Winded", recovering=True)
    c["consequences"][2].update(text="Trauma", recovering=True)
    rules.start_session(c)
    assert c["drama_points"] == 5 and c["consequences"][0]["text"] == "" and c["consequences"][2]["text"] == "Trauma"
    c["drama_points"] = 0
    rules.start_session(c)
    assert c["drama_points"] == 3
    c["drama_points"] = 6
    rules.start_chapter(c)
    assert c["drama_points"] == 3 and c["consequences"][2]["text"] == ""


def test_end_scene_heals_recovering_minor_only():
    c = rules.blank_character()
    c["consequences"][0].update(text="Wrapped Up Ankle", recovering=True)
    c["consequences"][1].update(text="Deep Cut", recovering=True)
    rules.end_scene(c)
    assert c["consequences"][0]["text"] == "" and c["consequences"][1]["text"] == "Deep Cut"


def test_deduction_rounds():
    # Great (+4) vs Good (+3) -> succeed, 1 progress, next opposition +4.
    r = rules.deduction_round([{"who": "N", "total": 3}, {"who": "T", "total": 4}, {"who": "S", "total": 1}], 3)
    assert r == {"winners": ["T"], "progress": 1, "cost": False, "next_opposition": 4}
    tie = rules.deduction_round([{"who": "S", "total": 4}], 4)
    assert tie["progress"] == 1 and tie["cost"] is True
    assert rules.deduction_round([{"who": "S", "total": 7}], 4)["progress"] == 2
    none = rules.deduction_round([{"who": "S", "total": 2}], 3)
    assert none["winners"] == [] and none["next_opposition"] == 3
    assert [rules.deduction_free_invokes(p) for p in (2, 3, 4, 5, 6)] == [None, 0, 1, 1, 2]


def test_old_records_keep_their_points():
    c = rules.normalize_character({"name": "Old", "fate_points": 5})
    assert c["drama_points"] == 5 and "fate_points" not in c
