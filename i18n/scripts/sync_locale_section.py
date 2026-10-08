#!/usr/bin/env python3
"""Insert a top-level section from one catalog into the others as English placeholders.

Parity (tests/agent/test_i18n.py) requires every non-English catalog to carry the
same key set as en.yaml. Rather than hand-editing seventeen files, copy the block.

    ./venv/bin/python scripts/sync_locale_section.py --section cron \\
        --source locales/en.yaml --targets 'locales/*.yaml' --skip locales/en.yaml,locales/zh.yaml
"""
from __future__ import annotations

import argparse
import glob
import sys

import yaml


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--section", required=True)
    ap.add_argument("--source", required=True)
    ap.add_argument("--targets", required=True, help="glob, comma list, or single path")
    ap.add_argument("--skip", default="", help="comma-separated paths to leave untouched")
    args = ap.parse_args()

    with open(args.source, encoding="utf-8") as f:
        src = yaml.safe_load(f) or {}
    if args.section not in src:
        print(f"FAIL: {args.source} has no top-level {args.section!r}", file=sys.stderr)
        return 2
    block = {args.section: src[args.section]}

    skip = {s for s in args.skip.split(",") if s}
    paths: list[str] = []
    for pattern in args.targets.split(","):
        pattern = pattern.strip()
        if not pattern:
            continue
        paths.extend(sorted(glob.glob(pattern)) if any(c in pattern for c in "*?[") else [pattern])

    rc = 0
    for path in paths:
        if path in skip:
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception as exc:
            print(f"FAIL {path}: {exc}")
            rc = 1
            continue
        if args.section in data:
            print(f"SKIP {path} (already has {args.section})")
            continue
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n")
            f.write(yaml.safe_dump(block, allow_unicode=True, sort_keys=False, width=100000))
        print(f"INSERTED {args.section} -> {path} ({len(block[args.section])} keys)")
    return rc


if __name__ == "__main__":
    sys.exit(main())
