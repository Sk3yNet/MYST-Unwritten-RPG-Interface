# Painted maps: prompts for an image generator

Each map has a **base image** in [`prompts/`](prompts/): the drawn map with its words, numbers, title and frame
removed. Give the generator the base image *and* the prompt, so the painting keeps every area where the campaign
expects it. (Regenerate the bases with `python3 campaigns/tools/base_images.py concordance`.)

## How to use them

* **ChatGPT:** upload the base image, paste the shared style and then the map's prompt, and ask for a landscape
  image (1536 × 1024). Tips:
  * Make all the maps of one adventure in **one chat**, and once one looks right, say "same painting style as the
    previous map" so the set matches.
  * To fix part of a picture, **edit it rather than regenerate**: open the image, use the selection tool to brush
    over the problem (a square coastline, stray text) and describe only that change, e.g. "make this a natural
    rocky coastline" or "join these two islands with a low rock causeway". The rest stays as it is.
  * If it adds words or numbers, select them and say "remove the text, paint the scenery underneath".
* **Midjourney:** upload the base image, use it as an image prompt with a high weight (`--iw 2`), add `--ar 10:7`,
  then paste the shared style and the map's prompt. Once one map looks right, use it as a style reference (`--sref`)
  for the other five so the set matches.
* **Stable Diffusion / Flux:** img2img at a denoise of about 0.55–0.7, or ControlNet (canny or depth) on the base
  image with the prompt.

If a result moves things around, say so in a follow-up ("keep the platforms exactly where they are in the reference").
A little drift is fine: the areas are traced on the finished picture, not the base.

**Then:** put the picture in `maps/` (e.g. `maps/sky-monastery.jpg`), point the map's `file:` at it, and trace the
areas with **✎ Trace** on the GM Screen (or ask Claude to do it). Keep the SVG versions as a fallback.

## Shared style (paste first, every time)

> A hand-painted fantasy map in the style of the Myst games: an overhead three-quarter view, like a detailed
> illustrated board-game map. Rich painterly texture, soft atmospheric light, fine architectural detail in brass,
> carved stone and old wood, quiet and mysterious, no people. Keep the layout of the reference image exactly: every
> platform, building, walkway and bridge stays in the same place, at the same size and shape. **No text, letters,
> numbers, labels, title, legend, frame, border or compass anywhere in the image.**

## 1. The Cartographer's Sanctuary — `sanctuary-base.jpg`

> An enclosed, lamp-lit scholar's sanctuary in warm sepia, gold and deep brown, seen from above as a cutaway of
> rooms on a dark parchment-coloured ground. In the centre, a round chamber holds a great machine of five concentric
> brass rings over a dark rippling pool, with a pale glowing point at its heart and stone pillars around its rim.
> To the left, a tall library of dark wooden bookshelves. To the right, a gallery of five tall glass display cases,
> each holding a book. Above, a curved balcony gallery beneath a painted dome of constellations, reached by a thin
> brass lift. Lower left, a cosy reading alcove with cushions, a desk and a small lamp. Lower right, a small study
> with a desk, a cold hearth and a dark doorway. Short stone passages join the rooms to the central chamber.

## 2. The Frozen Observatory — `frozen-observatory-base.jpg`

> A frozen observatory on a high glacier under a pale, low, unmoving sun. Blue-white ice, snow, jagged ice crags
> and frost-rimed brass. Lower left, a small round ledge of blue ice (the arrival point). In the centre, a wide round
> terrace with three enormous crystal mirrors on brass pivots, a thin beam of pale gold light lying across the ice.
> Upper left, a long stone hall with four brass telescopes aimed at a wall of clear blue ice. Upper middle-right, a
> stone archive room with star charts under glass and a tiny brass ring-machine on a pedestal. Far right, a tall
> round tower with a conical roof and a great telescope. Lower right, a round stone cistern of black, half-frozen
> water with floating ice. Stone stairways and ice bridges join them. Cold blues, whites and pale gold.

## 3. The Ember Forge — `ember-forge-base.jpg`

> A volcanic forge-world of black basalt over rivers of glowing orange lava, under a smoky red sky; sparks and heat
> shimmer. Lower left, a small round basalt landing beside the lava. Centre, a square valve gallery with two great
> brass valve wheels and a pressure gauge. Above it, a huge round hall of slowly turning brass gears as big as
> houses. Centre right, a narrow brass steam lift on a tall dark shaft. Upper right, a bell foundry with a crucible
> under a hood and a row of five bell moulds. Lower middle-right, a stone platform crossed by two straight, bright
> channels of lava. Far lower right, a small round shrine on an island of black rock, light glinting through holes
> in its roof. Thick stone causeways join them. Deep blacks, molten orange, brass and red.

## 4. The Sky Monastery — `sky-monastery-base.jpg`

> A monastery on floating islands of pale stone drifting in a vast sky of luminous clouds; each island has a rocky,
> jagged underside hanging into the void. Islands are tied together by sagging rope-and-plank bridges, and small
> windmills turn on the roofs; prayer flags stream in the wind. Lower left, a small arrival island with a wind gate.
> Centre, a broad terrace with three great prayer wheels. Upper left, an open belfry hung with hundreds of wind
> chimes and a single stone seat. Three slender towers with conical roofs and painted panels near their tops: one
> at the top centre (the tallest), one lower right, one far right. Upper right, a summit shrine with a door of
> slatted bronze. Sky blues, cloud whites, warm sandstone and red-tiled roofs.

## 5. The Verdant Labyrinth — `verdant-labyrinth-base.jpg`

> An ancient overgrown garden-labyrinth under a dense jungle canopy: moss-covered ruins, giant roots, ferns, dappled
> green light and birdsong atmosphere. Lower left, an arch of roots as thick as pillars (the arrival gate). Centre
> bottom, a round clearing in a shaft of sunlight with a tarnished green bronze sun-mirror on a swivel. Left, three
> stone tanks of rainwater with sluice gates. Centre top, terraced gardens with four planted seed beds. A deep narrow
> ravine runs top to bottom on the right, its floor lost in ferns, with no bridge across it. Beyond the ravine,
> lower right, a great round stone carved with five nested rings; upper right, an enormous ancient tree with a vast
> trunk. Greens, moss, weathered grey stone and warm sunlight.

## 6. The Tidal Cathedral — `tidal-cathedral-base.jpg`

> A drowned cathedral at night, half-flooded by a still, dark sea under a bright moon; glass floors gleam beneath
> clear water and every pillar is mirrored in the surface. Lower left, wide stone steps leading down into the water.
> Centre, a long flooded nave with rows of pillars and a vaulted, painted ceiling, its floor under shallow
> moonlit water. Left, a round platform with a great brass tide wheel. Top centre, a round moon pool beneath an
> open oculus, glowing with moonlight. Right side, from bottom to top: a hall of bells hanging at every height (some
> under water), a low drowned crypt, and a round apse lit through blue glass. Stone walkways join them. Deep teal,
> moonlit silver, wet stone and pale blue light.
