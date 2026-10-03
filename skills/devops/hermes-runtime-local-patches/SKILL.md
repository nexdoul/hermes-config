---
name: hermes-runtime-local-patches
description: "自愈分析 — persistence triage, then register runtime edits."
version: 1.8.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [hermes, self-heal, patches, runtime, persistence, triage]
    related_skills: [camofox-selfheal-deploy, hermes-config, hermes-agent]
---

# Keep local Hermes runtime patches alive across updates

The installed Hermes runtime (`~/.hermes/npm/node_modules/hermes-agent/runtime/hermes-agent`) is a git checkout pinned to one commit with a dirty working tree. Every local improvement — gateway features, locale work, provider-route fixes, tests — lives as uncommitted modifications that any version bump destroys. This skill registers them so `hermes-start` re-applies them automatically, and tells you when self-heal is the wrong answer.

Guardian does **not** reach Hermes (see `references/self-heal-entry-points.md`); the only self-heal path is `hermes-start` + the Hermes self-heal cron. Do not add Hermes to `restore-all.sh`.

## When to Use

- The user says **"自愈分析"** (or "self-heal analysis") — this is the alias for the whole skill. Run the triage and **finish the entire job in that one turn**: classify, then apply every implied fix (move `[M]`, register unregistered edits, clear `[R]`), then re-run the script to prove it exits 0. Do not stop after the report to ask what to do next.
- You are about to add or review **any** self-heal entry — run the persistence classification first, so you do not heal something that is already permanent.
- You just changed a file under the installed Hermes runtime and need it to survive the next reinstall.
- `hermes-start` reinstalled a baseline and local edits are gone.
- You suspect a self-heal entry is redundant, duplicated, or maintaining something that should just be moved.
- The user asks for a Hermes feature, gateway behaviour, or locale change that config cannot express.
- The user wants behaviour that is **conditional** — active only on a trigger phrase, a mode, or a platform — so it needs a gate, a default-off config section, and a proof that the ungated path is unchanged.
- You are pinning a new baseline version (new `PINNED_UPSTREAM_COMMIT`).
- `hermes-start.log` shows `runtime 本地补丁` WARN/FAILED lines.
- A red test run needs separating "environment cannot run async tests" from "my edit broke something".

Do not use for config-only changes (providers, aliases, reasoning effort) — those live in `~/.hermes/config.yaml` and survive by themselves.

## Alias & Propagation

The trigger word lives in `description` (it must survive the 57-char index-truncation window) and the mandatory behaviour lives in the first bullet of `## When to Use`. Both are required: the index finds the skill, the bullet forces the right action once it is loaded. A bare keyword in the description with no behaviour rule gets loaded and then ignored.

**State the alias scope and let the user pick before wiring it.** "Run this when I say X" can mean read-only diagnosis or diagnose-and-fix. Ask which, then encode the answer in one sentence in the trigger bullet — a future session must not have to re-derive the scope from context.

**Propagation needs no restart and no `/new`.** Edited and newly created skills go live on their own: the index snapshot is invalidated by a per-file signature of `(mtime_ns, size, ino, ctime_ns)` for every `SKILL.md`, `tools/skills_tool.py` re-scans on a 30-second TTL, and each turn rebuilds the system prompt from the fresh snapshot. Tell the user to just start talking, and confirm with `skills_list` — never advise restarting to pick up a skill edit.

If an edit still does not appear, delete the snapshot and let it rebuild:

```bash
rm -f ~/.hermes/.skills_prompt_snapshot.json
```

Writers that preserve mtime and size (`cp -p`, `rsync -t`, tar restores, `os.utime`) can stall the signature check. The snapshot file is the escape hatch; a restart is not.

## Always-on rules

