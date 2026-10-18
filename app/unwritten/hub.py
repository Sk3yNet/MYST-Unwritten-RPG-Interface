"""In-process pub/sub: each open table page holds one queue per campaign."""
from __future__ import annotations

import asyncio
from collections import defaultdict


class Hub:
    def __init__(self) -> None:
        self._subs: dict[int, set[asyncio.Queue]] = defaultdict(set)

    def subscribe(self, cid: int) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subs[cid].add(q)
        return q

    def unsubscribe(self, cid: int, q: asyncio.Queue) -> None:
        self._subs[cid].discard(q)

    def publish(self, cid: int, *topics: str) -> None:
        for q in list(self._subs.get(cid, ())):
            for t in topics:
                try:
                    q.put_nowait(t)
                except asyncio.QueueFull:
                    pass

    def listeners(self, cid: int) -> int:
        return len(self._subs.get(cid, ()))
