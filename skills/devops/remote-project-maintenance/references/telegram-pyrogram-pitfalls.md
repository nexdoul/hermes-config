# Pyrogram / Telethon traps on a threaded web server

Domain notes for a Python web console (waitress/gunicorn) that drives Telegram from
request handlers. These bite once each and cost hours, so check them before writing
any handler that touches a Telegram client.

## Client construction is loop-bound

- `Client.__init__` calls the deprecated `asyncio.get_event_loop()`. On Python 3.12 a
  worker thread (waitress) has no current loop, so the constructor raises
  "There is no current event loop" even though `asyncio.run()` inside that same thread
  works fine.
- **Rule: build the client inside a coroutine and `asyncio.run` the coroutine.** Never
  `asyncio.run(make_client())` where `make_client` constructs the client itself.

## Uncached peer errors come in three shapes

When a chat id has never been resolved in this session, pyrogram can raise:

- `PeerIdInvalid`
- `ChannelInvalid`
- a plain `ValueError("Peer id invalid: ...")` raised from `get_peer_type`

**Catch all three, or the fallback never runs** — a narrow `except (PeerIdInvalid,
ChannelInvalid)` silently lets the third one escape and the code below it never executes.

## Warming the peer cache

- Scanning `client.get_dialogs()` populates `session.storage`'s peer cache for every chat
  the account can see; that is the reliable fallback for an uncached id.
- **A long-running daemon's session and a fresh session copy are different worlds.** A
  probe that works on a copy may still fail on the daemon, so verify the fallback on the
  path that actually serves traffic — never conclude it is fixed from a side probe.
- When the fallback yields a dialog, mark the cache warm **at yield time**, not when the
  generator is exhausted, or the next lookup still misses.

## Resuming / re-pointing a backup

- Seed a resume checkpoint from the message URL: checkpoint = message_id - 1, so the next
  run starts at the message the user linked.
- **Never delete an old checkpoint when re-pointing a monitor.** Archive it under a
  rollback key (`<old_source>:pre-switch-archive`) so the previous position is recoverable.
- A target-side change keeps the source checkpoint untouched; only a source-side change
  re-seeds it. Encoding that difference wrongly silently re-copies (or skips) history.
