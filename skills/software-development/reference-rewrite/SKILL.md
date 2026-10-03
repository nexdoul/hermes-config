---
name: reference-rewrite
description: "Use when rewriting one layer of an existing system."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [rewrite, reimplementation, reuse, idempotency, e2e, reporting]
    related_skills: [cross-surface-feature-engineering, simplify-code, systematic-debugging]
---

# Reference rewrite: keep the verified behaviour, redesign the broken layer

The user asks to 重做 / 重新设计并实现 a component into a **new** directory while keeping the proven business rules — "参考重写，不要继续修补现有实现". The deliverable is a new layer that satisfies the same contract, proven by one unattended real end-to-end run **plus** a second identical run that changes nothing.

## When to Use

- The user names a new project or directory for a component that already exists, and says not to copy the old architecture.
- A subsystem has accumulated patch-on-patch until the architecture itself is the defect.
- You must extract proven behaviour from an existing implementation (code + docs + tests + run logs) and rebuild the failing layer around it.

Not for single-file refactors, or for greenfield builds with nothing to extract from.

## Always-on rules

- **Reuse only what is provider-neutral, and prove it per module.** Source-side modules (fetch, parse, rank, filter, normalize) are reusable; the layer that talks to the external system is where the defects live, so redesign it and reuse none of it. Copy a module only after reading it end to end and confirming nothing in it references the old orchestration.
- **The contract lives in the docs, the tests, and the runtime logs.** Read the project's own contract doc first, then the code in dependency order, then the tests (the executable spec), then the newest run logs (real failure modes the code never anticipated). Recon happens before design, never in parallel with it.
- **Write the extracted invariants down before writing code** — thresholds and whether the operator is strict or inclusive, name composition rules, candidate ordering, state names and transitions, what counts as done. The new layer must satisfy them even though none of the code is copied.
- **One atomic state document plus append-only logs.** tmp-write → fsync → rename for the state; one JSON line per transition (unit, action, outcome, ids) for the history. That is what makes restart-resume and re-run idempotency *checkable* instead of claimed.
- **Reads may retry; writes never may.** Resolve an ambiguous write with a fresh read of remote state, never a replay. Validate every multi-item response against its inputs (count and per-item identity) and fail closed on mismatch rather than binding the wrong entity.
- **Enforce any provider-stated polling ceiling in a shared cross-process gate** — a lock-protected timestamp file every process opens before reading. Enforcing it in one process's memory lets independent code paths silently double the rate.
- **E2E means twice.** One unattended real run, then the same input again from the official entry point; the second run must show no duplicate submission/move/rename and no damage to the first run's results. Only that pair with zero manual intervention counts as done, and the logs of both runs are the evidence you keep.
- **Prove the dry run is inert against the live service, not by reading the code.** An apply guard grepped out of the source is not evidence — some call path reaches the mutation without it. Run the dry run twice and diff the remote identity set (task hashes, file ids, directory ids) before and after; unchanged means read-only, a new identity means the flag is being ignored on one path.
- **Report per artifact** (see below).

## Procedure

1. **Recon.** Read the old contract doc, then modules in dependency order (pure rules → state → transport → orchestration → CLI), then the tests, then the newest logs. Keep a running list of invariants and of "verified" vs "assumed".
2. **Inventory.** `wc -l` plus the def/class list per module; mark each as *reusable / reusable-with-edits / redesign* with the reason.
3. **Scaffold the new tree.** Copy only the reusable modules, and do **not** copy the old entry point — the new orchestration gets wired deliberately or not at all.
4. **Build in dependency order**, lowest layer first: core rules (no network, no I/O) → durable state → client → postprocess planner → scheduler → extra services (titles) → CLI. After each module: compile, import, and exercise the pieces you just wrote.
5. **Unit-test the extracted invariants** with fixtures you build yourself (threshold operator, identity matching, candidate ordering, state transitions). Do not ask permission for harmless synthetic fixtures.
6. **Run the real E2E unattended in the background** — long runs exceed foreground tool timeouts and get killed; send stdout to a file you can quote from. If the background launcher rejects the completion-notification argument, drop it and poll the session id yourself rather than retrying the same call: a silently-started run you can poll is better than no run. **Bound the run by a deterministic unit, never by a count off the head of a list:** the first N cards of a listing are the most likely to be ineligible (no candidate, excluded, filtered out), so a small count can yield zero work and exit "source empty" for reasons that have nothing to do with your code. If the old entry point has no single-unit mode, add one in the new CLI — a bounded E2E needs a known-good unit you can name.
7. **Re-run the same input from the entry point.** Prove idempotency from evidence: attempt histogram all zero on the second run, no new remote task hashes, no second move/rename, prior results intact.
8. **Report** with the per-artifact table plus an explicit list of what remains and the next concrete step.

