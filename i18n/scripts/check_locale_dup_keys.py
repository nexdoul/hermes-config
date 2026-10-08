#!/usr/bin/env python3
"""Duplicate-key checker for locale YAML catalogs.

pyyaml silently keeps the LAST value for a duplicated key, so a bulk locale edit
that pastes the same block twice loses translations with no error. This loader
raises instead. Run after every bulk catalog edit:

    ./venv/bin/python scripts/check_locale_dup_keys.py locales/*.yaml
"""
from __future__ import annotations

import sys

import yaml


class _DupCheckLoader(yaml.SafeLoader):
    pass


def _no_dup(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ValueError(f"duplicate key {key!r} at line {key_node.start_mark.line + 1}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_DupCheckLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_dup)


def _flat(path):
    out: dict[str, str] = {}

    def walk(node, prefix):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{prefix}.{k}" if prefix else str(k))
        elif isinstance(node, str):
            out[prefix] = node

    with open(path, encoding="utf-8") as f:
        walk(yaml.load(f, Loader=_DupCheckLoader) or {}, "")
    return out


def main(paths):
    bad = 0
    for p in paths:
        try:
            _flat(p)
            print(f"OK   {p}")
        except Exception as exc:
            print(f"FAIL {p}: {exc}")
            bad = 1
    return bad


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