- **Config beats source.** Anything expressible in `~/.hermes/config.yaml` survives reinstalls and needs no roster entry. Patch source only for behaviour config cannot reach.
- **Express approval granularity in config, never in source.** `approvals.mode: smart` plus `approvals.smart_policy` already implements tiered approval (routine commands auto-pass, human card only for catastrophic ones); do not build a new mode for that requirement.
- **Register every runtime edit in the same session that made it.** An unregistered patch is one that silently vanishes on the next reinstall.
- **Never touch guardian.** `restore-all.sh` explicitly skips Hermes by design (guardian downloads official `latest`, conflicting with the pinned architecture). Hermes self-heal work belongs on the Hermes chain only.
- **Hand risky host operations to the container-side agent as a self-contained doc**, not as an instruction to "restart when ready". Hard limits first, then pre-state snapshot commands, the exact procedure, and a concrete verification checklist — the receiver cannot see this conversation. **A gateway restart is the paradigm case:** it drops the Feishu/WhatsApp link the user reaches the agent through, so it goes out as a handoff doc — not as an inline scripted restart you run yourself.
- **Never schedule a restart as a workaround for a bug you introduced.** Restart to apply approved changes or on an explicit user schedule; a restart issued to escape your own bad state is the one case that is never yours to trigger.
- **Never judge patch presence by grep.** Verify with `git apply --check` (applies only when NOT yet applied) and `git apply --reverse --check` (succeeds only when already applied).
- **Restarting the gateway is not restarting the container.** Host restarts belong to the container-side agent and are never yours to trigger. Python source edits always need a gateway restart. **"Config hot-reloads" is not universally true** — platform adapter settings are read once at startup, and believing the blanket version means reporting a change as done while the live adapter still runs the old value. Prove which class your key is in (next bullet) before acting.
- **Prove whether a config key hot-reloads before doing anything intrusive.** Grep the runtime for a config-change hook and for callers of the section's own settings loader: `grep -rn "on_config_change\|config_reload\|CONFIG_CHANGED" gateway/ plugins/ hermes_cli/`, then the loader's callers inside the target plugin. No watcher plus no caller outside startup means the value is read once at boot — `plugins/platforms/*/adapter.py` are in that class (their `_load_settings`/`_apply_settings` have no callers, and `run_plugin_rewire` rewires plugins only, never adapter settings).
- **Verify a config change offline before paying for the restart.** In a separate process, load the real `config.yaml` through the real plugin class with the packaged venv (`runtime/hermes-agent/venv/bin/python`) and assert the parsed settings. A wrong key path is cheap here and expensive through a dropped platform link.
- **Check what a restart would interrupt before requesting one.** Live turn leases are queryable: `sqlite3 ~/.hermes/state.db "SELECT conversation_id, holder, acquired_at, expires_at FROM session_turn_leases WHERE expires_at > strftime('%s','now');"`. A drain-aware restart waits for every live turn — including the one requesting it — so a restart asked for mid-turn will not finish inside that turn.
- **Your own terminal runs inside the gateway process tree, so gateway-management CLI verbs refuse you.** The agent shell carries `_HERMES_GATEWAY=1` and `hermes_cli/gateway.py`'s `_refuse_from_inside_gateway` rejects `gateway start/stop/restart` from there — a self-guard, not a bug. Confirm the lineage (`$$` back through `ps -o pid,ppid,comm`) before concluding the command is broken, then plan the restart as an out-of-band action instead of retrying the verb.
- **Lead work reports with a compact status table** — done / pending / needs-your-decision — and keep the breakdown to a few bullets. A full narration of the investigation trail gets rejected as unreadable; the research detail belongs in the skill and the logs, not in the reply. When the user says a message was too messy to follow, re-cut the SAME content into one table plus at most five bullets — do not answer with more narration or new detail. **Exception — a build or rewrite report is the opposite failure mode:** with many artifacts, a one-word-per-module status reads as opaque rather than compact. Give each artifact its source (copied vs new) and one line of what it enforces, and when the user asks for more detail, add per-artifact substance rather than a longer investigation trail.
- **Confirm how a change takes effect before answering a propagation question.** "When does my edit go live?" is answered from the caching source (snapshot signature, TTL, per-turn prompt rebuild), not from a guess — the honest answer here is "already live, no restart," and advising a restart would be both wrong and costly on this host.

## The Mechanism

All state lives under `~/.hermes/` (never under `$PKG_DIR`, which the reinstall wipes):

| Path | Role |
|---|---|
| `~/.hermes/runtime-local-patches.list` | Bundle registry, `bundle\|description\|reserved` |
| `~/.hermes/patches/<bundle>/files` | One runtime-relative path per line (tracked or untracked) |
| `~/.hermes/patches/<bundle>/*.patch` | Generated unified diffs |
| `~/.hermes/patches/<bundle>/meta` | Holds `TARGET_COMMIT` — the runtime HEAD the patches were made against |
| `~/.hermes/scripts/runtime-patch-snapshot.sh` | Regenerator |
| `apply_runtime_local_patches()` in `/home/hatch/bin/hermes-start` | Auto-apply hook |

`hermes-start` runs the apply hook after any reinstall: it compares each bundle's `TARGET_COMMIT` against the runtime HEAD, and only if they match does it `git apply --check` + `git apply`. This mirrors the `venv-extra-packages.txt` pattern already in the launcher.

## Procedure: Classify Before You Heal (run this on anything new)

Before adding a self-heal entry for anything, decide which of three fates it deserves.
Adding self-heal for something that is already persistent is redundant work that can
actively hurt (a second writer, a version conflict, an operator who thinks it is broken).

Run the triage script and act on its verdict:

```bash
bash ~/.hermes/scripts/persistence-triage.sh   # exits 3 when redundancy is found
```

**When the user says "自愈分析", run it and finish the whole job in one go** — triage,
then apply every fix it implies: move `[M]` items (updating all references), register any
unregistered runtime edit, and clear every `[R]` line. End by re-running the script and
reporting that it exits 0. Do not stop at the report and ask what to do next; the only
permissions needed are the ones the platform already surfaces for destructive commands.

1. **`[P]` permanent — needs no self-heal.** Everything under `/home/hatch` survives a
   rebuild: `~/.hermes` (program, config, skills, plugins, sessions, state, logs, patches),
   `~/workspace/{setup,enhance}`, `~/.cache/camoufox`, `~/.camofox/profiles`, `~/.ssh`.
   *Criterion:* nothing in this class gets a new cron job, a new watchdog section, or a new
   patch bundle. If you find one already exists, it is `[R]`.
2. **`[H]` healable — must be self-healed.** Process state that dies with the sandbox:
   the gateway process, Xvfb, cron daemon + its crontab, system packages (`cron`, `x11vnc`,
   `sshd`), `/usr/local/bin` binaries, NSSDB CA trust, MuseAutoApprove. Each must have a
   named self-heal owner (script + cron, or a `restore-all.sh` section).
   *Criterion:* every `[H]` line lists an owner that actually exists.
3. **`[M]` movable — move it instead of healing it.** Something living in an ephemeral
   location (`/tmp`) that would be permanent if relocated. pid files belong here: moving
   `gateway.pid` to `$HERMES_HOME` makes it diagnosable across restarts instead of
   rebuilding a process to recover a path.
   *Criterion:* mv done, all references updated, and **no** self-heal entry added.
   Exception — **locks stay in `/tmp` on purpose.** A stale persistent lock wedges
   self-heal forever; losing it on restart is exactly the semantics you want. Locks are
   `[P]` by design, not `[M]`.
