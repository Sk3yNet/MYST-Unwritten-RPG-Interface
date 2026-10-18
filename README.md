# Unwritten Table

A self-hosted, live table companion for **Unwritten: Adventures in the Ages of MYST and Beyond**: character sheets,
a Fate dice roller, a GM scene board, compels, deductions, milestones, and D’ni tools, all in a parchment-and-brass
journal style. Players and the GM share one live table in the browser.

This is a fan project. It ships **no rulebook text**: the mechanics (Fate Core, Open Game Content) are summarized in
our own words, and setting material stays in your own copy of the book. Myst, D’ni and Unwritten are © Cyan, Inc.
The D’ni font (`app/unwritten/static/fonts/DniFont.ttf`, © 1995 Cyan, Inc.) is the freely distributed one;
IM Fell English and EB Garamond are under the SIL Open Font License.

> **Never commit the PDFs.** `.gitignore` blocks `*.pdf`, `*.zip`, `sources/` and `private/`, because this repository
> is public and the books are not licensed for redistribution.

## What it does

| For | Feature |
| --- | --- |
| Everyone | **Live table**: rolls, compels, aspects and fate points update on every screen at once (Server-Sent Events). |
| Players | **Character sheet** with rule checks: the starting skill pyramid, skill columns, refresh (3 free stunts/resources, −1 per extra, never below 1), four journey aspects, consequence slots with recovery difficulty. Export/import as JSON, print. |
| Players | **Fate roller**: 4dF + skill + stunt + teamwork vs opposition. Outcome (fumble/tie/success/excel) with the options for each action (Overcome, Advantage create/take, Discover, Oppose), Discover question counter, cost lists, dangerous actions. **Invoke** after the roll for +2 or a reroll, paid with a fate point, a free invoke or a boost (one fate-point invoke per aspect per roll). |
| Players | **Consequences**: take one (rolls up to the next open slot, or you’re overwhelmed), sacrifice for 1/2/3 fate points, mark recovering. |
| GM | **Scene board**: situation aspects with free-invoke pips, boosts (promote to aspects), scene notes. **End scene / New session / New chapter** apply the fate point and recovery rules to every explorer. **Milestones** post each level’s choices and bank skill points. |
| GM | **Compels**: offer one on any explorer’s aspect; the player accepts (+1 FP) or buys it off (−1 FP). |
| GM | **NPCs**: full sheets, hidden from players until revealed; roll for them or for anyone (custom roll). |
| Table | **Deductions**: frame a question, players join with a reason, three rounds vs Good (+3) and then the previous winning total, progress tracking, winners declare facts (placed as aspects), the reveal roll, and the truth aspect with 0–2 free invokes. |
| Table | **D’ni lore**: a live cavern clock (hahr, vailee, yahr, bell), surface⇄D’ni date conversion, base-25 numbers in D’ni numerals, a transcription→D’ni script writer, the alphabet, and a **campaign timeline** with both calendars (GM-only entries allowed). |
| Table | **Rules quick reference** in our own words; a “cavern” dark theme next to the parchment one. |

## How people join

1. The GM signs in with Google and starts a campaign (**Begin a new journal**).
2. On the **GM’s Desk** they copy the invite link and send it to players. **New link** retires the old one.
3. A player opens the link, signs in with Google, and joins with one click. A campaign is invisible to anyone who
   hasn’t joined it.

`ALLOWED_EMAIL` / `ALLOWED_DOMAINS` can narrow who may sign in at all, and `GM_EMAILS` who may start campaigns.

## Deploy (Portainer, same shape as the Replicant Space client)

```
Internet ─► Cloudflare ─► cloudflared ─► nginx ─(auth_request)─► oauth2-proxy ─► Google sign-in
                                           └─► app (FastAPI + htmx, SQLite in a volume)
```

No host ports are published: the Cloudflare tunnel is the only way in, and nginx checks every request (including the
live stream) with oauth2-proxy. Only `/static/` (fonts, CSS, JS) and `/healthz` are public.

1. **Google OAuth client.** In <https://console.cloud.google.com/>, use your existing project or a new one.
   **APIs & Services ▸ Credentials ▸ Create credentials ▸ OAuth client ID ▸ Web application**, with the authorized
   redirect URI `https://<PUBLIC_HOST>/oauth2/callback`. On the **OAuth consent screen**, either add each player as a
   test user (up to 100) or **Publish app**. With only the basic email/profile scopes, publishing needs no Google review.
2. **Cloudflare tunnel.** In Zero Trust ▸ Networks ▸ Tunnels, create a tunnel (or add a public hostname to an
   existing one) pointing `<PUBLIC_HOST>` at `http://nginx:80`, and copy its token.
3. **Portainer.** Stacks ▸ Add stack ▸ Repository: this repo, compose path `docker-compose.yml`. Fill in the
   variables from `.env.example`:

   | Variable | Value |
   | --- | --- |
   | `PUBLIC_HOST` | e.g. `unwritten.yourdomain.com` |
   | `CF_TUNNEL_TOKEN` | from step 2 |
   | `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | from step 1 |
   | `OAUTH2_COOKIE_SECRET` | output of `python3 -c "import secrets,base64;print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"` |
   | `GM_EMAILS` | optional: who may start campaigns |
   | `ALLOWED_EMAIL`, `ALLOWED_DOMAINS` | optional: who may sign in at all |

4. Deploy, open `https://<PUBLIC_HOST>`, sign in, and start a journal.

Everything lives in the `unwritten-data` volume (`/data/unwritten.sqlite`); back that up.

## Develop

```bash
cd app
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -q
# Run locally with auth bypassed (pretend to be one user):
DEV_USER=you@example.com DB_PATH=dev.sqlite uvicorn unwritten.main:app --reload --port 8000
```

To try two people at once locally, leave `DEV_USER` unset and send an `X-Auth-Request-Email` header, for example
with a browser extension or Playwright’s `extra_http_headers`.

```
app/unwritten/rules.py      game mechanics (pure functions, no I/O): ladder, outcomes, refresh, checks, deductions
app/unwritten/dni.py        base-25 numbers, the D'ni calendar and clock, script transcription
app/unwritten/main.py       FastAPI routes, permissions, live updates
app/unwritten/db.py         SQLite storage
app/unwritten/templates/    Jinja2 pages and htmx fragments
app/unwritten/static/       CSS, JS (htmx 2 + SSE extension), fonts, dni.js (mirrors dni.py)
nginx/, docker-compose.yml  the Portainer stack
```

Changes go in `app/unwritten/version.py` (`VERSION` and `CHANGES`).
