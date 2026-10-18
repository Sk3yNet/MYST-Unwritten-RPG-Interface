# Adventures

Each folder here is one adventure the GM can load on the GM's Desk. Players never receive this content directly:
the server sends a map area only after it's revealed, and a handout only after the GM shows it.

```
campaigns/<slug>/
  campaign.yaml      chapters, scenes, maps, areas, NPCs, handouts
  maps/*.svg         maps (fog of war is applied by the server)
  handouts/*         images (SVG, PNG, JPG, GIF, WebP) or video (MP4, WebM)
```

Ids (`<slug>`, map, area, handout and scene ids) use lower-case letters, digits, `-` and `_`.

## campaign.yaml

```yaml
title: The Flooded Archive
summary: One-paragraph pitch shown when choosing an adventure.
players: 2-5 explorers
book:                       # optional: how it looks on the lobby shelf
  spine: The Flooded Archive                # identifier on the spine
  volume: "Vol. I"
  color: "#1f4a5a"                          # leather color
  cover: handouts/cover.svg                 # logo on the cover (and on the spine)
  preview: handouts/preview.svg             # plays in the linking window when the Book opens (4:3, animated SVG/GIF)
gm_intro: |                 # Markdown-lite: paragraphs, * bullets, **bold**, *italics*
  Shown on the GM Screen before the first scene.

npcs:                       # created as hidden NPC sheets when the adventure is loaded
  - name: Ilse Varga
    high_concept: Restless Surveyor Who Never Turns Back
    aspects: ["I Can Fix This Myself"]        # up to four
    skills: {Surveying: 4, Engineering: 3}
    stunts: [{name: ..., text: ...}]          # optional
    gm_notes: How to play them.

maps:
  - id: archive
    name: The Archivists' Hall
    file: maps/archive.svg
    start_revealed: [landing]                 # revealed when the adventure loads
    areas:
      - id: landing
        name: The Flooded Landing             # players see it once revealed
        teaser: Harbor stairs                 # what players see on the fog's edge before it's revealed
        shape: [80, 470, 220, 170]            # [x, y, width, height] or "x,y x,y x,y ..." in the SVG's viewBox
        read_aloud: Boxed text for the GM to read; players see it once revealed.
        gm_notes: GM only.
        secrets: ["GM-only answers to Discover questions"]
        hooks:                                # player suggestions once revealed
          - {text: "Follow the rope", skill: Notice, action: discover}   # action: overcome | advantage | discover
        aspects: ["Knee-Deep and Rising"]     # the GM can place them on the scene board
        handouts: [journal]                   # quick "show" buttons on the area
        discover: {difficulty: 2, skills: [Notice, Surveying], action: discover}  # default roll to reveal it
        exits: [hall, pump]                   # neighbors: unrevealed exits form the fog's explorable edge

handouts:
  - id: journal
    file: handouts/journal.svg
    caption: Shown under the image
    effect: fade                              # fade | link | reveal | flash | none
    gm_notes: When to show it.

chapters:
  - title: "Chapter 1: Into the Archive"
    summary: ...
    scenes:
      - id: arrival
        title: The Flooded Landing
        map: archive                          # shown to players when the scene starts
        reveal: [landing]                     # revealed when the scene starts
        read_aloud: ...
        goal: What the scene is about (also shown to players as the scene note).
        gm_notes: ...
        aspects: ["Knee-Deep and Rising"]     # replace the scene board's aspects when it starts
        npcs: ["Ilse Varga"]                  # quick cards on the GM Screen
        handouts: [journal]
        compel_ideas: ["..."]
        if_stuck: ["..."]
        ends_when: ...
```

## Map SVGs

* Give the root a `viewBox` (e.g. `0 0 1000 700`); area `shape`s use those coordinates.
* Put everything that belongs to an area inside `<g data-area="<area id>">…</g>`, including its label. Players'
  copies of the map have those groups **removed** until the area is revealed.
* Anything outside an area group (frame, title, compass, sea) is always visible.
* Prefix `id`s inside the SVG (`ar-ink`, `se-sea`) so two maps never clash on one page. No scripts.
* Handout SVGs are shown inline, so they can use the page fonts (`IM Fell English`, `EB Garamond`, and `Dni` for
  D'ni script and numerals) and SMIL animation (`<animate>`, `<animateTransform>`).