4. **`[R]` redundant — audit the existing scheme and delete what is not needed.** For
   every self-heal entry already configured, ask: is its target actually ephemeral?
   - Runtime local patches: patch bundles are `[P]`, but the working tree they repair is
     `[H]` → **reasonable, keep**.
   - Guardian managing Hermes: would download upstream `latest` and conflict with the
     pinned architecture → **must stay skipped**. Verify `restore-all.sh` still contains the
     `hermes 由用户自有自愈体系管理，guardian 跳过` guard and that `restore-hermes.sh`
     remains disabled.
   - Duplicate launcher scripts (same md5 in two locations): keep the one a cron job names,
     delete the other — **after repointing every reference to the survivor's absolute path**.
     Grep scripts, cron prompts, and notes for the doomed path before `rm`.
   - Anything that copies persistent data into an ephemeral location: the destination is
     wrong, not the source.
   *Criterion:* script exits 0 (no `[R]` lines), or each `[R]` line has been resolved.

Rules that follow from the classification:

- **Never add self-heal to protect something in `[P]`.** It is already safe; the heal is
  the risk.
- **Never add self-heal as a substitute for moving.** `[M]` + heal means two mechanisms
  maintaining one thing.
- **Config beats source beats heal.** `~/.hermes/config.yaml` is `[P]` by construction,
  so anything expressible there needs no patch and no self-heal at all.

## Procedure: Add a Gated Runtime Behaviour (conditional feature)

Use when the user wants behaviour that applies only under a condition — a trigger phrase, a mode, a
platform — rather than always. This is the pattern that keeps the ungated path untouched.

1. **Look for the existing mechanism before designing one.**
   `search_files(pattern='<capability>', target='content', path=tools/)` and the same under `agent/`, `gateway/`, `hermes_cli/`. Hermes usually already owns a manager, a registry, or a config key, so the elegant answer is usually "wire it, don't build it". Report what you found before proposing architecture — this user expects that check first.
2. **One pure module returns the decision.** A single function
   `(user message, config, session state) -> immutable policy object` exposing gated flags plus a
   short `reason` for logs. Every surface calls it; no surface re-derives the rule from context, and
   no prompt carries it.
3. **Enforce at the blocking points, not in the model's prompt.** Find where the runtime actually
   waits for a human (the clarify reply, the approval reply) and shorten or answer the wait there.
   A prompt block shapes behaviour; only code decides it.
4. **Publish per-turn state through a registry the surfaces already own.** Store the window beside
   the entries it gates so a surface holding only a `session_key` can consult it without the agent
   object, and clear it in the same teardown `/new` uses — otherwise the next turn inherits the gate.
5. **Fail closed on every uncertainty.** A registry read failure, a malformed config value, a
   negative number, or a missing session key must each degrade to the pre-existing behaviour, never
   to the ungated one.
6. **Reuse the existing contract text.** Returning the canonical "use your best judgement" sentinel
   instead of inventing one means no other surface learns a new shape and the model's existing
   handling still fires.
7. **Prove both directions against the real config.** Run a plain message (expect an unchanged
   sentinel / timeout / prompt) and the trigger phrase (expect gated) in one check. A feature that
   fires on every message has correct code and the wrong scope.
8. **Register the changed files and write the config keys in the same session** — see the
   registration procedure, and remember `hermes config set` writes only the keys you name.

See `references/gated-behaviour-seams.md` for the exact hooks and the trap at each one.

## Procedure: Notify One Watched Session Across Sessions

Use when the user mutes every window but one and wants the rest to stay silent except for
milestones. Unlike the gated waits above, nothing blocks and the message must reach a *different*
session than the one that produced it, so the seams and the traps are different.

1. **Hook the turn-end seam that already computes the outcome.** `gateway/run_turn.py` finalises every
   turn through `_run_agent_stamp_heartbeat_terminal`, and `_heartbeat_terminal_suffix` already decides
   completed / waiting / stopped. Add the reminder beside that call instead of writing a second
   completion detector.
2. **Derive "completed" from the field that carries the answer.** The response contract puts the text
   in `final_response`; `failed`/`interrupted` mark its absence. A dict without the answer text is a
   blocked or aborted turn no matter how many truthy flags it carries — classify from that field or a
   stalled turn reads as a milestone.
3. **Claim the watched session, never hardcode a chat id.** The first turn to reach
   `_wire_turn_agent_callbacks` keeps the role for the gateway's life, so the watched window is whichever
   one the user is already sitting in. Add a `gateway.notifications.<key>_override` escape hatch, but
   make a blank override fall through to the claim instead of matching nothing.
4. **Capture routing metadata at claim time.** `_inject_watch_notification` →
   `_build_process_event_source` needs `platform` + `chat_type` + `chat_id`, and `chat_type` is not
   derivable from a session key. Reuse the gateway's own `_parse_session_key` and store the trio
   beside the claim.
5. **Reuse the gateway's injector** (`_inject_watch_notification`) rather than hand-rolling an adapter
   lookup — it already resolves profiles, relay aliasing and push capability.
6. **Let delegation narrow the filter, not widen it.** Under full-trust delegation only completion and
   danger may interrupt; a branch choice the agent resolves itself inside its wait window is exactly
   the silence the mode promised. Confirm the scope with the user before making the filter ambient.
7. **Schedule, never await.** `run_coroutine_threadsafe` onto the gateway loop when reachable,
   `coro.close()` when not, every path fail-silent, and the common case down to two comparisons.
8. **Register and test in the same session** — one test per rule that would fail if the branch were
   inverted (completion fires, plain turn silent, decision fires, decision suppressed under delegation,
   never-notify-the-watched-session, nothing-raises).

