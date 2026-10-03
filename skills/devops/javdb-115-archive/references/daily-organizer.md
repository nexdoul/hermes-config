# Daily organizer (115DailyOrg)

The other class of work on the 115 account: not ingesting magnets, but putting
**files that already exist** where they belong. Runs daily at 05:00 Asia/Shanghai
against `/云下载/**` and `/我的视频/**`.

Contracts: `115DailyOrg/AGENTS.md` (rules), `115DailyOrg/SCHEMA.md` (shared data
model), `115DailyOrg/README.md` (CLI surface). This file is the procedure.

## The fixed pipeline

Nine phases, in this order, never reordered — the safety property depends on it:

    Discover → Identify → Plan → Duplicate Check → Move →
    Rename → Verify → Delete Source Residue → DONE

`PHASE_ORDER` in `_internal/d115_organizer.py` is the list. Blocking states
(`unresolved`, `ambiguous`, `multiple_organized_destinations`, `excluded`)
produce no phases at all: they are parked for review and never mutated.

A duplicate is **not** terminal the way `verified` is — a redundant external copy
still needs verify → delete residue → done, so it keeps its phases.

## Registry

- A directory is organized only because a human registered it:
  `dailyorg.py registry add '<dir>' --actor '<演员>'`, `list`, `remove`.
  Never infer an actor identity from a directory name.
- A registered directory excludes its **whole subtree** from discovery, so files
  already inside it are never candidates. An actor directory produced by a
  confirmed `115re` run must be registered explicitly, not guessed at.
- Trailing slashes normalize away; `has()` is true with or without one.

## Identification

1. Extract the release code locally from the filename. It must cope with
   `HD_MIDV-279.ts`, `MIRD-237-U_X1080X`, spaced-hanzi names, and
   `ホムラ ひな PKTA-010-uncensored-HD` (a source-tag suffix reduces to the base
   code).
2. Then reuse 115re's JavDB layer (`javdb_collector`: exact search → detail parse
   → AI Chinese title). No local code, no exact match, or several equally good
   candidates → `unresolved` / `ambiguous`: reported, and left alone.

Main film is **strictly >500MB**. Standard name is
`<全部女演员> <中文标题> <release_code>.<ext>`; a file already matching it is not
renamed, but is still written to state as `verified`.

## Duplicate check

Strong hash first, then release code **or** base code + identical size. Same
code with a different size is a different release — keep both. The deletion
target is always the *external* copy, never the organized original. Multiple
Multiple registry hits for one movie's cast → `multiple_organized_destinations`, and the
file stays where it is.

## The delete red line

Exactly two things may never be deleted, and both are protected as **directory
names**, never as subtrees:

1. `/我的视频` — the destination root itself.
2. every registered organized directory (`石原希望`, `皆瀬あかり`, `里番`, …) —
   each as the directory node.

Anything under either is ordinary organizer work and must stay approval-free:
a stray film in the destination root, a single file inside an organized
directory, a stale task subdirectory left inside one, an emptied task
directory under `/云下载`. A subtree rule adds no safety here — it blocks the
deletion the residue phase exists to perform.

Enforce it at every exit a deletion can take, and keep the layers independent:

| layer | what refuses |
|---|---|
| `_cli_rm` | the last exit, before the wrapper is invoked |
| `Run.mutate` | single mutation entry point, **ahead of** the dry-run gate |
| `Organizer._is_protected_path` | the residue calculation itself |
| `TestDeleteProtection` | all of the above, per layer |

`is_protected_delete_path(path, protected_dirs)` is the shared exact-directory
check. `_cli_rm` receives the registry names through a module-level hook
(`_PROTECTED_REGISTRY_DIRS`) that `Run` fills at startup, so a direct call to
the helper is protected too — a helper guarding only a hard-coded root refuses
`rm /我的视频` while happily deleting a registered organized directory.

**Put the guard ahead of the dry-run gate.** Behind it, `dry=True` answers
`{"success": True, "dry_run": True}` for the root, which reads as a legitimate
request that was merely skipped.

**Probe each layer on its own.** A guard exercised only through the high-level
entry point hides a gap in the low-level helper: call the helper directly,
assert the result is a refusal, and assert the side-effecting call never fired.

## Residue deletion

The residue is the directory the file was **discovered** in. `parent_path` is
rewritten to the destination by the move phase, so a residue phase that reads
`parent_path` deletes the destination root itself — carry the discovery
directory separately (`source_parent_path`) and check it against the red line
before deleting.

