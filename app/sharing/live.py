import asyncio

_views: dict[int, set[asyncio.Queue]] = {}


def subscribe(character_id: int) -> asyncio.Queue:
    queue: asyncio.Queue = asyncio.Queue(maxsize=1)
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
    for views in _views.values():
        for queue in views:
            _wake(queue)
