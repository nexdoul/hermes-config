#!/usr/bin/env python3
"""Emit a `tips:` catalog block for the TIPS / COMPOSER_PLACEHOLDERS lists.

The keys are the stable ids from hermes_cli/tips.py (`tip_000` ... `placeholder_00`),
never the sentence itself: a sentence containing quotes, braces or newlines is not
a usable YAML key and breaks placeholder parity.

    ./venv/bin/python scripts/gen_tips_catalog.py                 # print the block
    ./venv/bin/python scripts/gen_tips_catalog.py --emit /tmp/x.yaml
"""
from __future__ import annotations

import argparse
import ast
import sys


def _lists(path):
    tree = ast.parse(open(path, encoding="utf-8").read())
    out: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") in (
            "TIPS", "COMPOSER_PLACEHOLDERS"
        ):
            name = node.targets[0].id
            prefix = "tip" if name == "TIPS" else "placeholder"
            width = 3 if name == "TIPS" else 2
            for i, elt in enumerate(node.value.elts):
                out[f"{prefix}_{i:0{width}d}"] = ast.literal_eval(elt)
    return out


def _dump(entries: dict[str, str]) -> str:
    lines = ["tips:"]
    for key, sentence in entries.items():
        escaped = sentence.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'    {key}: "{escaped}"')
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="hermes_cli/tips.py")
    ap.add_argument("--emit", help="write the block to this file (default stdout)")
    args = ap.parse_args()
    entries = _lists(args.source)
    text = _dump(entries)
    if args.emit:
        with open(args.emit, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"wrote {len(entries)} entries -> {args.emit}")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