Delete only when nothing main-sized remains: a main video still present →
defer; junk-only or empty → delete. A duplicate is different: the external
copy *is* the residue, so remove the copy itself, not a directory.

A source directory that is already empty still needs the deletion: a move whose
source and destination share a name leaves an empty shell behind, and the
`current_path` check alone does not clear it. Treat "already empty" as deletable
rather than as a reason to skip.

## Running it

Global options come **before** the subcommand, and `--apply` is a **per-subcommand flag honoured only on `apply`/`run`**:

```bash
cd /home/hatch/code/javdb/115DailyOrg
export PYTHONPATH=_shared:_internal:../115re:../115re/_internal:../115pan:../115pan/_internal
$PY dailyorg.py status                            # registry, lock, last run
$PY dailyorg.py --run-name smoke plan            # dry-run: zero mutations
$PY dailyorg.py --run-name daily apply --apply   # real changes (lock-guarded)
```

Write that last form once and reuse it verbatim. `plan --apply` and `apply --resume`
(with `--apply` forgotten) both run dry — the parent config computes
`apply = args.apply and command in ("apply", "run")` — so the log says `DRY-RUN`,
nothing mutates, and a long wait is spent on a no-op.

**Before `--apply`, put the pending items in front of the user as a
`current_path → destination` table**, taken from `state.json` rather than the
log. A count line (`pending 20`) is not a plan anyone can check; the table is,
and this user asks for exactly what will be moved, renamed and deleted before
it happens.

Exit codes: `0` clean, `75` another run holds the lock, `2` failures. One
organizer at a time — the `flock` in `_shared/lock.py` dies with its holder, so
there is no stale lock to clean. A run that dies commits state per item and
resumes from it under the same `--run-name`.

**Check for a live run with `ps -eo args | grep 'python3 dailyorg.py'`.**
`pgrep -f '<run-name>'` matches the pattern inside your own command line and
reports the run as alive forever — and any cleanup built on that pattern can
kill your own shell.

A full real-account scan is a few minutes of directory listing plus one network
call per file; budget for it.

**Report an apply as a split, not a verdict**: `verified / failed / unresolved /
excluded` counts, the mutations performed, which residue directories were
removed, and what is left needing a human. `unresolved` items are by design
parked and reported — they are the operator's to-do list, not a silent skip.

## Smoke checklist (safe against the real account)

- Run `plan` on a scratch `--state-dir`, then assert **zero mutation
  artifacts**: no `attempts.jsonl` created, and no move/rename/delete entries in
  the event journal.
- Point a second smoke at a **copy of the production registry** — a scratch state
  dir starts empty, so registry exclusion silently does not apply and the smoke
  proves only half the behaviour.
- Confirm the lock: a second concurrent run exits `75` and names the holder.
- Confirm atomic-write recovery: plant a stale `.tmp` beside `state.json`, reload
  the document, and require the committed one to be intact — the next write must
  reclaim the path and leave no `.tmp` behind.

## systemd

`systemd/115dailyorg.service` (oneshot, `After=network-online.target
mihomo-local.service 115driver-cnvps-tunnel.service`) plus
`systemd/115dailyorg.timer` (`OnCalendar=*-*-* 05:00:00 Asia/Shanghai`,
`Persistent=true`). `run-daily.sh` is the entry point and **defaults to
dry-run**; `DRY_RUN=0` is what actually reorganizes the account. Verify both
units with `systemd-analyze verify` before enabling the timer.

## Pitfalls

- **`OrganizedRegistry.add()` mutates in memory only.** `save_registry(path,
  registry)` is what persists it. A test that registers a directory and
  forgets to save silently tests an empty registry, so the guard it claims to
  prove was never armed.
- **Do not assert `success is True` on a `dry=False` mutate in a test.** It
  shells out to the real 115 driver. Monkeypatch the command runner and assert
  the call *reached* the wrapper — that is what separates "allowed" from
  "refused".
- **The move phase rewrites `current_path` and `parent_path`.** Update the
  candidate's own path before the rename phase runs, or the rename addresses a
  source path that no longer exists.
