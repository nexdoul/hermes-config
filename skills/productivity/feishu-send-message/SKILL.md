---
name: feishu-send-message
description: "Use when sending a message into a Feishu chat via OpenAPI."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [feishu, lark, send, message, chat]
    related_skills: [feishu-platform-operations]
---

# Send a message into a Feishu chat via the lark SDK

Hermes itself can post into Feishu chats when it is a participant, but that path goes through the
gateway and its own session state. When you need a **direct, one-shot send** to an arbitrary
`chat_id` — a topic group, a group the gateway is not currently serving, or a test message from a
script — call the OpenAPI yourself with a typed SDK request. This is the action the user asked to
have recorded as a repeatable skill.

## When to Use

- The user gives you a `chat_id` and wants content posted there now ("往 Hermes工作台 发送 X").
- You are driving a Feishu group from a script and do not want gateway turn semantics.
- An outbound Feishu send failed and you must distinguish an auth/scope problem from a routing one.

Not for reading group info or members (`feishu-platform-operations` covers reads and the
`99991672` scope gap), and not for editing Hermes gateway strings.

## Procedure

1. **Confirm the bot can reach the chat.** `grep -c '<chat_id>' ~/.hermes/logs/gateway.log` — a
   non-zero count proves prior inbound/outbound activity, i.e. membership and a working send path.
   Zero means the bot has never been seen there; a send may still work if the app has
   `im:message:send_as_bot`, but expect to report the risk rather than assume success.
2. **Run the recorder script** (`scripts/send_text.py`) with the packaged venv — the only
   interpreter that carries `lark_oapi`:

   ```bash
   ~/.hermes/npm/node_modules/hermes-agent/runtime/hermes-agent/venv/bin/python \
     <skill_dir>/scripts/send_text.py '<chat_id>' '<text>'
   ```

   It prints `OK message_id=<id>` on success. That id is your verification handle.
3. **Verify via a read-back, not by trusting the exit code.** `scripts/list_recent.py` lists the
   last few messages in the chat. Note the asymmetry in step 4 — a gateway-less send leaves no
   `gateway.log` trace, so the SDK response plus a Feishu-side read-back are the evidence.
4. **Report plainly what was sent, where, and that the user can delete it.** Sends into a live
   group are user-visible immediately and the bot has no undelete capability through this script.

## How it works

`send_text.py` reads `FEISHU_APP_ID` / `FEISHU_APP_SECRET` from `~/.hermes/.env` (never from
`config.yaml`, never printed), builds a `lark.Client` with `FEISHU_DOMAIN` imported from
`lark_oapi.core.const`, and issues a **typed** `im.v1.message.create` request with
`receive_id_type=chat_id`, `msg_type=text`, content `{"text": ...}`.

Text-only by design: `send_text.py` deliberately does not handle post/rich/media. If the user asks
for a card, image, or file, build the corresponding `msg_type` explicitly rather than stretching
this script.

## Pitfalls

- **A successful send leaves no `gateway.log` line.** Only sends routed through the Hermes gateway
  are logged there. Absence of a log entry is not evidence of failure — check the returned
  `message_id` and read the chat back.
- **Never `print` the app secret.** The loader strips quotes; keep it that way.
- **Direct HTTPS to `open.feishu.cn` is killed by the sandbox egress proxy**, which surfaces as a
  bare connection close and looks like an outage. Go through the lark SDK, which routes correctly.
- **Do not put this script under the scratch dir.** Entries idle for 24h are pruned; a send script
  that vanishes is a silent capability loss. It lives in this skill.
- **`lark.Client.builder().domain(adapter.FEISHU_DOMAIN)` raises** `domain must be a non-empty https
  URL` — the adapter module does not expose the constant at import time. Import from
  `lark_oapi.core.const`.
- **`resp.success()` is the only real success signal.** A non-typed/raw request comes back with
  `code=None, msg=None` and `b'404 page not found'`, which reads as inconclusive. Always use the
  typed builder.
- **Sending is not idempotent.** Re-running with the same arguments posts a second message. Do not
  retry a send whose result you did not actually read.
