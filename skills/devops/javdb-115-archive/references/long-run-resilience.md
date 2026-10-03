# Long, unattended runs

For a job the user expects to finish while they sleep: several hours, no human
watching, and a real possibility the host restarts mid-way. The pattern below
is what makes "一次完成" survive that.

## Measure the batch, then slice it

Every driver here costs one network call per item (JavDB detail + title relay),
and most batch writers commit state **after the last item**, not per item. So a
batch's loss window on interruption is the whole batch. Before launching, know
the number:

- items collected
- how long a single item takes
- whether state is flushed per item or per pass

If items x per-item-time is longer than the patience of the environment, slice
off a frozen list (`--names-file` / `--limit`) into batches small enough that
losing one is acceptable. A frozen list also makes the slices deterministic, so
a resumed run reproduces the same batches.

## Chain the jobs, don't hand them off

Two long jobs in sequence (backfill, then ingest) must not depend on a human
noticing the first one ended. Chaining options, best first:

1. One driver script that runs both back to back.
2. Two daemons plus a **marker file** — the second polls for the marker the
   first touches when done. Prefer this when the first driver is already
   running and restarting it would cost its progress.
3. A cron relauncher (below) as the backstop for all of the above.

Never hold the first driver's PID to gate the second: a restart can recycle a
PID to an unrelated process.

## Make every driver idempotent at the top

A relaunched driver must never duplicate work. For the backfill that is
`filter_resumable` (finished items are skipped, so a re-run from the top is
harmless); for ingest it is 115re's own per-movie state. If a driver is not
resumable, do not put it on a relauncher — it will redo finished work on every
wake.

## Restart-proof the chain with a cron relauncher

`setsid` detaches a background job from the session, which is enough for
gateway-level signals but **not** for a container restart. So:

- Start drivers detached (`setsid`, stdio to a file) so a turn interruption
  cannot take them down.
- Add a watchdog cron (every 15m) that checks marker files and relaunches
  whichever driver is missing, with its own rate-limit stamp so a healthy
  chain stays silent.
- Deliver watchdog output locally (`deliver: local`) — a job whose normal
  state is "nothing to do" must not post on every tick.

## Report honestly — progress is not completion

A user who delegated overnight will read only your morning report. Separate
what actually changed on the drive from what is still pending, and name the
cause of any shortfall rather than implying nothing ran. Useful shape:

```
X of N processed.
What actually changed: <concrete file-level evidence>.
Still pending: <count / which jobs>.
Why nothing more: <container restart / still identify-bound>.
Expected to finish: <time>.
```

Evidence must be from the remote listing (or state written after a real
mutation), not from a log tail — a zero-byte log and a killed run look
identical.

## Watchdog script skeleton

```bash
#!/bin/bash
# rate-limit ourselves, then relaunch whichever driver is missing
set -u
NOW=$(date +%s)
if [ -f "$STAMP" ] && [ $((NOW - $(cat "$STAMP"))) -lt 900 ]; then exit 0; fi
echo "$NOW" > "$STAMP"
# both markers present -> exit 0 silently
# driver alive          -> exit 0 silently
# else: setsid bash <driver> >> log 2>&1 < /dev/null &
```

Keep the checks in this order — "done marker", "driver alive", "relaunch" — so a
completed job never relaunches and a mid-flight one is never restarted.

## Scope the watchdog to task intent, never to a fixed marker set

The skeleton's failure mode is a *global* completion gate placed first —
`if [ both known markers exist ]; then exit 0`. That check is correct for the
chains it was written against and silent for everything else, so the day a
third job is added (a retitle, an organizer pass) it has **no watchdog at all**:
the tick still fires, the stamp still advances, and the log still says `nothing
to do`, so the watchdog reads as healthy while the new task sits dead. A
completed job looks exactly like a healthy one.

Drive the watchdog from a registry — one line per task carrying the driver path
and its own completion condition (done marker, or a ledger that says N of N).
The watchdog scans the table and asks *"is there registered work that is not
done?"*, so recovery is independent of which task it is and any new job
inherits the same protection by adding a line:

```bash
# registry: driver_path|done_marker
while IFS='|' read -r driver done; do
  [ -f "$done" ] && continue
  ps -eo args | grep -q "$driver" && continue
  setsid bash "$driver" >> "$LOG" 2>&1 < /dev/null &
done < "$REGISTRY"
```

State the trade-off up front: the watchdog relaunches whatever is unfinished,
so stopping a task *intentionally* means marking it done or removing its line
first — otherwise the next tick reads the stopped task as an interrupted one.

## Guarantee the completion marker structurally, never by convention

A registry whose "done" signal depends on the agent remembering to write it is
not a signal, it is a hope — and the user will refuse permanent auto-relaunch
until it is guaranteed. Make the marker fall out of the architecture instead:

