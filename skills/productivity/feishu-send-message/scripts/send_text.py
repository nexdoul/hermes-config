#!/usr/bin/env python3
"""Send a text message into a Feishu chat via the lark SDK (typed request).

Usage: send_text.py <chat_id> [text]        (text defaults to "测试")

Prints "OK message_id=<id>" on success; that id is the verification handle.
Credentials come from ~/.hermes/.env and are never printed.
"""
import json
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
        print("usage: send_text.py <chat_id> [text]", file=sys.stderr)
        return 2
    chat_id = sys.argv[1]
    text = sys.argv[2] if len(sys.argv) > 2 else "测试"

    env = load_env()
    client = (lark.Client.builder()
              .app_id(env["FEISHU_APP_ID"])
              .app_secret(env["FEISHU_APP_SECRET"])
              .domain(FEISHU_DOMAIN)
              .log_level(lark.LogLevel.ERROR)
              .build())

    req = (lark.im.v1.CreateMessageRequest.builder()
           .receive_id_type("chat_id")
           .request_body(lark.im.v1.CreateMessageRequestBody.builder()
                         .receive_id(chat_id)
                         .msg_type("text")
                         .content(json.dumps({"text": text}, ensure_ascii=False))
                         .build())
           .build())
    resp = client.im.v1.message.create(req)

    if not resp.success():
        print(f"FAIL code={resp.code} msg={resp.msg}")
        return 1
    mid = resp.data.message_id if resp.data else None
    print(f"OK message_id={mid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