See `references/gated-behaviour-seams.md` for the notification seam table and its traps.

## Procedure: Register a New or Changed Runtime Edit

1. **Confirm the file is dirty in the runtime repo.**
   `git -C ~/.hermes/npm/node_modules/hermes-agent/runtime/hermes-agent status --porcelain`
   *Criterion:* the file appears with `M`/`A`/`??`.
2. **Pick a bundle.** Read `~/.hermes/runtime-local-patches.list`. Add the file to an existing bundle if it belongs to the same change (a heartbeat fix touching `gateway/run_turn.py` + `gateway/turn_context.py` + its test is one bundle). Otherwise append `my-change|one-line description|anything` and create `~/.hermes/patches/my-change/files` with the path(s).
   *Criterion:* every dirty path you care about is inside exactly one `files` file.
3. **Regenerate:** `bash ~/.hermes/scripts/runtime-patch-snapshot.sh`
   *Criterion:* ends with `OK: 快照完成` and **no** `WARN: 有 N 个改动未登记` block. That warning means a dirty file is in no bundle — the script auto-files it under `patches/_unassigned/` so nothing is lost, but fix it by adding a path and re-running.
   *Stronger criterion:* count the generated `*.patch` files and compare against the line count across every bundle's `files` — the script `rm -f`s each bundle's patches before regenerating, so a file it fails to export loses its patch with no error and no `_unassigned` entry. Exit code 0 is not sufficient.
4. **Verify idempotence and re-appliability** (the two properties that actually matter):
   ```bash
   RT=~/.hermes/npm/node_modules/hermes-agent/runtime/hermes-agent
   # 4a. nothing should apply now — all changes are already live
   for pf in ~/.hermes/patches/*/*.patch; do \
     git -C "$RT" apply --check "$pf" 2>/dev/null && echo "WOULD-APPLY $pf"; done   # expect empty
   # 4b. hard proof: stash tracked changes, delete the untracked tests,
   #     apply every patch, md5sum-compare against the stash, drop the stash
   # 4c. stronger proof — let the PRODUCTION heal do it: clear the tree
   #     (git checkout -- + rm the untracked tests) and then simply wait for
   #     the self-heal cron to fire (~5 min). Verify with reverse-check plus
   #     the feature's own tests. This exercises the real path instead of a
   #     replay of it, and catches hooks that only exist in your test harness.
   ```
   *Criterion:* `4a` prints nothing; `4b`/`4c` restore every file byte-identical and end with the same dirty-file count you started with.
5. **Clean up any leftover stash** from step 4b — never leave a stash holding live work.

## Procedure: After a Baseline Reinstall

1. Read the tail of `~/.hermes/logs/hermes-start.log`.
2. Expect `runtime 本地补丁：applied=N already|mismatch=M skipped=K failed=0`.
3. If `skipped>0`, a bundle's `TARGET_COMMIT` no longer matches the runtime HEAD. The pinned baseline moved: regenerate patches **on the new commit** with the reinstall already done, then re-run the snapshot script. Never force-apply a stale patch — the context will not line up and you get a half-old/half-new tree.
4. If `failed>0`, `hermes-start` exits non-zero on purpose. Inspect the named patch; `--check` passing while `apply` fails is rare and needs a human look.

## Pitfalls

- **`_unassigned` is a safety net, not a home.** Any dirty file not listed in some bundle's `files` gets auto-patched there and every run WARNs. Register it properly.
- **A bundle's `files` and the roster `.list` take different formats.** `files` is one runtime-relative path per line; `bundle|description|reserved` triples belong only in `runtime-local-patches.list`. The tell is that files you listed correctly also land in `_unassigned`: the triple is parsed as a path, matches nothing, and every file in the bundle loses its patch until `files` is rewritten with bare paths and the snapshot is re-run.
- **An override layer must thread the original value through as its fallback.** Gating a global timeout per-session broke the tests that mock the global getter: returning "no override" as `None` let the caller fall through to a hard-coded default instead of the surface's configured value, so an ungated session reported a different window than before. When you layer a narrower value over a wider one, keep returning the wider one whenever the narrow one is absent.
- **A trigger phrase and a session-wide mode are different scopes — default the mode off.** A feature armed by "when I say X" must not also fire on every ordinary message; a mode that gates all turns makes the trigger redundant and changes behaviour for sessions that never asked. Set the mode to `off` so the phrase alone gates it, then verify both directions against the real config. **When trigger-only versus session-wide is your call, ask before wiring it.** Choosing the session-wide mode silently re-scopes the feature to every conversation, leaves the trigger phrase as dead configuration, and means a second config edit the user has to review to undo it; state the tradeoff in one line and let them choose.
- **`hermes config set` writes only the keys you name.** A new section's remaining keys come from code defaults and never appear in `config.yaml`, which reads as an unfinished implementation. Write every key explicitly, including the safe/false defaults, so the file states the whole contract.
- **Run runtime tests with the packaged venv.** `runtime/hermes-agent/venv/bin/python -m pytest` carries `httpx` and `pytest`; the system interpreter lacks `httpx`, so any test importing `gateway.*` dies at import before a single assertion runs. A standalone library-level module imports cleanly under system python3, which makes that import error look like a bug in your change.
- **A failing assertion can be the test telling you the contract.** When a new test contradicts the
  implementation, find what the runtime actually returns before deciding which side is wrong: here the
  "completed" branch was keyed on absent failure flags, and the real contract carries the answer in
  `final_response`. Guessing the response shape from the flag names is what produced the bug.
