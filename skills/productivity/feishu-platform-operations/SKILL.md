---
name: feishu-platform-operations
description: "Use when operating the Feishu workspace via its OpenAPI."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [feishu, lark, openapi, chat, topics, group]
    related_skills: [hermes-gateway-localization, hermes-integrations]
---

# Operating the Feishu workspace through its OpenAPI

Feishu is the platform this user lives on, so "do X in Feishu" requests arrive often: create or
rename a group, add the bot or a member, inspect a group, post into a topic, list the bot's chats.
The work is mostly knowing three things — the capability boundary, how to authenticate from this
host, and which failure means what.

## When to Use

- The user asks for any change or lookup in a Feishu group, topic, or the bot's own chat list.
- The user asks whether something is possible ("can you create a topic / 话题 in <group>?") —
  answer the capability question **before** writing code or probing endpoints.
- Any task that needs an authenticated Feishu API call from this host.
- A Feishu API call failed and you must tell an app-scope gap from an egress fault from a
  platform capability limit.

Not for localizing Hermes/Feishu strings (use `hermes-gateway-localization`) or for wiring a new
provider or MCP key (use `hermes-integrations`).

## Procedure

1. **Check the capability boundary first.** Fetch the official group overview,
   `https://open.feishu.cn/document/server-docs/group/chat/intro?lang=zh-CN`, which enumerates the
   `chat_mode` values and states which are OpenAPI-creatable. Compare against the known boundaries
   below. If the request lands on a boundary, answer it immediately and hand over the manual step —
   do not spend turns probing endpoints that do not exist.
2. **Build a lark client; never use urllib/requests against `open.feishu.cn`.** Credentials are
   `FEISHU_APP_ID` / `FEISHU_APP_SECRET` in `~/.hermes/.env` (keys only there, never in
   `config.yaml`). Recipe:

   ```python
   import lark_oapi as lark
   from lark_oapi.core.const import FEISHU_DOMAIN

   env = {}
   for line in open('/home/hatch/.hermes/.env', encoding='utf-8'):
       line = line.strip()
       if line and not line.startswith('#') and '=' in line:
           k, v = line.split('=', 1)
           env[k.strip()] = v.strip().strip('"').strip("'")

   client = (lark.Client.builder()
             .app_id(env['FEISHU_APP_ID'])
             .app_secret(env['FEISHU_APP_SECRET'])
             .domain(FEISHU_DOMAIN)
             .log_level(lark.LogLevel.ERROR)
             .build())
   ```

   Run it with the packaged venv — the only interpreter that carries `lark_oapi`:

   ```bash
   ~/.hermes/npm/node_modules/hermes-agent/runtime/hermes-agent/venv/bin/python script.py
   ```

   Never print `app_secret`.
3. **Use a typed SDK request for anything you need to diagnose.** The typed builders give a real
   `.success()`, `.code`, `.msg`, `.data`; the raw `BaseRequest` path does not (see pitfalls).
4. **Confirm the bot is actually in the target group before diagnosing access.**
   `grep -c '<chat_id>' ~/.hermes/logs/gateway.log` — the bot posts and receives in every group it
   serves, so log activity proves membership and moves the fault elsewhere.
5. **Report a scope gap as a grant to request, naming the exact scopes.** The `99991672` error body
   lists the scopes the app lacks and a consent URL; that is an open-platform console action, not a
   code problem.
6. **When the platform cannot do it, say so plainly and offer the reachable alternative.** For a
   topic-group topic that alternative is usually "you create it in the client, then give me the
   `thread_id` so I can route into it" — Hermes can then work inside that topic.

## Per-group behaviour: trigger and admission

Two independent keys under `platforms.feishu.group_rules.<chat_id>` decide what the bot does with a group message, and they must be reasoned about as a pair:

