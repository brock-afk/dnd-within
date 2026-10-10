"""Telling open shared views that their character changed, so they refresh right away.

In-process only: each open view holds a queue here, and requests that change a character
wake the queues for it. That's enough because the app runs as a single uvicorn process; with
several workers a change in one wouldn't reach views connected to another, and this would
need a shared channel (MySQL polling or Redis) instead.

Only touched from the event loop (async middleware and the event stream), so no locking.
"""

import asyncio

_views: dict[int, set[asyncio.Queue]] = {}


def subscribe(character_id: int) -> asyncio.Queue:
    queue: asyncio.Queue = asyncio.Queue(maxsize=1)  # one pending "changed" is enough
    _views.setdefault(character_id, set()).add(queue)
    return queue


def unsubscribe(character_id: int, queue: asyncio.Queue) -> None:
    views = _views.get(character_id)
    if views is not None:
        views.discard(queue)
        if not views:
            del _views[character_id]


def _wake(queue: asyncio.Queue) -> None:
    if queue.empty():
        queue.put_nowait(True)


def publish(character_id: int) -> None:
    for queue in _views.get(character_id, ()):
        _wake(queue)


def publish_all() -> None:
    """Every open view: a homebrew item changed, and any character may carry it."""
    for views in _views.values():
        for queue in views:
            _wake(queue)
