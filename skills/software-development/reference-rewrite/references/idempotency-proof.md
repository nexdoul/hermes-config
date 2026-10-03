# Idempotency proof: what a second identical run must show

One successful run proves the pipeline works. The **second** run of the same input from the official entry point is what proves idempotency, and it is the part users ask for explicitly. Collect this evidence from both runs before reporting done.

## Evidence to capture from the re-run

- **Attempt histogram.** The per-action counters (submit / move / rename / delete) must all be zero on the second run. A non-zero counter means a unit was re-processed, whatever the state file claims.
- **Remote identity set.** No new remote task hashes, file ids, or directories appeared. Compare the identity set before and after, not the counts.
- **State file diff.** Every unit either kept its terminal state or advanced; none regressed from done back to pending/submitted. Include the diff in the report.
- **Prior results intact.** The artifacts the first run produced (renamed files, removed task directories) are unchanged — verified by a fresh listing, not by trusting the state file.
- **No duplicate writes.** One move per file id, one rename per file id, one delete per directory id, ever. The append-only attempt log is the source for this; count per-id occurrences.

## How the design makes this possible

- Durable state keyed by a deterministic identity derived from the input, so a re-run recognizes each unit instead of rediscovering it.
- A frozen candidate order in the state, so "primary" means the same magnet on both runs.
- Terminal states that short-circuit the scheduler: a unit already done is read, never mutated.
- Remote state reconciled against the checkpoint at startup, so a restart continues from where the cloud actually is rather than where the local file says.

## Proving the read-only mode is inert

Read-only/plan mode has its own failure mode: a flag greppable in the source but not on every call path, so the "dry" run performs real writes. Prove inertness against the live service before running the real apply, because a dry run that mutates is indistinguishable from a working one until you audit the account.

```bash
# 1. capture the remote identity set (task hashes + file ids + directory ids), not counts
export IDS_BEFORE=$(<provider-cli> list --json | jq -c '[.tasks[].hash, .files[].id] | sort')
# 2. run the dry run twice (second run catches one-shot paths a single run misses)
<entry-point> ... --dry-run
<entry-point> ... --dry-run
# 3. re-capture and diff
export IDS_AFTER=$(<provider-cli> list --json | jq -c '[.tasks[].hash, .files[].id] | sort')
[ "$IDS_BEFORE" = "$IDS_AFTER" ] && echo INERT || echo MUTATED
```

A count comparison is not sufficient here: one task id plus one removed task id nets to the same total. Diff the sets.

What still counts as an acceptable dry-run write: an idempotent `mkdir -p` of the destination, when the provider rejects submissions to a directory that does not exist — document it as the one unconditional write so a later auditor is not surprised by it.

## Reporting it

Quote the numbers, not the adjectives: "second run: submit=0, move=0, rename=0, delete=0; 34 units still `done`; identity set unchanged". If any counter is non-zero, the run is not idempotent — report that as a defect with the offending unit ids, not as a partial success.
