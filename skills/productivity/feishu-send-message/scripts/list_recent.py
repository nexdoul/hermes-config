#!/usr/bin/env python3
"""Read back the most recent messages in a Feishu chat (read-only).

Usage: list_recent.py <chat_id> [page_size]

A send made outside the gateway leaves no gateway.log trace, so this is the
evidence that a message actually landed.
"""
import sys

import lark_oapi as lark
from lark_oapi.core.const import FEISHU_DOMAIN

ENV_PATH = "/home/hatch/.hermes/.env"


def load_env() -> dict:
    env = {}
    for line in open(ENV_PATH, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: list_recent.py <chat_id> [page_size]", file=sys.stderr)
        return 2
    chat_id = sys.argv[1]
    size = int(sys.argv[2]) if len(sys.argv) > 2 else 5

    env = load_env()
    client = (lark.Client.builder()
              .app_id(env["FEISHU_APP_ID"])
              .app_secret(env["FEISHU_APP_SECRET"])
              .domain(FEISHU_DOMAIN)
              .log_level(lark.LogLevel.ERROR)
              .build())

    req = (lark.im.v1.ListMessageRequest.builder()
           .container_id_type("chat")
           .container_id(chat_id)
           .page_size(size)
           .build())
    resp = client.im.v1.message.list(req)
    if not resp.success():
        print(f"FAIL code={resp.code} msg={resp.msg}")
        return 1
    for m in (resp.data.items or []):
        sender = getattr(m.sender, "id", "?") if m.sender else "?"
        stype = getattr(m.sender, "sender_type", "?") if m.sender else "?"
        body = getattr(m.body, "content", None) if m.body else None
        print(f"  {m.create_time}  {m.message_id}  from={sender} ({stype})  "
              f"type={m.msg_type}  body={str(body)[:120]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
