"""Rules-based nudges: what a player might try next, and prompts for a new GM. No AI, no I/O."""
from __future__ import annotations

from . import rules

# What each skill is typically good for, as (action, idea).
SKILL_TIPS = {
    "Athletics": ("overcome", "climb, swim, jump or push past a physical obstacle"),
    "Craft": ("advantage", "improvise a tool or repair something by hand"),
    "Deceive": ("advantage", "bluff, misdirect or put on a convincing act"),
    "Empathy": ("discover", "read how someone really feels or what they want"),
    "Engineering": ("overcome", "get a machine working, or work out what it does"),
    "Experiment": ("advantage", "test a theory: set up a trial and see what happens"),
    "Finesse": ("advantage", "do something delicate: pick a mechanism, balance, sleight of hand"),
    "Intrusion": ("overcome", "get through a lock, seal or security system"),
    "Medicine": ("overcome", "treat an injury, yours or someone else's"),
    "Notice": ("discover", "look around for what others missed"),
    "Provoke": ("advantage", "rattle someone into reacting"),
    "Rapport": ("advantage", "win someone over and get them talking"),
    "Research": ("discover", "dig through books, notes or records"),
    "Stealth": ("overcome", "move unseen or unheard"),
    "Surveying": ("discover", "read the land, the structure or the layout"),
    "Survival": ("discover", "track, forage, or read weather and wild signs"),
    "Will": ("overcome", "steady your nerve, resist pressure, push through"),
}

ACTION_WORD = {"overcome": "Overcome", "advantage": "Create an advantage", "discover": "Discover",
               "create": "Create an advantage", "take": "Take advantage", "oppose": "Oppose"}


def _hook(h) -> dict:
    if isinstance(h, str):
        return {"text": h, "skill": "", "action": ""}
    return {"text": h.get("text", ""), "skill": h.get("skill", ""), "action": h.get("action", "")}


def for_player(ch: dict, scene: dict, area: dict | None = None, frontier_teasers: list[str] = (),
               pending_roll: dict | None = None) -> list[dict]:
    """Up to ~7 suggestions as {title, detail, skill, action, kind}. `area` is the player-safe current area."""
    d = ch["data"]
    skills = d.get("skills", {})
    out: list[dict] = []

    def add(title, detail="", skill="", action="", kind="idea"):
        out.append({"title": title, "detail": detail, "skill": skill, "action": action, "kind": kind,
                    "rating": skills.get(skill, 0) if skill else None})

    if pending_roll:
        add(f"The GM called for a roll: {pending_roll['label']}",
            f"{ACTION_WORD.get(pending_roll['action'], 'Roll')} vs {rules.ladder(pending_roll['difficulty'])}"
            f" using {' or '.join(pending_roll['skills']) or 'any fitting skill'}.", kind="roll")

    if area:
        for h in map(_hook, area.get("hooks", [])):
            if h["text"]:
                sk = h["skill"]
                detail = (f"{ACTION_WORD.get(h['action'], 'Roll')} with {sk} ({rules.ladder(skills.get(sk, 0))})"
                          if sk else "")
                add(h["text"], detail, sk, h["action"], "area")

    for a in scene.get("aspects", []):
        if a.get("free"):
            add(f"Use the free invoke on “{a['text']}”", "+2 or a reroll on a roll where it helps, no fate point needed.",
                kind="invoke")
            break

    for t in frontier_teasers[:2]:
        add(f"Explore: {t}", "Tap it on the map to ask the GM to inspect it.", kind="explore")

    for s in d.get("consequences", []):
        if s.get("text") and not s.get("recovering"):
            diff = rules.CONSEQUENCES[s["severity"]]["recover"]
            add(f"Treat “{s['text']}”", f"Overcome vs {rules.ladder(diff)} (one harder on yourself); "
                f"someone with Medicine can help.", "Medicine", "overcome", "heal")
            break

    best = sorted(skills.items(), key=lambda kv: -kv[1])[:3]
    have = {o["skill"] for o in out}
    for sk, v in best:
        if sk in have or sk not in SKILL_TIPS:
            continue
        act, idea = SKILL_TIPS[sk]
        add(f"Play to your strength: {sk} ({rules.ladder(v)})", f"{ACTION_WORD[act]}: {idea}.", sk, act, "skill")

    fp = d.get("fate_points", 0)
    aspects = [x for x in [d.get("high_concept", ""), *d.get("journey", [])] if x]
    if fp == 0:
        add("You're out of fate points", "Lean into your aspects so the GM can compel them (+1 each), "
            "or make a sacrifice: take a consequence for 1–3 points.", kind="fp")
    elif aspects:
        add(f"{fp} fate point{'s' if fp != 1 else ''} to spend",
            f"When a roll matters, invoke “{aspects[0]}” (or another aspect that fits) for +2 or a reroll.",
            kind="fp")
    return out[:8]


def compel_ideas(pcs: list[dict]) -> list[dict]:
    """For a new GM: each explorer's aspects as compel prompts."""
    out = []
    for c in pcs:
        d = c["data"]
        for a in [d.get("high_concept", ""), *d.get("journey", [])]:
            if a:
                out.append({"who": d["name"], "char_id": c["id"], "aspect": a})
    return out


GM_TIPS = [
    ("Start of a scene", "Read the boxed text, name one or two situation aspects, then ask “What do you do?”"),
    ("Setting difficulty", "Mediocre 0 trivial · Adequate +1 easy · Fair +2 routine for a pro · Good +3 hard · "
                           "Great +4 very hard · Superb +5 heroic. When unsure, pick Fair (+2)."),
    ("When a roll fails", "Failure should change the story, not stop it. Offer success at a cost: a complication, "
                          "lost time, a consequence, or an advantage for the other side."),
    ("Only roll when it matters", "If failing wouldn't be interesting, just say yes."),
    ("Compels", "When an aspect would make life harder in a fun way, offer a compel. It's how players earn fate "
                "points, so offer one or two per session per player."),
    ("Discover answers", "Each question earned deserves a true, useful answer. Use the area's secrets."),
    ("Spotlight", "Rotate who you ask “What do you do?”. Quiet players often have the best ideas."),
    ("End of a scene", "End it once the question it posed is answered. Use End scene to clear boosts."),
]
