"""Unwritten game mechanics (drama dice, aspects, drama points), written in our own words.

Everything here is pure: no I/O, so it is easy to test and reuse from the web layer.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

LADDER = {
    8: "Legendary", 7: "Epic", 6: "Fantastic", 5: "Superb", 4: "Great", 3: "Good",
    2: "Fair", 1: "Adequate", 0: "Mediocre", -1: "Poor", -2: "Terrible",
}

SKILLS = [
    "Athletics", "Craft", "Deceive", "Empathy", "Engineering", "Experiment", "Finesse", "Intrusion", "Medicine",
    "Notice", "Provoke", "Rapport", "Research", "Stealth", "Surveying", "Survival", "Will",
]

# Starting skill pyramid: rating -> number of skills.
PYRAMID = {4: 1, 3: 2, 2: 3, 1: 4}
BASE_REFRESH = 3
FREE_STUNTS = 3
MAX_EXTRA_STUNTS_AT_CREATION = 2
JOURNEY_ASPECTS = 4

# Consequence severity -> (shift value, recovery difficulty, drama points from a sacrifice).
CONSEQUENCES = {
    "minor": {"label": "Minor", "shifts": 2, "recover": 2, "sacrifice": 1},
    "moderate": {"label": "Moderate", "shifts": 4, "recover": 4, "sacrifice": 2},
    "severe": {"label": "Severe", "shifts": 6, "recover": 6, "sacrifice": 3},
}
CONSEQUENCE_ORDER = ["minor", "moderate", "severe"]

ACTIONS = {
    "overcome": "Overcome",
    "create": "Advantage (create)",
    "take": "Advantage (take)",
    "discover": "Discover",
    "oppose": "Oppose",
}

OUTCOMES = ("fumble", "tie", "succeed", "excel")


def ladder(value: int) -> str:
    """'Good (+3)' style label; values off the ladder still get a sign."""
    sign = f"+{value}" if value >= 0 else str(value)
    if value > 8:
        return f"Beyond Legendary ({sign})"
    if value < -2:
        return f"Abysmal ({sign})"
    return f"{LADDER[value]} ({sign})"


def roll_drama_dice(rng: random.Random | None = None) -> list[int]:
    r = rng or random.SystemRandom()
    return [r.choice((-1, 0, 1)) for _ in range(4)]


def dice_faces(dice: list[int]) -> str:
    return " ".join({-1: "−", 0: "0", 1: "+"}[d] for d in dice)


def outcome_for(shifts: int) -> str:
    if shifts < 0:
        return "fumble"
    if shifts == 0:
        return "tie"
    if shifts <= 2:
        return "succeed"
    return "excel"


# What each outcome lets you do, per action. Paraphrased summaries for the table, not book text.
OUTCOME_TEXT = {
    "overcome": {
        "fumble": ["You don't get past it.", "Or: succeed at a serious cost."],
        "tie": ["You don't get past it.", "Or: succeed at a minor cost."],
        "succeed": ["You get past the obstacle."],
        "excel": ["You get past it with flair, and gain a boost."],
    },
    "create": {
        "fumble": ["No advantage, or an aspect you didn't want.", "Or: succeed at a serious cost.",
                   "The GM may hand a free invoke to someone who benefits."],
        "tie": ["Only a fleeting edge: gain a boost."],
        "succeed": ["Place a situation aspect with 1 free invoke."],
        "excel": ["Place a situation aspect with 2 free invokes.",
                  "On a character, you may spend one to give them a minor consequence instead."],
    },
    "take": {
        "fumble": ["You can't make use of it; the GM may hand a free invoke to someone else.",
                   "Or: succeed at a serious cost and gain 1 free invoke."],
        "tie": ["Gain 1 free invoke on the aspect."],
        "succeed": ["Gain 1 free invoke on the aspect."],
        "excel": ["Gain 2 free invokes on the aspect."],
    },
    "discover": {
        "fumble": ["Nothing useful turns up.", "Or: serious cost (you damage something) and ask 1 question."],
        "tie": ["Nothing useful turns up.", "Or: minor cost and ask 1 question."],
        "succeed": ["Ask one question per shift."],
        "excel": ["Ask one question per shift, and you may ask the GM for an important hint.",
                  "Don't use the hint this scene and you gain a drama point instead."],
    },
    "oppose": {
        "fumble": ["The actor gets through you."],
        "tie": ["The actor ties."],
        "succeed": ["You stop the actor."],
        "excel": ["You turn the tables for a moment: gain a boost."],
    },
}

DANGEROUS_TEXT = "Dangerous action: fumbling means you are overwhelmed and out of the scene."

MINOR_COSTS = ["A new wrinkle that complicates things a little", "A tough choice attached to the success",
               "An NPC gains a boost", "A situation aspect lands on the character"]
SERIOUS_COSTS = ["A new wrinkle that complicates things a lot", "Reinforce or add opposition",
                 "A minor consequence (or the lowest open slot)", "An opponent gains an advantage with a free invoke",
                 "Success takes much longer than expected"]


def questions_for(action: str, shifts: int) -> int:
    """Discover questions earned on a full success (fumble/tie at a cost give 1, chosen by the player)."""
    if action != "discover" or shifts <= 0:
        return 0
    return shifts


@dataclass
class Modifier:
    kind: str          # "invoke" (drama point), "free" (free invoke), "boost", "reroll"
    label: str
    value: int = 2


@dataclass
class Roll:
    action: str
    skill: str
    skill_value: int
    dice: list[int]
    opposition: int | None = None
    stunt_bonus: int = 0
    teamwork: int = 0
    dangerous: bool = False
    modifiers: list[Modifier] = field(default_factory=list)

    @property
    def dice_total(self) -> int:
        return sum(self.dice)

    @property
    def bonus(self) -> int:
        return sum(m.value for m in self.modifiers if m.kind != "reroll")

    @property
    def total(self) -> int:
        return self.dice_total + self.skill_value + self.stunt_bonus + self.teamwork + self.bonus

    @property
    def shifts(self) -> int:
        return self.total - (self.opposition or 0)

    @property
    def outcome(self) -> str:
        return outcome_for(self.shifts)

    def to_dict(self) -> dict:
        return {
            "action": self.action, "skill": self.skill, "skill_value": self.skill_value, "dice": self.dice,
            "opposition": self.opposition, "stunt_bonus": self.stunt_bonus, "teamwork": self.teamwork,
            "dangerous": self.dangerous,
            "modifiers": [{"kind": m.kind, "label": m.label, "value": m.value} for m in self.modifiers],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Roll":
        mods = [Modifier(**m) for m in d.get("modifiers", [])]
        return cls(action=d["action"], skill=d["skill"], skill_value=d["skill_value"], dice=list(d["dice"]),
                   opposition=d.get("opposition"), stunt_bonus=d.get("stunt_bonus", 0),
                   teamwork=d.get("teamwork", 0), dangerous=d.get("dangerous", False), modifiers=mods)

    def summary(self) -> dict:
        """Everything a template needs to show the roll."""
        oc = self.outcome
        lines = list(OUTCOME_TEXT.get(self.action, OUTCOME_TEXT["overcome"])[oc])
        if self.dangerous and oc == "fumble":
            lines.insert(0, DANGEROUS_TEXT)
        if self.teamwork and oc == "fumble":
            lines.append("Teamwork: every helper shares the cost.")
        return {
            "faces": dice_faces(self.dice), "dice_total": self.dice_total, "total": self.total,
            "total_label": ladder(self.total), "shifts": self.shifts, "outcome": oc,
            "outcome_label": oc.capitalize() if oc != "succeed" else "Success",
            "lines": lines, "questions": questions_for(self.action, self.shifts),
            "has_opposition": self.opposition is not None,
            "opposition_label": ladder(self.opposition) if self.opposition is not None else "",
            "action_label": ACTIONS.get(self.action, self.action),
        }


# --------------------------------------------------------------------------------------------
# Characters
# --------------------------------------------------------------------------------------------
def blank_character(name: str = "") -> dict:
    return {
        "name": name, "high_concept": "", "journey": [""] * JOURNEY_ASPECTS, "skills": {},
        "stunts": [], "resources": [], "refresh_base": BASE_REFRESH, "drama_points": BASE_REFRESH,
        "consequences": [{"severity": s, "text": "", "recovering": False} for s in CONSEQUENCE_ORDER],
        "notes": "", "skill_points_banked": 0,
    }


def normalize_character(c: dict) -> dict:
    """Fill in fields an older or partial record may lack, so templates never KeyError."""
    if "fate_points" in c:  # records saved before the rename to drama points
        c.setdefault("drama_points", c.pop("fate_points"))
    base = blank_character()
    for k, v in base.items():
        c.setdefault(k, v)
    while len(c["journey"]) < JOURNEY_ASPECTS:
        c["journey"].append("")
    c["skills"] = {k: int(v) for k, v in c["skills"].items() if int(v) > 0}
    return c


def stunt_count(c: dict) -> int:
    return len(c.get("stunts", [])) + len(c.get("resources", []))


def refresh(c: dict) -> int:
    return int(c.get("refresh_base", BASE_REFRESH)) - max(0, stunt_count(c) - FREE_STUNTS)


def skill_columns(skills: dict[str, int]) -> dict[int, list[str]]:
    cols: dict[int, list[str]] = {}
    for name, v in sorted(skills.items()):
        if v > 0:
            cols.setdefault(v, []).append(name)
    return dict(sorted(cols.items(), reverse=True))


def check_character(c: dict) -> list[dict]:
    """Rule checks as a list of {level: 'warn'|'info'|'ok', text}. Never blocks saving."""
    out: list[dict] = []
    skills = {k: v for k, v in c.get("skills", {}).items() if v > 0}
    counts = {r: sum(1 for v in skills.values() if v == r) for r in range(1, 9)}
    # Skill columns: never more skills at a rank than at the rank below.
    for r in range(2, 9):
        if counts[r] > counts[r - 1]:
            out.append({"level": "warn", "text": f"Skill columns: {counts[r]} at {ladder(r)} but only "
                                                 f"{counts[r - 1]} at {ladder(r - 1)} to support them."})
    if counts == {**{r: 0 for r in range(1, 9)}, **PYRAMID}:
        out.append({"level": "ok", "text": "Starting pyramid complete (1 Great, 2 Good, 3 Fair, 4 Adequate)."})
    elif sum(counts.values()) < sum(PYRAMID.values()) and not any(counts[r] for r in range(5, 9)):
        missing = ", ".join(f"{PYRAMID[r] - counts[r]} {LADDER[r]}" for r in PYRAMID if counts[r] < PYRAMID[r])
        if missing:
            out.append({"level": "info", "text": f"Starting pyramid still open: {missing}."})
    rf = refresh(c)
    if rf < 1:
        out.append({"level": "warn", "text": f"Refresh is {rf}: it can never drop below 1. Remove a stunt."})
    extra = stunt_count(c) - FREE_STUNTS
    if extra > 0:
        out.append({"level": "info", "text": f"{extra} stunt(s) beyond the 3 free ones cost {extra} refresh."})
    if not c.get("high_concept"):
        out.append({"level": "info", "text": "No high concept yet (quick start needs a name, high concept and peak skill)."})
    return out


def consequence_slots(c: dict) -> list[dict]:
    return c.get("consequences", [])


def recovery_difficulty(severity: str, self_treat: bool = False) -> int:
    return CONSEQUENCES[severity]["recover"] + (1 if self_treat else 0)


def open_slot_for(c: dict, severity: str) -> int | None:
    """Index of the slot a consequence of this severity lands in, rolling up when full. None = overwhelmed."""
    want = CONSEQUENCE_ORDER.index(severity)
    slots = consequence_slots(c)
    for idx in sorted(range(len(slots)), key=lambda i: CONSEQUENCE_ORDER.index(slots[i]["severity"])):
        s = slots[idx]
        if CONSEQUENCE_ORDER.index(s["severity"]) >= want and not s["text"].strip():
            return idx
    return None


# --------------------------------------------------------------------------------------------
# Session & chapter housekeeping
# --------------------------------------------------------------------------------------------
def start_session(c: dict) -> dict:
    """Refill drama points up to refresh (keep extras); clear recovering minor/moderate consequences."""
    c["drama_points"] = max(int(c.get("drama_points", 0)), refresh(c))
    for s in c["consequences"]:
        if s["recovering"] and s["severity"] in ("minor", "moderate"):
            s["text"], s["recovering"] = "", False
    return c


def end_scene(c: dict) -> dict:
    """Recovering minor consequences clear when the scene ends."""
    for s in c["consequences"]:
        if s["recovering"] and s["severity"] == "minor":
            s["text"], s["recovering"] = "", False
    return c


def start_chapter(c: dict) -> dict:
    """Reset drama points to refresh (extras lost); clear every recovering consequence."""
    c["drama_points"] = refresh(c)
    for s in c["consequences"]:
        if s["recovering"]:
            s["text"], s["recovering"] = "", False
    return c


MILESTONES = {
    "minor": {
        "label": "Minor milestone", "when": "End of a session",
        "choices": ["Switch the ratings of two skills", "Replace an Adequate (+1) skill with a new one",
                    "Swap one stunt for another", "Rename a journey aspect"],
    },
    "significant": {
        "label": "Significant milestone", "when": "End of a chapter",
        "choices": ["Everything a minor milestone allows", "Gain one skill point (new skill at +1, or raise one by a step; "
                    "you may bank it)", "Spend a refresh on a new stunt (refresh never reaches 0)",
                    "Attempt a journey roll"],
    },
    "major": {
        "label": "Major milestone", "when": "End of a story arc",
        "choices": ["Everything a significant milestone allows", "Rename your high concept", "Raise refresh by one",
                    "Take the result of a successful journey roll (on top of the one you roll)"],
    },
}


# --------------------------------------------------------------------------------------------
# Deductions
# --------------------------------------------------------------------------------------------
DEDUCTION_START_OPPOSITION = 3


def deduction_round(results: list[dict], opposition: int) -> dict:
    """results: [{who, total}]. Returns winner(s), progress and whether a minor cost is owed."""
    best = max((r["total"] for r in results), default=None)
    if best is None or best < opposition:
        return {"winners": [], "progress": 0, "cost": False, "next_opposition": opposition}
    winners = [r["who"] for r in results if r["total"] == best]
    shifts = best - opposition
    progress = 2 if shifts >= 3 else 1
    return {"winners": winners, "progress": progress, "cost": shifts == 0, "next_opposition": best}


def deduction_free_invokes(progress: int) -> int | None:
    """None = unanswered (fewer than 3 progress)."""
    if progress < 3:
        return None
    if progress >= 6:
        return 2
    if progress >= 4:
        return 1
    return 0
