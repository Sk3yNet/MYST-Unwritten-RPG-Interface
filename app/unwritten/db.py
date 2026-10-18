"""SQLite storage. Records are mostly JSON blobs; the tables only index what we query by."""
from __future__ import annotations

import json
import secrets
import time

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    email TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '', created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS campaigns (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, gm_email TEXT NOT NULL, invite TEXT NOT NULL UNIQUE,
    scene TEXT NOT NULL DEFAULT '{}', created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS members (
    campaign_id INTEGER NOT NULL, email TEXT NOT NULL, role TEXT NOT NULL, joined REAL NOT NULL,
    PRIMARY KEY (campaign_id, email)
);
CREATE TABLE IF NOT EXISTS characters (
    id INTEGER PRIMARY KEY, campaign_id INTEGER NOT NULL, owner_email TEXT NOT NULL, kind TEXT NOT NULL,
    data TEXT NOT NULL, updated REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS characters_campaign ON characters (campaign_id);
CREATE TABLE IF NOT EXISTS log (
    id INTEGER PRIMARY KEY, campaign_id INTEGER NOT NULL, ts REAL NOT NULL, email TEXT NOT NULL,
    kind TEXT NOT NULL, data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS log_campaign ON log (campaign_id, id);
CREATE TABLE IF NOT EXISTS deductions (
    id INTEGER PRIMARY KEY, campaign_id INTEGER NOT NULL, data TEXT NOT NULL, open INTEGER NOT NULL,
    created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS timeline (
    id INTEGER PRIMARY KEY, campaign_id INTEGER NOT NULL, greg TEXT NOT NULL, title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '', gm_only INTEGER NOT NULL DEFAULT 0
);
"""

EMPTY_SCENE = {"name": "", "aspects": [], "boosts": [], "notes": "", "next_id": 1}


class DB:
    def __init__(self, path: str):
        self.path = path
        self.conn: aiosqlite.Connection | None = None

    async def open(self) -> None:
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.execute("PRAGMA journal_mode=WAL")
        await self.conn.executescript(SCHEMA)
        await self.conn.commit()

    async def close(self) -> None:
        if self.conn:
            await self.conn.close()

    async def _one(self, sql: str, *args):
        async with self.conn.execute(sql, args) as cur:
            return await cur.fetchone()

    async def _all(self, sql: str, *args):
        async with self.conn.execute(sql, args) as cur:
            return await cur.fetchall()

    async def _run(self, sql: str, *args) -> int:
        cur = await self.conn.execute(sql, args)
        await self.conn.commit()
        return cur.lastrowid

    # users ------------------------------------------------------------------------------------
    async def ensure_user(self, email: str) -> dict:
        row = await self._one("SELECT * FROM users WHERE email=?", email)
        if not row:
            await self._run("INSERT INTO users (email, name, created) VALUES (?,?,?)",
                            email, email.split("@")[0], time.time())
            row = await self._one("SELECT * FROM users WHERE email=?", email)
        return dict(row)

    async def set_user_name(self, email: str, name: str) -> None:
        await self._run("UPDATE users SET name=? WHERE email=?", name, email)

    async def user_names(self, emails) -> dict[str, str]:
        emails = list(emails)
        if not emails:
            return {}
        rows = await self._all(f"SELECT email, name FROM users WHERE email IN ({','.join('?' * len(emails))})",
                               *emails)
        return {r["email"]: r["name"] or r["email"] for r in rows}

    # campaigns --------------------------------------------------------------------------------
    async def create_campaign(self, name: str, gm_email: str) -> int:
        cid = await self._run("INSERT INTO campaigns (name, gm_email, invite, scene, created) VALUES (?,?,?,?,?)",
                              name, gm_email, secrets.token_urlsafe(12), json.dumps(EMPTY_SCENE), time.time())
        await self.add_member(cid, gm_email, "gm")
        return cid

    async def campaign(self, cid: int) -> dict | None:
        row = await self._one("SELECT * FROM campaigns WHERE id=?", cid)
        if not row:
            return None
        c = dict(row)
        c["scene"] = {**EMPTY_SCENE, **json.loads(c["scene"])}
        return c

    async def campaign_by_invite(self, token: str) -> dict | None:
        row = await self._one("SELECT id FROM campaigns WHERE invite=?", token)
        return await self.campaign(row["id"]) if row else None

    async def rename_campaign(self, cid: int, name: str) -> None:
        await self._run("UPDATE campaigns SET name=? WHERE id=?", name, cid)

    async def new_invite(self, cid: int) -> str:
        token = secrets.token_urlsafe(12)
        await self._run("UPDATE campaigns SET invite=? WHERE id=?", token, cid)
        return token

    async def save_scene(self, cid: int, scene: dict) -> None:
        await self._run("UPDATE campaigns SET scene=? WHERE id=?", json.dumps(scene), cid)

    async def campaigns_for(self, email: str) -> list[dict]:
        rows = await self._all("SELECT c.id, c.name, c.gm_email, m.role FROM campaigns c JOIN members m "
                               "ON m.campaign_id=c.id WHERE m.email=? ORDER BY c.created DESC", email)
        return [dict(r) for r in rows]

    async def delete_campaign(self, cid: int) -> None:
        for table in ("members", "characters", "log", "deductions", "timeline"):
            await self.conn.execute(f"DELETE FROM {table} WHERE campaign_id=?", (cid,))
        await self._run("DELETE FROM campaigns WHERE id=?", cid)

    # members ----------------------------------------------------------------------------------
    async def add_member(self, cid: int, email: str, role: str) -> None:
        await self._run("INSERT OR IGNORE INTO members (campaign_id, email, role, joined) VALUES (?,?,?,?)",
                        cid, email, role, time.time())

    async def role(self, cid: int, email: str) -> str | None:
        row = await self._one("SELECT role FROM members WHERE campaign_id=? AND email=?", cid, email)
        return row["role"] if row else None

    async def members(self, cid: int) -> list[dict]:
        rows = await self._all("SELECT m.email, m.role, u.name FROM members m LEFT JOIN users u ON u.email=m.email "
                               "WHERE campaign_id=? ORDER BY m.role, m.joined", cid)
        return [dict(r) for r in rows]

    async def remove_member(self, cid: int, email: str) -> None:
        await self._run("DELETE FROM members WHERE campaign_id=? AND email=? AND role!='gm'", cid, email)

    # characters -------------------------------------------------------------------------------
    async def create_character(self, cid: int, owner: str, kind: str, data: dict) -> int:
        return await self._run("INSERT INTO characters (campaign_id, owner_email, kind, data, updated) "
                               "VALUES (?,?,?,?,?)", cid, owner, kind, json.dumps(data), time.time())

    async def character(self, ch_id: int) -> dict | None:
        row = await self._one("SELECT * FROM characters WHERE id=?", ch_id)
        if not row:
            return None
        c = dict(row)
        c["data"] = json.loads(c["data"])
        return c

    async def characters(self, cid: int, kind: str | None = None) -> list[dict]:
        if kind:
            rows = await self._all("SELECT * FROM characters WHERE campaign_id=? AND kind=? ORDER BY id", cid, kind)
        else:
            rows = await self._all("SELECT * FROM characters WHERE campaign_id=? ORDER BY kind DESC, id", cid)
        out = []
        for r in rows:
            c = dict(r)
            c["data"] = json.loads(c["data"])
            out.append(c)
        return out

    async def save_character(self, ch_id: int, data: dict) -> None:
        await self._run("UPDATE characters SET data=?, updated=? WHERE id=?", json.dumps(data), time.time(), ch_id)

    async def delete_character(self, ch_id: int) -> None:
        await self._run("DELETE FROM characters WHERE id=?", ch_id)

    # log --------------------------------------------------------------------------------------
    async def add_log(self, cid: int, email: str, kind: str, data: dict) -> int:
        return await self._run("INSERT INTO log (campaign_id, ts, email, kind, data) VALUES (?,?,?,?,?)",
                               cid, time.time(), email, kind, json.dumps(data))

    async def log_entry(self, lid: int) -> dict | None:
        row = await self._one("SELECT * FROM log WHERE id=?", lid)
        if not row:
            return None
        e = dict(row)
        e["data"] = json.loads(e["data"])
        return e

    async def save_log(self, lid: int, data: dict) -> None:
        await self._run("UPDATE log SET data=? WHERE id=?", json.dumps(data), lid)

    async def recent_log(self, cid: int, limit: int = 60) -> list[dict]:
        rows = await self._all("SELECT * FROM log WHERE campaign_id=? ORDER BY id DESC LIMIT ?", cid, limit)
        out = []
        for r in rows:
            e = dict(r)
            e["data"] = json.loads(e["data"])
            out.append(e)
        return out

    # deductions -------------------------------------------------------------------------------
    async def open_deduction(self, cid: int) -> dict | None:
        row = await self._one("SELECT * FROM deductions WHERE campaign_id=? AND open=1 ORDER BY id DESC LIMIT 1", cid)
        if not row:
            return None
        d = dict(row)
        d["data"] = json.loads(d["data"])
        return d

    async def past_deductions(self, cid: int) -> list[dict]:
        rows = await self._all("SELECT * FROM deductions WHERE campaign_id=? AND open=0 ORDER BY id DESC", cid)
        return [{**dict(r), "data": json.loads(r["data"])} for r in rows]

    async def create_deduction(self, cid: int, data: dict) -> int:
        return await self._run("INSERT INTO deductions (campaign_id, data, open, created) VALUES (?,?,1,?)",
                               cid, json.dumps(data), time.time())

    async def save_deduction(self, did: int, data: dict, is_open: bool = True) -> None:
        await self._run("UPDATE deductions SET data=?, open=? WHERE id=?", json.dumps(data), int(is_open), did)

    # timeline ---------------------------------------------------------------------------------
    async def timeline(self, cid: int, include_hidden: bool) -> list[dict]:
        sql = "SELECT * FROM timeline WHERE campaign_id=?" + ("" if include_hidden else " AND gm_only=0")
        rows = await self._all(sql + " ORDER BY greg", cid)
        return [dict(r) for r in rows]

    async def add_timeline(self, cid: int, greg: str, title: str, body: str, gm_only: bool) -> int:
        return await self._run("INSERT INTO timeline (campaign_id, greg, title, body, gm_only) VALUES (?,?,?,?,?)",
                               cid, greg, title, body, int(gm_only))

    async def delete_timeline(self, cid: int, tid: int) -> None:
        await self._run("DELETE FROM timeline WHERE id=? AND campaign_id=?", tid, cid)
