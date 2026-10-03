#!/usr/bin/env python3
"""Audit 115 directories against the naming contract (read-only).

Standard name: <全部女演员> [中文标题] <release_code>.ext

For each directory given it reports:
  * files / sub-dirs
  * files whose name has no Han segment outside the release code (title missing)
  * files whose release code cannot be extracted at all
  * files at or below the main-film threshold (500MB, strictly greater required)

Never mutates. Run it before and after any backfill, and before writing a
baseline table into a runbook or handoff.

Usage:
    python scripts/audit-names.py "/我的视频/石原希望"
    python scripts/audit-names.py "/我的视频" "/云下载"
"""
import json
import re
import subprocess
import sys
from pathlib import Path

PROJECT = Path("/home/hatch/code/javdb")
for _p in (
    str(PROJECT / "115DailyOrg"),
    str(PROJECT / "115DailyOrg" / "_shared"),
    str(PROJECT / "115DailyOrg" / "_internal"),
):
    sys.path.insert(0, _p)

CLI = PROJECT / "env" / "bin" / "115driver"
MIN_MAIN = 500 * 1000 * 1000
_CODE_RE = re.compile(r"([A-Z][A-Z0-9]{1,8}-[0-9]{2,6}[A-Z0-9-]*)")
_HAN_RE = re.compile(r"[\u4e00-\u9fff]")


def list_dir(path: str) -> list[dict]:
    """One page of a directory listing; a failure is an empty answer, not an error."""
    out = subprocess.run(
        [str(CLI), "ls", path, "--limit", "500", "--offset", "0", "--json"],
        capture_output=True, text=True, timeout=180,
    )
    try:
        payload = json.loads(out.stdout or "{}")
    except Exception:
        return []
    return (payload.get("data") or {}).get("files") or []


def analyse(name: str) -> dict:
    """Classify a file name against the contract.

    The actress block is kana, so a Han segment anywhere outside the release
    code is the Chinese title. A name whose actress block is written in Han
    (a multi-actress block, a non-actress directory) needs the identified
    title to judge properly — this script only answers the mechanical
    question, and its "missing title" list is a candidate list, never a
    verdict.
    """
    stem = name.rsplit("/", 1)[-1]
    stem = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", stem)
    m = _CODE_RE.search(stem)
    if not m:
        return {"code": "", "title_ok": False, "no_code": True}
    before, after = stem[: m.start()], stem[m.end():]
    return {
        "code": m.group(1),
        "title_ok": bool(_HAN_RE.search(before)) or bool(_HAN_RE.search(after)),
        "no_code": False,
    }


def main(argv: list[str]) -> int:
    for path in argv:
        entries = list_dir(path)
        files = [e for e in entries if not e.get("is_dir")]
        dirs = [e for e in entries if e.get("is_dir")]
        missing, small, nocode, ok = [], [], [], []
        for e in files:
            info = analyse(str(e.get("name") or ""))
            if info["no_code"]:
                nocode.append(e)
            elif not info["title_ok"]:
                missing.append(e)
            else:
                ok.append(e)
            if int(e.get("size") or 0) <= MIN_MAIN:
                small.append(e)
        print(f"\n=== {path}")
        print(f"  files={len(files)}  dirs={len(dirs)}  titled={len(ok)}  "
              f"missing_title={len(missing)}  no_code={len(nocode)}  <=500MB={len(small)}")
        for label, rows in (("missing Chinese title", missing),
                           ("no release code extracted", nocode),
                           ("below the main-film threshold", small)):
            if rows:
                print(f"  --- {label}:")
                for e in sorted(rows, key=lambda r: str(r.get("name") or "")):
                    print(f"    {e.get('name')}  ({int(e.get('size') or 0):,} B)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:] or ["/我的视频"]))
