"""Shared chat primitives for the turn modules. chat.py owns message storage; the turn modules only need these two entry points.
Resolved lazily so chat.py can import the turn modules without an import cycle."""


async def emit_final(ctx, text: str, credits, extra: dict):
    from chat import _emit_final
    async for ev in _emit_final(ctx, text, credits, extra):
        yield ev


async def latest_media(cid: str, kind: str):
    from chat import _latest_media
    return await _latest_media(cid, kind)