| Key | Question it answers | Consequence of leaving it alone |
|---|---|---|
| `require_mention` (bool) | Does a message need `@bot` before the bot responds? | — |
| `policy` | Who is admitted at all — `open` (anyone in the group) or `allowlist` (only `FEISHU_ALLOWED_USERS` from `~/.hermes/.env`) | Non-`@` messages from senders outside the allowlist are dropped, so "no @ needed" looks broken for everyone but the allowlisted user |

Write both through the CLI so the schema stays correct:

```bash
hermes config set platforms.feishu.group_rules.<chat_id>.require_mention false
hermes config set platforms.feishu.group_rules.<chat_id>.policy open
```

- **There is no "lurk-only" mode.** Clearing `require_mention` makes every message an inbound turn, so the bot answers all of them; the adapter has no "read the chatter, stay quiet" state. When the user asks for visibility without replies, name that boundary and let them pick between "no @, bot answers everything" and "@ required".
- **`policy: open` widens who can drive the bot — proposal order matters.** "Make @ unnecessary for me" is satisfied by `require_mention: false` alone; widen to `open` only when the user actually wants every group member to be able to trigger it, and state which one you applied.
- **A group-rule change needs a gateway restart** — the adapter reads its settings once at startup and nothing watches `config.yaml` for it. Verify the parsed rule offline under the packaged venv first, then hand the restart to whoever owns host operations (see `hermes-runtime-local-patches` for the config-vs-restart proof, the live-turn check, and the in-gateway CLI refusal).

## Known capability boundaries

- **A topic inside a topic group cannot be created through the OpenAPI**, and neither can the
  topic group itself. Official wording: "topic：话题群组。无法通过 OpenAPI 创建，只能在飞书客户端内
  手动创建。" (chat_mode `topic` is client-only; `group` and `p2p` are the other values.)
- What the API *can* do around topics: create/update a chat with `group_message_type: thread`
  (a topic-*form* group, which is `chat_mode: group`), and reply with `reply_in_thread: true`.
- The `im.v1.thread` resource exposes only `forward`. There is no create/update/delete.
- Group-shaped resources in the installed SDK: `chat` (create/get/list/search/update/delete/link),
  `chat_tab` (create/list/update/sort/delete_tabs), `chat_members` (create/get/list/delete), plus
  the message resources.

## Pitfalls

- **Direct HTTPS to `open.feishu.cn` is killed by the sandbox egress proxy** — the connection is
  closed with no response, which looks like an outage or bad credentials. The identical call through
  the lark client succeeds, so route through the client (or the gateway's Feishu adapter) and never
  diagnose a proxy kill as a Feishu problem.
- **The raw `BaseRequest` path does not surface API errors.** A non-existent endpoint comes back as
  `code=None, msg=None` with `raw.content` of `b'404 page not found'`, so an endpoint probe looks
  inconclusive when the endpoint simply is not there. Build a typed SDK request to get a real
  `code`/`msg` before concluding a capability exists or does not.
- **`FEISHU_DOMAIN` is not an attribute of the Feishu adapter module.** The adapter lazy-imports it
  inside a function, so `adapter.FEISHU_DOMAIN` is unset at import time and
  `lark.Client.builder().domain(...)` raises `domain must be a non-empty https URL`. Import it from
  `lark_oapi.core.const`.
- **An app scope gap reads like "the bot cannot see the group".** `im.v1.chat.get` fails with
  `99991672` naming the missing scopes (`im:chat:readonly` / `im:chat` / `im:chat:read`). This app
  currently lacks them, so chat info and member reads fail; send/edit message paths still work.
  Report it as a grant to request rather than a mystery about the group.
- **System `python3` has neither `lark_oapi` nor `httpx`.** A script that imports cleanly there is
  not evidence the gateway-side import works — run it under the packaged venv.
- **A group id from the user is not proof of visibility, and visibility is not proof of a usable
  scope.** Establish both separately (log activity, then a successful typed read) before reporting
  what the bot can or cannot do in that group.