- **A delete guard protecting a subtree instead of the exact directory name disables its own work.** Protect the root and each registered directory as names; contents stay deletable, or residue never fires at all.
- **Derive the residue directory list from `source_parent_path`, and expect the destination root to appear in it.** That entry is exactly the accident the red line exists for — reporting it in the plan is the point, not noise to filter out.
- **Do not report remote-account damage from a stale listing.** The remote tree moves between turns — a user can restore a directory, or an earlier run can have completed — so re-list before saying what is missing or which operation removed it, and re-verify the restore against the tree before planning on top of it.
- **Read sizes from the key the schema actually uses before trusting an `--apply` list.** Per-file documents carry `size_bytes`; a reader that asks for `size` prints zero for every row while the data is fine, and an all-zero column then reads as a discover-stage bug that it is not. Dump one row's keys, re-check the threshold story (a genuinely all-zero plan cannot satisfy `>500MB` at all, so its pending/unresolved split is an artifact), and only then suspect discovery.
- **When several source files resolve to one destination name, resolve their hashes before the run.** Identical sha1 → one survivor, the rest are external copies to delete after verification; different sha1 → genuinely different versions, both kept. Never let a rename decide it.
- **Verify must read past the first page, and must never match a directory.** A directory listing is capped (`_LIST_PAGE`, 100), so a moved file can sit past the cut-off — an actor directory with 379 entries hides the film that landed at offset 300 — and the single-page read reports `verify_missing_target` for a file that is plainly there. Page through the remainder (`probe_paged`, which `Run` implements against the wrapper's `--offset`) before declaring it missing. Separately, skip `dir` entries when matching the target **name**: a source directory named exactly like the file (`/我的视频/AVOP-173.avi`, left behind by the move) matches on name and reports size 0, which reads as `verify_size_mismatch`. Both look like planner bugs and are read bugs; both are safe by design (nothing is deleted behind a failed verify), which is exactly why they hide for a whole run. **And drive the page walk from the listing's own `has_more` / `next_offset`, never from "the first page came back full"** — the full paging contract is the next pitfall below; a full first page is not proof of a second one, and an empty page is not an error.
- **A paged listing past the last page returns empty with `success: true` — it is the end of the directory, not a probe failure.** `--limit 100 --offset 100` on a 61-entry directory answers `files: 0` rather than an error. The response already carries `has_more` and `next_offset`, so read them and let the server decide when to stop: `has_more: false` ends the walk even on a full page, `next_offset` is authoritative when present, and only a response that omits both falls back to page fullness (`len(page) < _LIST_PAGE` = last page). Guessing from page fullness instead is what condemned 271 already-correct records while every file sat exactly where the plan said. Propagate the paging answer through **every** read adapter, not just the paged one, and probe the CLI's real pagination with a sweep (`offset=0/100/200/300`, **plus a directory genuinely large enough to have a second page**) before trusting a paging helper — `--help` documenting `--offset` says nothing about what it returns out of range, and a short directory cannot prove real pagination at all.
- **Settle the direction of the fix with a decisive probe before editing code.** Two failure modes looked identical from the ledger — "the offset parameter is broken" versus "one CLI call failed transiently" — and they demand opposite fixes. Run the *exact* argv the failing code path issues (same wrapper, same global flags, same order, `--json` first) against the real account, and sweep the parameter range: `--offset 100/200/300` on the same directory, plus `--limit 1150` as a sanity read. All-`rc=0` with real slices proves the parameter works and the fault was transient, which reclassifies the whole batch from "systematic defect" to "correct data plus a bad error path" — 271 of 271 records suddenly re-verified. Derive the fix from what the probe measured, not from the symptom's name.
- **Re-run the full failing set against the fixed algorithm before calling it repaired.** Re-checking 15 sample records is a smoke, not a proof; read each distinct directory once with a large `--limit` (verified: 1150 returns 379 entries) and apply the fixed logic against that in-memory listing, so the whole set is covered in one read per directory instead of one per file per page. What remains failing afterwards is the real signal — two `size_mismatch` entries that correctly fail closed are the verifier working, not a repair gap.
- **A test that fails after a fix is usually asserting the old contract.** Re-read what the test actually pinned before "fixing the implementation" again: the three failures here were the tests' own fixtures (`next_offset: 0` beside an empty first page breaks immediately) and their expectation of a page-1 read that the fix legitimately removed. Fix the fixture/expectation and say why in the comment, so the test documents the new contract rather than being bent until it passes.
- **Keep a runbook of the ledger's failure vocabulary.** `state.json`'s `last_error` values are the fastest diagnostic this project has — `Counter(last_error)` separates an interruption from a systematic fault in one line, and one reason covering ~99% of records is always the latter. Group it *before* registering any task for auto-relaunch.
- **A read that could not answer is not an answer — keep it its own error.** When a page fetch fails, report `verify_probe_failed` and never collapse it into `verify_missing_target`: one is a transient cloud fault worth retrying, the other is a verdict that the file is gone. Folding them together is what turned one bad CLI call into 272 permanently-failed records.
- **Start the page walk from the listing already in hand; never re-read page 1 through the paged path.** The caller already read the first page, so calling `probe_paged(offset=0)` both wastes a call and lets two adapters disagree about the same directory — the test double agreed with the real adapter on every page *except* 0, and the divergence stayed invisible until a test caught it. Loop from `(entries, 0)` and call the paged reader only to advance.
- **Give the page walk a hard iteration bound.** A `next_offset` that never terminates (or one the server repeats) otherwise spins forever against a rate-limited cloud account. Cap it far above any real directory (`_MAX_VERIFY_PAGES = 2000`) so only a genuine fault can reach it.
- **Make the paged read honour the same field spellings as the first page, `is_dir` included.** The CLI returns `is_dir`; an adapter that maps it to a `dir` key and then reads `dir` makes every directory entry on a later page look like a file, so a same-named directory can "verify" at size 0. Convert both reads in one adapter so one fact cannot carry two shapes inside one phase.
- **Map the paged read in the test fake, not just the first page.** A fake that only implements `probe()` never exercises the pagination loop at all — which is precisely how these bugs survived a green suite. The fake must slice by offset and derive `has_more` / `next_offset` from the slice it actually returned; a fake that hands back the whole directory for any offset hides the very bug the test exists to pin.
- **A batch writer that replaces the document wholesale erases finished work on resume.** `write_files` sets `document["files"]` from the map it is handed, so a resumed run that passes only its own batch leaves the ledger holding just that batch: earlier `verified` items vanish, a later resume redoes them, and a later residue cleanup loses track of what may be deleted. Seed the map from the store and overwrite only the entries this run produced — and assert it with a two-batch test, since a single-batch test cannot see it.
- **Match a finished item on its destination as well as its path.** A moved file has a new `current_path` on the next scan because its discovery path no longer exists, so matching only the recorded path re-queues finished work. The re-queued copy is identified from scratch, a JavDB hiccup marks it `no_results`, and the residue phase is then blocked because residue requires `verified` — one matching bug surfacing as two unrelated symptoms.
- **Check that a regression test fails before the fix.** Revert the one-line change and re-run the test: a test that passes both ways is decoration, not a guard. The multi-pass collision fix and the resume-merge fix both looked correct in isolation and were both still wrong until a run-level test was written.
- **Read a plan out of `state.json`, not the log tail.** The log prints a count line; only the state document carries each file's path, destination, code and actresses. `actresses` is a list of dicts, so join it field-wise, and keep the dump in a script file rather than a `python -c` one-liner (nested quotes in f-strings are not portable there).
- **Back up the whole state dir before clearing a journal, and never clear `state.json` or the registry with it.** A state dir usually holds several files named `.lock` (`state/.lock` plus the run's own), so one flat `cp -a . …` collides on the second; copy the directories separately, rename on the way in, and verify the untouched documents are byte-identical. Then truncate only the journals.
- **Rehearse a ledger reconciliation read-only, forever, before `--apply`.** Any script that rewrites `state.json` takes a mandatory `--apply` flag and prints the full plan (per-record verdicts, counts, the directories it will read) with the default invocation, exiting 0 without writing. The plan line is the contract: if it says `269 -> verified` on the dry run and the apply then writes 271, the two runs read different data and one of them is wrong — re-read the document and reconcile the set that is actually there.
- **Never relabel a record `verified` without re-reading its directory, and never trust a stale one.** The ledger is provenance: a state that was not re-checked against the drive claims a verification nobody performed. Reconciliation scripts read the live listing per directory, with proxy variables stripped from the child environment (`http_proxy`/`https_proxy`/`all_proxy` and their uppercase forms break the local 115 tunnel) and `JAVDB_ENV_ROOT` set, and they only write the fields they can prove.
- **A verified film with an empty `verified_at` and a cleared `last_error` is not a fix — set the timestamp.** Clearing the error field alone leaves a record that looks verified but carries no evidence of when or by what. Stamping it is what makes the restored state auditable later.
