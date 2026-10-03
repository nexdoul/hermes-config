---
name: flaky-failure-triage
description: "Use when a failure is intermittent or a fix stopped working."
version: 1.0.0
---

# Flaky / Intermittent Failure Triage

Use when a symptom comes and goes, a previous fix "worked" then stopped working, or a health check passes while the feature it guards keeps failing. Method: stop patching, isolate the variable, and change the path instead of the patch when the failing mode cannot be controlled.

Complements `systematic-debugging` (which owns the canonical 4-phase process); this skill covers only what that process needs when the symptom is non-deterministic.

## Always-on rules

1. **A non-reproducible symptom is never a solved bug.** If a shipped fix and the symptom returns, the first fix was not validated — return to investigation, do not stack a second patch on top.
2. **Always run a control group.** Verify a fix by running the failing path once WITH it and once WITHOUT it (`env -u VAR`, pre-fix binary, old config). If the control also passes, your variable is not what fixed it. The classic trap: the variable is already set globally (`/etc/environment`, `/etc/profile.d`, an inherited cron env), so the "fix" changes nothing while the passing run comes from something else entirely.
3. **A state flip is a finding.** Same code, same config, same input failing N/N then passing N/N after an unrelated action = the cause is state, not logic. Record the flip point; it is the strongest clue available.
4. **Never write one process observation down as behavior.** One `ps` snapshot showing a launch shape does not establish it; re-observe in a different window. A single seeing is how a wrong root cause gets into AGENTS.md and how two rounds of useless fixes follow it.
5. **"Check passes, feature fails" (two truths) → suspect the check's target first.** Find what the failing component actually consumed — its real profile, config, socket, or file — before adding robustness to the feature.
6. **"Fix verified N rounds" is not verification for an intermittent fault.** N consecutive passes prove nothing when the failure rate is ~10%. Require coverage across time or across the conditions you can vary, and say so explicitly when you only have the former.
7. **Prefer changing the path over refining the patch** when the failing mode cannot be controlled from outside. A stable same-signal alternative (e.g. `curl`-based smoke test instead of a browser probe) beats any number of knob tweaks on the uncontrollable component.

## Procedure

1. **Classify before touching anything.** Count real failures from the executor's own state (e.g. `sqlite3 executions.db "SELECT status, COUNT(*) ... GROUP BY status"`), not from the alert text. Repeated alerts can replay one incident record across days — the alert count is not the failure count.
2. **Prove the alternate path.** Before replacing the failing component in a health check, establish a same-load alternative and show it stable over many iterations (`for i in $(seq 1 30)`), including that it is not silently bypassing the check that matters (verify certificate validation returns success, not that `-k` was used).
3. **Bisect the boundary, cheapest first.** In a multi-layer stack, split the failing request across layers in the same second: low-level client (`curl`, `openssl s_client -proxy`) vs the failing component. A green low-level path while the component is red localizes the fault inside the component.
4. **Evidence for a browser/proxy TLS fault** — gather these before any theory (all cheap, all read-only):
   - Is the cert a real public chain or MITM-re-signed? (`openssl s_client -showcerts`)
   - Does the trust DB itself validate? (`certutil -V -u L -n <nick> -d sql:<profile>`)
   - Does the component consume the profile/config you inspected? (full `ps -eo args` line, saved verbatim — not a parsed extract)
   - Same certificate chain, different host: does one pass and the other fail? (rules out cert content)
   - Does plain HTTP over the same proxy pass while HTTPS fails? (rules out network/DNS/proxy)
   - Are the config knobs you suspect actually recognized? (`strings <binary> | grep <pref-or-env-var>` — an unrecognized pref or env var is a silent no-op, however confident you are)
5. **Capture the failure, not just the success.** Loop until the symptom appears while collecting per-iteration state (real profile, trust flags, timestamps). A loop that only ever succeeds yields no evidence; break on first red and snapshot everything.
6. **Stop-the-bleed decision.** If evidence localizes the fault inside an uncontrollable component and a stable alternative exists, swap the health probe to the alternative, keep the original tool for its real job, and write down explicitly that the component's root cause remains open plus the ordered evidence to collect next time.

## Evidence-capture pitfalls

- Parsing `ps` with `grep -o '<pattern>'` self-matches: the pattern string appears in the ps output and corrupts the parse. Use `ps -eo args | sed -n 's/.*-<flag> \\(...\\).*/\\1/p'`, or save the whole command line unparsed.
- `execSync` throws when a pipeline's trailing `grep` finds nothing (exit 1). Wrap in try/catch or append `|| true`, or every diagnostic returns a misleading empty/error value and you debug the harness instead of the system.
- Case-insensitive greps on files whose writer normalizes case can miss; fingerprint-match instead of matching human-readable labels.

## What not to record as durable knowledge

- Environment-dependent failures (missing binary, unconfigured credential, fresh-install path mismatch) — those are setup state, record the fix command instead.
- Negative claims about a tool being broken in general — record the specific conditions and the evidence.
- Dead-end hypotheses that were tested and failed — the rule "test the hypothesis, discard it" is enough; do not preserve the failed attempts as guidance.