- **Do not classify by assumption — classify by running the script.** "It looks like it lives in the workspace" is how a redundant heal gets added; the triage script prints the actual paths.
- **Expect the production heal to race your verification.** Once you clear the tree, the cron-driven `hermes-start` will re-apply the patches within minutes, so a run reporting `applied=0` is not proof of a bug — check `hermes-start.log` for a fresh `applied=N` line before debugging your own code. Conversely, a test that "passes" against a tree the real heal already restored has verified nothing: snapshot the tree state immediately before and after your own run.
- **The triage script is read-only and exits 3 on redundancy.** Exit 3 is not a script failure; it means "cleanup needed". Resolve the `[R]` lines, then re-run to 0.
- **A duplicate launcher is only safe to delete after repointing references.** Grep every script, cron prompt, and note for the old path before `rm`. Hermes cron entries live in `~/.hermes/cron/jobs.json` (fields `script` / `prompt`) and never appear in `crontab -l`. An md5 duplicate group can also collide *by name* with a different-content file — after the `rm`, confirm the md5 of the file the cron actually names is unchanged.
- **A daemon must never inherit the launcher's flock FD.** Anything the launcher backgrounds while holding `exec 9>lock` keeps that lock forever — `setsid cmd ... 8>&- 9>&1 &`, or `flock -o/--close <lock> cmd` when wrapping. The failure is invisible: the leaked lock makes every later run exit 0 with a benign "another run in progress" line, so cron reports `ok` and the log looks active while nothing is healed. Distinct from the stale-lock-file case below — the file is fresh and correct, the *holder* is your own daemon (Xvfb, node server, any helper that started one). Diagnose with `ls -l /proc/*/fd 2>/dev/null | grep <lockfile>` plus `/proc/<pid>/cmdline`, and compare the health marker's mtime against now before trusting any log line.
- **A backstop beats a silent exit.** When `flock -n` fails, identify the holder with `fuser <lockfile>` and judge it: if its cmdline is not the launcher, the lock leaked — steal it and continue rather than exiting 0. Giving up politely turns one transient leak into a permanently dead heal.
- **`fuser` prints every holder PID space-separated.** Iterate them (`for h in $holders`); collapsing the output (`tr -d ' '`) fuses several PIDs into one garbage number whose `/proc/<pid>` cannot be read, so the backstop judges a healthy lock as leaked. If *any* holder's cmdline names the launcher, treat the lock as legitimately busy and exit 0.
- **A backstop that cannot steal the lock must yield, not error.** Ordinary contention (the previous round still finishing) is the common case; exit 0 and let the next cron round retry. Exiting non-zero on a failed steal blocks a perfectly good heal and makes the backstop the bug it was written to fix.
- **Do not move a lock file to a persistent location to make it `[M]`.** A surviving stale lock blocks the very self-heal that owns it. Locks are the one thing `/tmp` is right for.
- **Never pass a command ending in `&` to a synchronous shell runner**, in any language. `&` binds the whole AND-list, so the subshell stays in the foreground waiting on the daemon and the caller blocks forever with **zero output on stdout and stderr** — an unreadable hang, not an error message. In Node use `spawn('setsid', [...], {detached:true, stdio:['ignore','ignore','ignore']})` + `child.unref()`; all-ignore stdio doubles as the inherited-FD close, so the daemon cannot inherit the lock either. Same bug as the FD-leak rule, different idiom — the `9>&-` habit in bash does not protect a dynamic-import script.
- **Score the exit code against the fault you can actually repair.** A self-heal exists to repair its *own* stack; a third party blocking this host's egress IP (a WAF refusal, a revoked credential, a rate-limit wall) is not repaible by any script, so exiting non-zero on it converts a transparent status line into a recurring alert and flattens the real signal. Classify with one cheap probe taken beside the failing one — the same reachable third-party hosts that answer 200 while the blocked one refuses — then report the ownable half as healthy and the blocked half as degraded with a clean exit, leaving the health marker untouched so it keeps meaning "everything was green". See also the cooldown rule below and the javdb-stack instance in `javdb-115-archive`.
- **When a probe costs more than the cron interval, remember its conclusion instead of redoing it.** A probe that takes 3×150s under a 5-minute cron spends a whole round to re-derive the same answer, and an external block cannot lift inside that window. Write a cooldown stamp on confirmed block, have later rounds do one fast probe, and clear the stamp the moment that probe succeeds — recovery is automatic, and no manual stamp cleanup is ever needed.
- **A green cron run proves the script ran, nothing more.** Exit 0 and `ok` status are compatible with a completely dead heal: the script can block, time out, or bail early and still exit 0. Score a round green only when it produced fresh real work — a new smoke-test line, or an advanced health-marker mtime — and read what that line *says*, not just its existence.
- **A self-heal audit that reads only its own registries cannot answer "what is running in the background".** Task registries, cron lists and marker files cover what was registered; an independently installed systemd service (a server monitoring probe, a third-party agent) is in none of them, so "nothing unfinished" and "there is traffic" are simultaneously true. Answer from the process table and `/proc/<pid>/environ` beside the registry read, name the owning unit, and confirm whether the target the user named actually appears in the connection list — audit procedure in `javdb-115-archive`'s `references/long-run-resilience.md`.
- **A red cron alert proves nothing about the current state either.** Hermes dedupes failures into `cron_incidents` (error signature, `state`, `first_seen_at`, `last_seen_at`, `alerted_at`) inside `~/.hermes/cron/executions.db`, and a scheduler restart re-emits `unknown` rows and can re-alert an incident whose `state` is already `resolved` — so an alert can arrive hours after the failure it names, with the target healthy the entire time. Before editing any self-heal script on a reported failure, read the evidence: `sqlite3 ~/.hermes/cron/executions.db "SELECT status,started_at,error FROM executions WHERE job_id='<id>' ORDER BY started_at DESC LIMIT 12;"`, plus `last_status`/`failure_streak` in `~/.hermes/cron/jobs.json` and the per-run status under `~/.hermes/cron/output/<id>/`. When the newest rows are all `completed` and `failure_streak` is 0, the report is stale or replayed — editing the script then is an unbacked change to a working heal, and the honest answer is that nothing needs fixing. The shape of the check is **evidence age**: the last real failure and the consecutive successes since it, weighed against the health marker's mtime.
- **A stale alert can be proven wrong in a later turn — re-check, do not stand on the earlier verdict.** A report judged "replayed, nothing to fix" is itself a snapshot in time; the next report of the same symptom means fresh evidence must be read before repeating it. Re-run the same queries and compare timestamps: if new `failed` rows exist since the previous verdict, the alert was real and the earlier conclusion was false. State the changed reading plainly instead of defending the first one.
- **A verification script reporting success while the thing it verifies is failing means the two inspect different targets.** Self-heal verifying `probe-profile` CA trust with `certutil` while the browser runs on a different profile is the canonical case: the check must target what the live process actually uses (`ps -eo args`), not the path handed to the library. When a health check and the real workload disagree, resolve the disagreement first — the disagreement is the finding.
- **A library that accepts a parameter does not necessarily use it.** `firefox.launchPersistentContext(dir, opts)` from camoufox-js starts Firefox on a fresh `playwright_firefoxdev_profile-*` under `~/.hermes/cache/scratch` and ignores `dir` entirely, so every pre-flight fix applied to `dir` is a no-op. Resolve the real target from the running process and apply the fix there, immediately after launch and before the first navigation.
- **Any self-heal fix must be idempotent before it can be wired in**, because the cron fires repeatedly against state that may already be correct. Gate on a read of the current value (cert fingerprint + trust flags, a symlink target, a config value) and exit 0 doing nothing when it is already right; otherwise the repeated fix accumulates duplicates, flaps between states, or fails on the second run for a reason the first run created.
- **Recovery that follows a change in time is not evidence the change caused it.** When a smoke test fails while the CA file, fingerprint, and trust flags all verify correct, suspect a transient (proxy/TLS moment) before suspecting the artifact. Before replacing anything, reproduce the failure with that artifact alone in isolation; if the supposedly-corrupt artifact then passes, it was never corrupt and your remediation was coincidental. Vary one axis at a time — original probe × fresh state, then original artifact × fresh probe — to separate "broken artifact" from "broken moment". Never add automatic rebuild/replacement to a self-heal loop for an artifact you have not shown to fail in isolation: it wipes diagnostic evidence on every transient, adds a new failure mode, and books a fix that never happened. Report an unconfirmed diagnosis as a hypothesis plus the next discriminating check, never as a repair.
- **cron's environment is not yours — `HOME=/root` on this host.** A self-heal that passes when run by hand can fail under cron because toolchains resolve binaries and caches through `$HOME` (a browser launcher looks for `$HOME/.cache/camoufox`). When a cron round reports an error your manual run does not, reproduce under the cron environment (`env -i HOME=/root PATH=... <cmd>`) and check whether the resulting error class even matches the original — a different symptom means you reproduced an environment gap, not the bug, and must keep looking.
- **Assert self-heal evidence on content, never on HTTP status.** A cached `304` is a successful probe; scoring `status == 200` as the pass condition marks healthy runs as failures. Require a real page title/body plus zero error markers instead.
- **Verify persistence with a multi-round restart loop, not a single pass.** Repeatedly kill the daemon *and* delete its `/tmp` lock, re-run self-heal each round, and require every round to yield a fresh smoke-test line. One clean pass hides the bugs that only appear on repeat: contention between overlapping rounds, the backstop misfiring, a lock-stealing race. A single pass is what produced two false "self-heal fixed" reports in a row on this stack.
- **"Process alive" is not "task alive".** A watchdog whose only liveness test is `pgrep` scores a driver that is hanging on a child as healthy, so the task sits dead while every log line says ok. Measure the work's own progress (the log file the worker writes to as it advances, mtime-based) and treat a generous silence — longer than one legitimate unit of work — as a stall to be killed and relaunched. Killing is safe only because the worker is idempotent at the top; confirm that before adding the STALL branch.
- **A throttle inside a script must be shorter than the cron that calls it.** A 15-minute stamp under a 15-minute cron doubles the recovery latency to 30 minutes, so the guard the author added for "manual/concurrent runs" becomes the reason a restart recovery is slow. Size the internal throttle against the caller's interval and comment which interval it is smaller than.
- **A long-running task needs its own relaunch owner, and a healthy-looking stack is not one.** Chain-level self-heal (the parts a stack check covers: units, proxies, tunnels, ports) never restarts the worker. When a task survives as an on-disk checkpoint plus idempotent workers, add a watchdog that owns those workers, and wire it into BOTH the host-level launcher and a cron entry so neither scheduler being down loses the task.
- **A relaunch owner for *tasks* is a different artifact from a stack self-heal script, and it needs a completion guarantee before it may be permanent.** A stack heal asks "is the service up?"; a task relauncher must ask "did the work finish?" — and that answer cannot rest on the agent remembering to write a marker, or the user is right to refuse auto-relaunch. Build it as a registry of tasks, each run through one wrapper that observes the payload's exit code and writes `done` itself, with `stopped`/`exhausted` also terminal, and prove all five terminal-state behaviours with a real-fixture test (real state dir, real kills, real exit codes) **before** registering any live task. Then gate the wiring on the fault being repairable: group the run ledger's failure reasons, and if one reason covers ~all records the fault is a code bug that a relauncher will only repeat — fix it first. See the `long-run-resilience.md` reference in the **`javdb-115-archive`** skill for the registry pattern, the five-case smoke test, and the three bugs it caught (`flock -n 9` on an unopened fd silently disabling the whole scan; a created task storing a copy of the payload instead of a shim; exhaustion written as a retry instead of a surviving state).
- **Kill by PID, never by inline pattern match.** `pkill -f '<cmdline pattern>'` matches the checking shell itself when the pattern appears in the command or in a script you just wrote — it SIGTERMs the agent mid-verification. Read PIDs with `pgrep -x <exact name>` and confirm each with `/proc/<pid>/cmdline`, from a script file, before killing.
- **`git status --porcelain` has a two-column status code.** Parsing `${line#?}` keeps the trailing status char and silently breaks assignment matching. Strip the first **two** characters, then one space, then the path.
- **Dedupe by content, not by path.** Comparing `readlink -f` paths makes identical files in two locations look distinct; dedupe on md5 and report each duplicate group once.
- **Patches are commit-specific.** A bundle recorded against one commit will not apply to another, and that is correct — regenerating on the new commit is the fix.
- **The snapshot script briefly `add -N`s untracked files** to make git emit new-file diffs, then `reset`s them. Do not run it concurrently with other git operations in the runtime tree; it is not re-entrant. The self-heal cron runs `hermes-start` against the same tree every few minutes, so a snapshot that ends `OK` with a WARN but no visible WARN body is that race, not a registration gap — re-run the snapshot and re-count the patches.
- **`grep`/text echo is not evidence a patch landed.** When writing files through muse write/exec, the transport can swallow a space in a `" ]` sequence (bash `[ ... ]` tests then fail with `missing ']'`) and can also drop a `$(...)` inside double quotes, leaving dead text that surfaces as `_real: command not found`. Confirm with `bash -n` **and** a real run — a visual read of the written file is not proof.
- **The `ALLOW_RUNTIME_MODIFICATIONS` sentinel only suppresses the dirty-working-tree branch** of the drift check. A real version change (npm version, packaged/runtime commit, git HEAD, marker, VERSIONS record) still triggers the full reinstall — patches and all.
- **Operator approval policy outranks the guardian's built-in default.** `approvals.smart_policy` is appended to the guardian system prompt as TRUSTED text, so one line like "when uncertain, approve" disables escalation wholesale and every flagged command is auto-approved. Write policy as explicit escalate/approve rules and let uncertainty fall through to the default — an approval card that "will not pop" is usually permissive policy, not a code bug.
- **Never prove a gateway-side change from a terminal tool call.** Locally issued commands skip the gateway approval flow entirely, so the surface you are verifying (approval cards, busy ack, wait notices) never renders for the user and the click resolves to zero approvals. Have the user send the triggering instruction as a chat message, then run the tool call inside that turn; that is the only path that renders the card.
- **Do not `pip install` to fix a suite** then report it as a green baseline; the bridge venv lacks `pytest-asyncio` and pre-existing async tests fail for environmental reasons.
- **Locale strings are the one place a patch can be partially on disk.** Bulk YAML edits create duplicate nested blocks, so run a duplicate-key check after any bulk edit.
- **Stale `__pycache__` can shadow fresh source in odd cases; the launcher already removes `__pycache__` after applying patches — do not add bytecode dirs to a `files` list.
- **A scraping pipeline that reports zero results is not a transport failure — check for an age/consent gate first.** A site returning an interstitial ("您已年滿 18 歲嗎？") yields a valid-looking full-body page, so byte counts and HTTP 200 say success while the parser legitimately finds nothing. Distinguish it by searching the fetched body for a page-specific marker (here `/v/` detail links) alongside the gate text, then set the cookie (`Cookie: over18=1`, from the gate's own `respond=1` link) rather than changing proxies or reader code.
- **urllib's opener can short-read a chunked response where `http.client` does not.** Same URL, same headers: `response.read()` raising `IncompleteRead` at 4KB~15KB while `http.client.HTTPSConnection` + `read1(8192)` cleanly returns the full 74KB. `IncompleteRead` is an `HTTPException`, not an `OSError`, so broad `except OSError` retry loops do not catch it and it escapes as a pipeline fault. When a reader fails mid-body, retry with `http.client` before blaming the server, the proxy, or compression.
- **A state machine that terminates a wait loop wrongly makes a completed task look timed out.** A "WAIT_STATES"/"ACTIVE_STATES" set that still contains post-wait states (e.g. READY, POSTPROCESSING) keeps a finished item active forever: the loop re-polls it, hits its deadline and marks it failed, and a re-run then re-enters recovery for a record that already succeeded. Classify states by *what the waiter is waiting on*, not by "not terminal", and keep post-processing states out of the wait-set.
- **A dry-run must be enforced inside the mutation layer's caller, not by omitting a flag.** A read-only plan path that still reaches the submit call performs real writes; and a dry-run that returns *before* binding task hashes leaves every record in PENDING so the selection loop re-selects them forever and the run never terminates. Gate every mutating call on the apply flag, and in dry-run advance the state as if it had run (then log `outcome=dry_run`) so the loop converges and the plan is still produced.
- **A provider precondition failure can look like a masked "0 processed" summary.** Submitting to a destination that does not yet exist is rejected by the provider (`Save directory not found`); the run reported `total=0 resolved=0` with no error line because an exception path emitted a summary lacking the real keys. Fix the precondition (create the target unconditionally when it is idempotent), and make the fallback summary carry the true pending codes plus the real error reason — a zero-count report must never be a stand-in for a failure.
- **`resolved: 0` in a summary line is not "nothing to do" — read the per-record ledger before believing it.** A batch that submitted every magnet and then aborted reported `resolved=0 failed=0`, which reads as a clean no-op; the real state was 20/20 submitted with 19 already downloaded provider-side. `resolved` counts records the runner itself post-processed, so an early batch abort leaves it at zero while the remote work is already done. Read the per-record ledger (`attempts.jsonl`: `action`, `outcome`, `reason`) and reconcile against the provider's own task list before concluding anything from a zero-count summary.
- **Do not accept a state machine's own label as the root cause.** `WAF_COOLDOWN` was the phase name on a batch whose every record failed with `invalid_response` at the protocol layer — the actual cause was a submit failure, not rate limiting, and the label aimed every later check at the wrong layer. When the machinery supplies its own explanation, verify it against the raw error records first.
- **A retry helper that re-raises below its tolerance defeats the tolerance.** Catching a transport error, counting it, and then `raise`ing when the count is still under the limit means the first transient fault aborts the caller anyway. A retry/backoff helper must either swallow and retry up to the limit or return a sentinel (`None`) the caller understands, never re-raise before the limit is reached; and reset the counter on success so tolerance measures *consecutive* failures.
- **A run-directory slug that strips every non-ASCII character collapses all CJK names onto each other.** A `safe_slug` built as `re.sub(r"[^A-Za-z0-9_.-]+", "-", ...)` maps every Chinese run name to the same `run` directory, so two actors' runs silently overwrite one another's state. Preserve non-ASCII (only replace the genuinely illegal path characters and `/`), and confirm the fix by running twice under two CJK names and checking they land in different directories.
- **`--json` changes a CLI's interactive safety prompt into a hard refusal.** `115driver rm <dir>` needs an explicit `--force` when `--json` is passed; without it the command fails with `directory delete requires --force`, which read exactly like the proxy outage that was happening at the same moment. When a wrapper's write fails, check for a missing mode flag before diagnosing the network — and re-run the failing step on its own rather than judging it from a piped `tail`, whose exit code belongs to the last command in the pipe.
- **When a scratch/recovery step fails mid-way, re-read the remote state instead of re-running the whole script.** A recovery that died between its move and its delete leaves the source holding only residue, so a second full run now sees "no eligible asset" and stops at a manual-review branch. Give the script an explicit resume branch keyed on the *outcome* (asset already at the destination) rather than only on its input (asset still at the source), and let each destructive step re-verify the earlier ones before it fires.
- **When editing a `try/except` inside an `if/else` in a shared file, re-check the tail indentation before compiling.** Moving the success path into an `else` easily swallows the trailing `self.sleep(...)` into that block; the lint error names the line, but the fix is to re-read the surrounding 20 lines rather than patch the reported line alone.

## Procedure: Resume After an Interruption

The host restarts on its own schedule and a turn can be cut mid-command. Re-running history re-creates
side effects that already happened; assuming the work was lost re-does finished work. Prove what
survived first.

1. **Compile the changed set.** `py_compile` every file the interrupted work touched — a clean compile
   plus an unchanged dirty-file count means the edits are intact.
2. **Re-read the config the work depends on.** `hermes config get <section>` should still show the
   values you set. `~/.hermes/config.yaml` is `[P]`, so a missing key means the write never landed,
   not that the restart ate it.
3. **Resume only the unfinished step,** and state plainly that the interrupted command was not re-run.

## Verification

- `bash ~/.hermes/scripts/persistence-triage.sh` exits **0** (no `[R]` lines) — and you actually read the `[P]` / `[M]` / `[H]` lists, not just the exit code.
- Every `[H]` line's named self-heal owner exists and is enabled.
- The heal path was exercised **through cron**, not by a manual launcher run: trigger with `hermes cron run <id>`, then let at least two scheduled cycles fire and confirm the health marker's mtime advanced each cycle. cron differs in cwd, FD table, and environment, so one passing manual run is not evidence. Deliberately break each dependency (kill the daemon, delete its state dir, remove a symlink it needs) and re-run the whole check — a pass while the cron path is lock-starved is a false pass.
- Each restart round actually did the work — fresh smoke-test log line or advanced marker mtime, not just exit 0. Kill-and-heal was repeated across several rounds, and no round produced a spurious backstop or "another run in progress" line.
- Every `[M]` item is either moved (references updated, no heal added) or documented as a deliberate `/tmp` lock.
- `bash ~/.hermes/scripts/runtime-patch-snapshot.sh` ends `OK: 快照完成` with zero WARN.
- `~/.hermes/patches/*/meta` each carry a current `TARGET_COMMIT`.
- Full drop-and-restore test restores all files byte-identical, dirty count unchanged.
- `tail ~/.hermes/logs/hermes-start.log` shows a runtime-patch line with `failed=0`.
- The feature itself still works (run its own tests, not just the patch check).
- A directory-wide pytest run can be killed by the tool's own timeout and proves nothing either way. Enumerate the files that touch your seams (`ls tests/gateway/ | grep -iE '<seam>'`), then run that named set in one bounded call.
- A change that only manifests on the gateway/session path was verified **through that path**, not by replaying it — a terminal-side reproduction proves nothing about what the user sees.

See `references/self-heal-entry-points.md` for the on-host self-heal map, the drift check, and why guardian is deliberately excluded.
See `references/gated-behaviour-seams.md` for the hooks and traps when adding a conditional behaviour to the
runtime, including the proactive cross-session reminder seam.