- **One sanctioned entry point.** Every task runs through a wrapper
  (`task-run.sh <id>`) that starts the payload as its own child, so the wrapper
  is the only process positioned to observe the payload's exit code. An agent
  that forgets, crashes, or is killed mid-run produces **no** marker — which is
  exactly the "interrupted, safe to relaunch" case.
- **Ask which way the failure breaks.** A missing-but-should-exist marker
  relaunches work (cheap, idempotent); a present-but-should-not marker kills
  work silently (unrecoverable). Design so absence of evidence always means
  "interrupted": only `exit 0` writes done, never a heuristic or a flag the
  payload sets.
- **Make the terminal states explicit and machine-readable**, not just
  "done": `done` (proved complete), `stopped` (a human intervened),
  `exhausted` (attempts used up). The watchdog checks all three before any
  relaunch, so a deliberate stop and a real completion are equally safe.
- **Store the wrapper's own PGID, not a name.** A container restart leaves
  `state=running` beside a dead pid; reading the recorded pgid from `/proc` is
  what distinguishes "interrupted" from "still going", and it never requires
  matching a command line.
- **Fail closed on every uncertainty.** A lock failure, a malformed count, or a
  missing state file must degrade to *not relaunching*, because the watchdog's
  whole value is that it never invents work.

## Build and test the registry before wiring any live task

Do not register the first real task on an untested watchdog. Write a
real-fixture smoke test (real state dir, real kills, real exit codes) covering:

1. a payload that always fails → exhausts, then the wrapper refuses to start
2. a payload that succeeds → `done`, and a re-run is refused
3. `stop` blocks relaunch, `resume` re-allows it
4. an externally-killed wrapper (state still `running`, pid dead) → the
   watchdog relaunches with a **new** pgid
5. `done` / `stopped` / `exhausted` are never touched again

Three bugs this test caught that reading the scripts did not:

- **A created task must store a shim that execs the original payload, never a
  copy of it.** Copying the content freezes the payload at create time and
  makes `bash run.sh` fail with `126`; a shim means the agent keeps editing the
  original and every relaunch picks up the new version. Write the original path
  to its own `payload_path` file for `show`.
- **`flock -n 9` needs fd 9 opened first.** `flock -n 9` alone prints
  `Bad file descriptor` and the script exits before scanning a single task —
  the watchdog then looks perfectly healthy while relaunching nothing. Open it
  in the same command: `exec 9>"$LOCK"` then `flock -n 9`.
- **Exhaustion is a state, not a retry.** Once written it must survive
  restarts, otherwise a permanently-failing task is relaunched forever and
  burns the provider's rate budget on every tick.
- **A payload can exit 0 having done nothing, and the wrapper cannot tell.**
  The wrapper observes an exit code, not a mutation, so a payload that
  silently degraded to a dry-run (a mistyped flag, a subcommand that ignores
  `--apply`) writes `done` over zero work — the one failure that looks like
  success forever. The payload must therefore hard-fail on its own no-op
  signal: assert the mutation marker it would only produce on a real run
  (`APPLIED` in the output, not `DRY-RUN` / `no mutations were performed`)
  before returning 0, and state the reason in the task log. Re-run the
  payload once under the corrected flags and confirm the marker before wiring
  it to a cron relauncher at all.

## Check the fault is repairable before you let a watchdog heal it

A relauncher automates whatever it finds, so registering a task whose failure
is a **code bug** turns a single failure into a recurring one: every tick
re-triggers the same fault, re-fails every record, and consumes rate budget
until `exhausted` trips. Before wiring a task into auto-relaunch, classify its
actual failures:

