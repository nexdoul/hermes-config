# Backfilling and correcting names inside organized directories

The third class of work on this account, after ingest (115re) and organize
(115DailyOrg): **files that already sit in the right directory but carry a
wrong or incomplete name**. Two real shapes:

1. a whole directory named after one actress, so every co-star is missing
   from every file name;
2. files named `演员 番号.ext` with no Chinese title, because a relay
   failure silently collapsed every title to `""`.

Both are fixed by `dailyorg.py retitle`. This file is the procedure and the
gotchas that only apply to it.

## Which entry point

| shape | entry |
|---|---|
| files already in DailyOrg state | `retitle` (state-seeded) |
| directory an earlier non-DailyOrg run filled — **no state at all** | `retitle --registry-dir <dir>` |
| one named directory, control the batch | add `--names-file <frozen list>` and/or `--limit N` |

A registered organized directory is excluded from every normal scan, so the
state-seeded path finds **zero** candidates there. Read it directly instead.

## The pipeline

`retitle` re-uses identify → plan → rename → verify. For a registry-dir run the
candidate carries no `movie_url` and no `release_code`: everything the rename
needs comes from identify. The destination is the directory the file is
already in, so there is **no move and no residue deletion** — only renames.

Concrete form (global option before the subcommand):

```bash
cd /home/hatch/code/javdb/115DailyOrg
$PY dailyorg.py --state-dir /home/hatch/code/javdb/runtime/dailyorg \
  --run-name <run> retitle --registry-dir '/我的视频/<演员>' --apply
```

## Identification gotchas

- **Retry per item, not once per run.** The same film and models returned
  `""` twice and then a correct title on the third call. Bound it
  (`TITLE_ATTEMPTS`, default 4), retry on a *copy* of the record so the
  caller's identity never changes, and record the reason for the final
  failure. A silent empty title is indistinguishable from "no title needed" —
  which is how an entire run once finished with no Chinese titles and no
  error anywhere.
- **Search the base release code when the suffixed form returns nothing.**
  JavDB indexes a movie under its base code, so `q=DLDSS-545-UC` searches
  empty while `q=DLDSS-545` finds it. Fall back to the base code, but keep the
  suffix the file already carries in the name — identification legitimately
  returns the short code and the on-disk suffix is real version information.

## What "already correct" means

- **A file name cannot tell you whether it carries a Chinese title.** The
  actress block is itself Han ideographs, so `江波りゅう AVOP-173.avi` has
  kanji and no title, and a real title only adds more. A shape filter on the
  name drops half the untitled files and re-titles half the titled ones.
  Queue everything and let `plan()` adopt the current name verbatim when the
  identified title is already in it — no rename phase, no churn.
- **Force the rename when the actress set is incomplete, not only when the
  title is.** A name can satisfy the title-less standard check and still be
  wrong about the cast. Gate on
  `not all(a in name for a in identified_actresses)` *in addition to* the
  title check, so completeness is decided by the identified cast rather than
  by whatever the current name happens to contain.
- **The standard name is `全部女演员 中文标题 release_code.ext`.** The title may
  be shortened; the cast and the code are always assembled locally.

## Durability

A single big batch is one loss window. See
`references/long-run-resilience.md` for the slicing, chaining and relauncher
pattern — the short version:

- state is committed **after the whole batch is identified**, so identify is
  the expensive, unrecoverable part; slice off a frozen name list;
- `filter_resumable` skips finished items, so a driver relaunched from the top
  never redoes work — and an item marked `failed` *after* its rename already
  succeeded is still finished for resume purposes;
- run the driver detached (`setsid`) and poll with short sleeps, because a long
  foreground wait that gets killed takes the background child with it.

## Verifying a backfill

- A zero-byte log is the normal shape: one film costs one JavDB detail call
  plus one relay title call and nothing prints until the final summary. Silence
  is not a hang.
- **Diff the listing against the pre-run listing, per `file_id`; do not
  count.** A directory whose first N entries are already renamed looks
  finished — the remaining work sits further down, past the first page.
- **A verify failure on a file that needed no rename is a probe hiccup, not
  lost work.** When the identified cast and title are already in the name,
  `plan()` adopts it verbatim and there is nothing to mutate; the verify that
  follows still reads the drive and can fail on one flaky listing, marking the
  item `failed`. Confirm the name already carried the full cast before
  treating it as a mutation failure.
- Report `unchanged / renamed / missing`, and name the items that cannot be
  renamed at all (no formal release code → no identification → nothing safe to
  rename to) as parked for review rather than failures.