## Reporting progress on a rewrite

A one-word status per module (`✅ 完成`) reads as compact but tells the user nothing about what the module enforces, and the reply comes back as "详细一点". For every artifact give: **source** (copied from X / newly written), **one line of what it enforces**, and its state; then the not-started list with the next concrete step. Cut the investigation trail, never the per-artifact substance.

When the user then asks to see the full execution chain, answer with a **stage-by-stage walkthrough in data-flow order** — each stage's module and line anchors, its concrete inputs and outputs, the exit-code table, and the values from the verified run. This is not a re-cut of the status table: detail that was noise in a progress report is the whole deliverable here, and the chat answer must stand alone rather than pointing at the artifact doc.

## Pitfalls

- **Passing a compile check is not verification.** `py_compile` catches syntax only: undefined names, calls to a subcommand on the wrong binary, and wrong argument shapes all survive it. Import the module and exercise the new class or method (construct the error, call the helper, feed it a fake payload) before calling the file done.
- **Confirm which binary owns each subcommand before writing the call.** Helper subcommands frequently live on a separate binary than the main wrapper, and passing them to the wrong one fails only at runtime. Run `<bin> <subcommand> --help` for every subcommand you intend to call.
- **Let `--help` pick the primitive, not the code you are replacing.** Flags you assume exist (a by-id listing, a delete switch) may not; sometimes the only read path is a combined snapshot command. Design around the primitive that actually exists instead of porting the old call shape.
- **A patch touching control flow can break the block it edited.** After any patch into a try/finally or an indented region, re-import the file immediately — lint output can look clean while the file no longer parses.
- **A dry run's top-level failure can be correct semantics.** Read the phase/summary logic before treating `success=false` as a bug: a dry run that submits nothing legitimately ends "complete with pending", and "fixing" it would destroy a deliberately strict success口径.
- **Never log raw external-service output in the new client.** Classify failures into reasons (waf / rate_limited / not_found / ambiguous) and log only the reason plus ids; raw dumps leak private paths and session material into every report.
- **Give every "wait for an external event" a deadline.** An open or handshake with no timeout turns a transient stall into a silent hang that a process-exists health check scores as alive.
- **Ambiguity is not an error to smooth over.** When a batch response could map N results to N inputs more than one way, fail closed — a wrong binding costs far more than a retry.
- **Treat a delayed exit notification from an abandoned process as stale until the artifacts confirm it.** A mid-session interruption can deliver the exit code of a run you already discarded and relaunched, and it reads as the new run having failed. Check the runtime directory's newest mtimes and the current report before reacting, and clear the runtime directory when you relaunch so old and new artifacts cannot be confused.
- **Count the head explicitly when splicing flags into an args list.** Prepending `--flag value` and then slicing `[2:]` off the front drops the prepended pair rather than the original head, and the CLI exits with a required-argument error that looks like a bug in the new code. Build the argument list in one place instead of prepend-and-slice.

See `references/execution-layer-contract.md` for the extraction checklist to run before designing a new external-service layer, and `references/idempotency-proof.md` for what evidence a second identical run must produce.
