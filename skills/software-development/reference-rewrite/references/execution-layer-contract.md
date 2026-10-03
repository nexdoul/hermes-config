# Execution-layer contract extraction checklist

Run before designing a new layer that talks to an external service (cloud storage, a rate-limited API, a job queue). Each question is answered from the old implementation and its docs, then becomes an invariant your unit tests assert. The answers are project-specific; the questions are not.

## Thresholds and identity

- What is the eligibility threshold, and is the operator strict or inclusive? Declare the constant once and test the exact boundary value.
- What is the durable identity of a unit of work (hash, code, id)? Derive it deterministically from the input so resume keys survive a restart, and test every accepted input format (including alternative encodings of the same identifier).
- How is a name matched against an identifier — substring or boundary? A loose match cross-matches sibling ids; assert the negative case, not just the positive one.
- What file extensions count, and what is excluded? Keep the exclusion list with the threshold so "small file" and "ad file" cannot drift apart.

## Candidate rotation

- What is the ordering of alternatives, and is it recomputed on resume or frozen at first sight? Recomputing can flip which candidate is primary between two runs; freeze the order in durable state when the spec wants stable retries.
- When may an alternative be tried — only after the primary has failed explicitly, or any time? Never rotate while the primary is still in flight.
- What is the cap on attempts per unit before it is declared exhausted?

## Polling and rate limits

- What ceiling does the provider state? Enforce it in a shared lock-protected timestamp file opened by every process, including any helper binary, before a read.
- Which statuses mean "in progress but healthy", "failed", and "done"? Classify by status words first and percentage second — a unit can sit at 100% while the service finalizes it.
- What is the per-batch wait ceiling, and what happens to units that pass it? A timeout is a state, not an exception: it routes the unit to recovery.

## Write policy

- Which operations are reads (bounded-backoff retry allowed) and which are writes (never retried)?
- For batch writes, how do results map back to inputs? Require an exact count plus per-item identity, and refuse the whole batch when they disagree.
- What is the least destructive recovery for a bad unit? Prefer removing the task record while keeping the files, and require the exact identity — never a name or a path — as the argument.
- Which responses are classified as "do not retry" (rate limited, blocked) versus "retryable" (transport)? Replaying a blocked request only adds remote pressure.

## Completion and destruction

- What is the full proof that a unit is finished — moved **and** renamed **and** verified — before any destructive step is allowed?
- What counts as ambiguity that must block the destructive step (unknown entry, mixed result, missing expected name)? Default to keeping the data.
- Is every destructive step re-validated against a fresh listing immediately before it runs, so a plan derived from an old snapshot is refused rather than executed?

## Resume and dry-run semantics

- Which persisted fields let a fresh process reconstruct each unit's position from remote state plus the local checkpoint alone?
- Which calls mutate the external system, and does every one of them check the same read-only flag? List them per module: a flag read once at the entry point does not cover a call reached from a helper, and the dry run then performs real writes.
- What does a dry run legitimately report at the top level? Write it down before you "fix" a failing status you have not understood.
