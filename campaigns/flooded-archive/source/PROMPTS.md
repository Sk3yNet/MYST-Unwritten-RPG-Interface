# Painted maps: prompts for an image generator

Each map has a **base image** in [`prompts/`](prompts/): the drawn map with its words and numbers removed. Give the
generator the base image *and* the prompt so the painting keeps every area where the adventure expects it. How to
use them with ChatGPT, Midjourney or Stable Diffusion, and what to do with the result, is in
[The Concordance's PROMPTS.md](../../concordance/source/PROMPTS.md#how-to-use-them).

## Shared style (paste first, every time)

> A hand-painted fantasy map in the style of the Myst games: an overhead three-quarter view, like a detailed
> illustrated board-game map. Rich painterly texture, soft atmospheric light, fine architectural detail in brass,
> carved stone and old wood, quiet and mysterious, no people. Keep the layout of the reference image exactly: every
> room, wall and passage stays in the same place, at the same size and shape. **No text, letters, numbers, labels,
> title, legend, frame, border or compass anywhere in the image.**

## 1. The Archivists' Hall, Lower Ward — `archive-base.jpg`

> A flooded D'ni archive deep underground, lit by the orange glow of a cavern lake; black water, carved grey stone,
> wet paper and brass. Lower left, stone stairs descending from a harbour walk straight into black water through a
> carved archway. Lower centre, a long reading hall with rows of stone tables standing in water like boats at
> anchor, ledgers floating between them, and pillars carved with coiled shells. Upper left, a pump room of huge
> half-submerged brass gears and pipes. Lower right, collapsed bookshelves fallen against one another like dominoes.
> Upper centre, a dry, sealed study with a desk, a pushed-back chair and an open journal. Right, a great circular
> stone vault door with three dials, a seam of light leaking around its edge. Top right, a small alcove with a
> single pedestal holding an open book that glows violet. Dark blues, black water, orange lake-light, grey stone.

Add for the hall (the base image has no doors, and "glowing lake" can come back as lava):

> The archive stands in the still, dark WATER of a vast underground lake, NOT lava: the water glows faintly orange
> from light deep beneath its surface. Every room is connected by visible open doorways or arches in its walls:
> the landing to the reading hall and to the pump room; the reading hall to the pump room's neighbour the study
> (by the steps at its far end) and to the collapsed stacks; the pump room to the study; the study and the stacks
> each to the vault room; and the great round stone door stands upright in the wall between the vault room and the
> small alcove beyond it, closed.

## 2. The Age of Seleshva — `seleshva-sketch.jpg` (preferred) or `seleshva-base.jpg`

The drawn map's areas are boxes, and a generator copies them as square islands. `seleshva-sketch.jpg` is a loose
colour sketch with natural coastlines instead; use it with a *lower* image weight (Midjourney `--iw 1`, img2img
denoise about 0.75), and add the coastline paragraph below to the prompt.

> A strange coastal Age under a low violet sun that never moves; a bruise-coloured sea with the tide rushing out,
> wet rocks and spray. Lower left, a stone pier slick with spray. Centre, a wide field of reeds made of something
> like glass, glinting, with a trodden path winding through them. Top centre, a ridge with a tarp lean-to, a cold
> fire ring and papers pinned under stones. Lower right, a staircase of rock pools left by the retreating sea, brass
> rings set in their floors, something rectangular glinting in the lowest pool. Upper right, a tall white lighthouse
> of fitted stone with its lamp turning. Violet, indigo, sea-green, wet black rock and white stone.

Add for Seleshva:

> One natural tidal island, not separate blocks: an irregular, eroded coastline with coves, sea stacks, tumbled
> boulders and sandy necks between the parts. The reed field follows the shape of the land, with ragged soft edges,
> not a rectangle. The camp sits on a grassy rise; the lighthouse stands on a rocky headland joined to the island by
> a low causeway of rock; the tide pools are on a flat shelf of dark rock stepping down to the sea. The pier is the
> only built straight edge. The reference sketch shows only rough positions; do not copy its flat shapes or colours.
