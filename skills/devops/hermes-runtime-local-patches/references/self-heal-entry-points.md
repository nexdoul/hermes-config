# Where the on-host self-heal chain enters Hermes

Map of the standalone self-heal system that owns the Hermes install, so a patch roster can be hooked in at the right point instead of inventing a parallel mechanism.

## The three layers (and which one reaches Hermes)

| Layer | Entity | Reaches Hermes? |
|---|---|---|
| 1 (in-sandbox) | `watchdog.sh` via root crontab, every minute | No — `restore-all.sh` explicitly skips Hermes |
| 2a (outside sandbox) | platform-scheduled keepalive/minutely probes | Only if its prompt names Hermes |
| 2b (boot) | `/home/hatch/init.sh` → `restore-all.sh` | No — same skip |
| Hermes's own chain | `hermes-start` + the Hermes self-heal cron | **Yes — this is the only path** |

Guardian deliberately does not manage Hermes: it would download upstream latest and conflict with the pinned-version architecture. Any Hermes self-heal work belongs on the Hermes chain.

## The Hermes chain

- Entry: `hermes-start` (the standalone self-heal script) — runs env detection, version-identity check, missing-item repair, health checks, then gateway start.
- Invoked by the Hermes self-heal cron (every few minutes) and at boot; also idempotent when run by hand.
- Already contains a **manifest pattern** for user data the reinstall cannot preserve — the venv extra-packages manifest. Follow that pattern; do not invent a second one.

## The drift check (what wipes your patches)

`version_identity_check` compares five signals against hardcoded pinned values:

1. `npmVersion` of the installed package
2. `packagedCommit` from the bridge status
3. `runtimeCommit` from the bridge status
4. git HEAD of the runtime checkout
5. runtime marker fields and the `VERSIONS` record

Plus two working-tree signals: `runtimeDirty` / `runtimeModifiedByNativeUpdate`, and non-empty `git status --porcelain`.

`ALLOW_RUNTIME_MODIFICATIONS` existing suspends only the working-tree signals. Any of the five version signals drifting still triggers `restore_pinned_baseline`: `rm -rf $PKG_DIR` + pinned npm reinstall, then re-verify. **Everything not in `$HERMES_HOME` dies there** — the whole dirty runtime tree, including patch work and new tests.

## Classifying persistence before adding any self-heal

`bash ~/.hermes/scripts/persistence-triage.sh` prints a read-only verdict for everything that
needs to survive a restart. Read all four sections; the exit code alone is not the answer.

| Tag | Meaning | Action |
|---|---|---|
| `[P]` | already under `/home/hatch` — survives rebuild | no self-heal, ever |
| `[H]` | dies with the sandbox (process, package, binary, trust store) | must have a named self-heal owner |
| `[M]` | in an ephemeral path but would persist if moved | move it; add no self-heal |
| `[R]` | an existing self-heal whose target does not need healing | delete it, after repointing references |

The `[M]` exception worth internalising: **locks belong in `/tmp`**. A lock that survives a
restart is a permanent wedge — the next self-heal run finds it held and gives up forever. The
same script separates pid files (move them, so they are diagnosable) from locks (leave them).

The `[R]` checks that currently matter on this host:

- `restore-all.sh` still containing `hermes 由用户自有自愈体系管理，guardian 跳过`, and
  `restore-hermes.sh` still disabled. Removing either guard reintroduces a competing
  self-heal that downloads upstream `latest` against the pinned architecture.
- Duplicate launcher scripts with identical md5. Keep the copy a cron job names (check
  `~/.hermes/cron/jobs.json` `script` fields and root crontab); the other is dead weight that
  two future editors will keep in sync by hand.
- Anything copying persistent data into an ephemeral location — the destination is the bug.

## Where to hook a patch roster

Implemented: `apply_runtime_local_patches()` runs in `/home/hatch/bin/hermes-start`, right after the repair phase and before the health checks, so the re-verified tree is the one that gets patched.

- Manifest: `~/.hermes/runtime-local-patches.list` (`bundle|description|reserved`), one line per bundle.
- Per-bundle directory `~/.hermes/patches/<bundle>/` holding generated `*.patch` files, a `files` list of runtime-relative paths, and `meta` with `TARGET_COMMIT`.
- Regenerate everything with `bash ~/.hermes/scripts/runtime-patch-snapshot.sh`; it also sweeps any dirty file not listed in some bundle into `patches/_unassigned/` so nothing is silently lost.
- Apply is idempotent: `git apply --check` first — a patch that is already applied fails `--check` and is skipped as `already/mismatch`, never double-applied.
- A bundle whose `TARGET_COMMIT` no longer matches the runtime HEAD is skipped wholesale (stale context would produce a mixed tree), and the run counts it as `skipped`.
- Apply failures make `hermes-start` exit non-zero rather than continuing with a half-applied roster.

## Verifying a restart actually happened

- `hermes gateway status` says whether the gateway is up; it does not say whether it runs your code.
- Python source edits take effect only after the gateway process restarts. Compare process start time against file mtimes to know which code is live.
- Scheduled restarts: run them through a script the cron prompt names by path only. Prompts containing gateway lifecycle wording get blocked before the job is created.
- Cron timezone: no per-job timezone parameter — convert the desired wall-clock time to UTC in the schedule value itself.

## Long-lived vs disposable

Persists: `$HOME/.hermes` (program, config, skills, sessions, state), `workspace/`, patch roster placed under `$HOME`.
Lost on rebuild: system packages, `/usr/local/bin` binaries, systemd units, root crontab, `/tmp`.
So the roster must live under `/home/hatch`, and the apply logic must be reachable from a script that survives — not from `/tmp`.