1. **Read the ledger, not the log.** Group the failure reasons across the run
   (`collections.Counter(last_error)` over `state.json`'s files). One reason
   covering 99% of records is a systematic fault, not an interruption.
2. **A task interrupted mid-run and a task failing deterministically look
   identical from the outside** — both show "process gone, work incomplete".
   Only the ledger separates them.
3. **Interrupted → safe to relaunch** (idempotent resume). **Deterministic
   failure → fix the bug first**, then register. Otherwise the automation is
   only a faster way to repeat a known error.
4. **Never read "the stack is green" as "the task is fine."** Link-level
   self-heal covers units, tunnels, ports and `whoami`; a per-record software
   fault is invisible to it. Both can be true at once, and that is the
   signature of this class of problem.

## Diagnosing a silent chain: nobody relaunched vs relaunched-then-failed

Split the two before touching anything, because they need opposite fixes:

1. **Is the watchdog even waking?** Read its rate-limit stamp / `.last_healthy`
   mtime, not the log — a silent-healthy watchdog writes nothing when all is
   well, so an empty log proves nothing.
2. **If it is waking, has it gone deaf?** Read its log for a `nothing to do` /
   `all done` line. A watchdog that fires every tick and short-circuits on a
   stale completion gate is the common shape of "nothing restarts itself".
3. **Only if neither holds** is the watchdog itself broken (bad cron, missing
   script, extension misparsed) — check `hermes cron runs <id>` for the real
   exit code rather than assuming.

Confirm what actually died with `ps -eo args | grep <literal>`, never
`pgrep -f` — the pattern in your own check command matches your own shell and
reports a dead task as alive.

After a cron job is created, fire it once by hand (`cronjob(action='run')`)
before trusting the schedule, and read what the run actually did. An `ok`
status on a `no_agent` script job only means the script exited 0 — "silent
(empty output)" is the healthy shape for a job whose normal state is "nothing
to relaunch". Verify by side effects instead: task states in the registry must
be unchanged (no extra attempts, no new pgid, no touched `started_at`), which
is what separates "it ran and found nothing" from "it never ran at all".

A service watchdog and a task watchdog are not the same thing. A 常驻 service is
healthy when its port answers and its process lives; a one-shot task is finished
when it disappears. Same tool, opposite meaning of "process gone", so never
reuse a port-based health check to decide whether a batch job needs relaunching.

## Everything green is not the same as the work being fine

When a user reports "it stopped again every night", expect to find a *layered*
cause, and report the layers rather than the first one you hit:

1. **Who owns relaunching this task at all?** If no entry names it, the honest
   answer is "nothing was responsible", not "self-heal is limited" — and the fix
   is a registry entry, not a bigger watchdog.
2. **Is the link healthy?** `whoami` plus the tunnel proves the stack, never the
   task. A green stack beside a red task is the normal shape and means the fault
   is in the work, not the plumbing.
3. **Is the fault repairable by relaunch?** Group the ledger's failure reasons
   (above). A systematic reason means automation would repeat a known bug.

Do not escalate to a second agent (a container-side helper, a host operator) to
cover a gap that a locally-runnable watchdog already covers — moving the job
elsewhere adds a hop that also cannot see the real state. Keep the recovery
local, and say plainly which of the three layers is actually missing.

Owner rule of thumb: **link-level self-heal owns units, tunnels and ports; the task
relauncher owns workers; the agent owns "is the failure worth relaunching
at all".** Fix in that order and never skip the third.

## Auditing unfinished work, and what is actually running

"Which heartbeat has not finished?" and "something is hitting X in the background" are
two questions, and only the first is answered by the registry. Answer both, because the
user asks the first one while looking at the second.

1. **Take the registry's root from the script that owns it, never from a project note.**
   `grep -n 'TASKS_ROOT' ~/.hermes/scripts/taskctl.sh` prints the path the code actually
   uses; a documented path that was never wired reads as zero tasks, and you report
   "nothing is running" for a registry that is alive somewhere else. Paths in notes drift
   from the code that implements them.
2. **Classify each task by its `state` file, not by whether a process is alive.**
   `pending` / `running` are non-terminal; `done` / `stopped` / `exhausted` are terminal and
   the watchdog never touches them. Report the terminal states plainly — including "none of
   them is unfinished" when that is the answer — and cite the completion evidence
   (`completed_at`, the exit code in the wrapper log) rather than the bare word.
3. **Then answer the traffic question from the process table**, because the registry
   cannot: `ps -eo pid,ppid,etimes,cmd` for the relevant binaries, `ss -tnp` for
   established connections, `/proc/<pid>/fd` for where the daemon's stdout goes.
   **Check the connection list for the target the user actually named before attributing
   anything** — a probe's sockets may go to its own measurement nodes while the route to
   the named site is held open by a tunnel daemon nothing is using, so the honest report is
   "no connection to the target exists; the outbound traffic belongs to X". An
   independently installed service appears in no task registry and no Hermes cron, so
   "nothing unfinished" and "there is traffic" are both true at once.
4. **Identify the owner before naming the process.** `/proc/<pid>/environ` carries
   `SYSTEMD_EXEC_PID`, `INVOCATION_ID` and a `MEMORY_PRESSURE_WATCH` path naming the owning
   `*.service`; the unit file plus its installer log under `workspace/setup/logs/` then say
   what it reports to and at what interval. "A stripped binary is running" is not something
   the user can act on; "an independently installed monitoring probe reports to its operator
   endpoint every 60s" is.
5. **Say which half of the premise was wrong, in one line.** "No heartbeat is unfinished;
   the traffic is an independent probe, not a task" is the report. Do not defend the
   registry, and do not pad with an inventory of every other daemon on the host.
