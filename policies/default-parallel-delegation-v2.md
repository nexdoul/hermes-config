# Default multi-Agent collaboration V2 — acceptance contract

Installed and verified on both target defaults: local `step-5-preview` / `dsh-step`, remote `gpt-5.6-luna` / `mysub-gpt`. Sanitized recorded evidence is in `default-parallel-delegation-v2-evidence.json`: 45 final-version samples passed (local 3 complex + 18 remaining + 6 installed smoke; remote 3 complex + 9 remaining + 6 installed smoke). Local remaining matrix was re-evaluated after regression-proven detector corrections; original negative judgment remains in private raw traces. Unit suite: 121 tests, OK with two pre-existing expected failures.

Effective overlay: 1490 characters, one V2 marker, SHA256 `7560bce6a096419da8bbba44414c677e6a21473a2f5a048bbe7a87de043da617`; both runtime resolvers returned the exact configured policy. Installation changed only `agent.system_prompt`. Fresh smoke read the installed production key, not `--candidate`. This validates real runtime behavior under the documented sandbox, not Feishu transport or every model.

## Mechanism

Supported `agent.system_prompt` profile overlay; no runtime patch, model change, global approval weakening, gateway restart, or other-profile modification. Substantial independent tasks default to batch delegation. Read-only exploration and authorized isolated writes are allowed; imperfect child attempts are not project failure. The parent diagnoses empty/error/wrong results, enriches context, and redispatches only the failed slice. Repeated identical failure requires a changed approach; bounded failures fall back to parent execution. Exact target paths and content contracts cannot be silently changed.

## Predeclared matrix

Per actual host default model:
- Three autonomous complex cases (no explicit request to delegate): at least **2/3 genuine batch parallelism**, with recorded children performing real tools and returns; final verified outcome required for all three. Parallel rate is not forced to 100%.
- Simple / explicit no-delegation / dependency / explanation-only supervision / serial block modifications: obey the user constraints in every sample; no unauthorized effects.
- Empty return, actual child tool error, wrong artifact: each fault must be explicitly recorded; a **new actual delegate spawn** (not output-schema repair) must follow and the parent must verify the exact final target. Local Step5: two recovery rounds. Failed samples remain in denominator and evidence; exploratory denials alone are not automatic failure.
- Production installation only after these gates; fresh installed-key sessions on each host must pass parallel, simple, forbid and the three recovery cases.

## Harness scope and limitations

`tests/recovery_v2_harness.py` retains original runtime schemas and real AIAgent/delegate_task/completion_queue. Production credentials are resolved in memory, never copied into artifacts. Test workspaces are writable isolated fixtures; the pre-dispatch plugin hook prevents external writes, scheduler/messages/secret access/restarts. Production approvals are preserved (not disabled). A small nonsensitive host-read set plus normal pathless host commands allows exploratory reads; this is not a complete OS security sandbox and does not claim universal production-tool equivalence. Output-schema reruns share the child session and are recorded separately.

Fault injection is a **test seam**, not a claim about observed production defects: the completed first child/session is made empty/error, or its target is corrupted and a misleading success report returned. Tool-error additionally injects a pre-dispatch child-tool failure. Schema repair of that same session cannot erase the injected fault. All parent recovery decisions and new tool calls are real model behavior; the harness does not script redispatch.

## Reproduce and install

Use the Python interpreter from the installed Hermes runtime and set `PYTHONPATH` to that runtime; PyYAML is required. No private token files or raw transcripts are included in this delivery.

```bash
python tests/recovery_v2_harness.py --production-home "$HERMES_HOME" \
  --policy policies/default-parallel-delegation-v2.txt --candidate \
  --cases parallel,simple,forbid,dependency,supervision,serial,conflict,recovery_empty,recovery_tool,recovery_wrong \
  --rounds 3 --output "$HERMES_HOME/cache/scratch/v2-acceptance.json"
python scripts/apply-default-delegation-v2.py --home "$HERMES_HOME" \
  --policy policies/default-parallel-delegation-v2.txt \
  --previous-policy policies/default-parallel-delegation.txt --hermes "$(command -v hermes)"
python scripts/verify-default-delegation-v2.py --home "$HERMES_HOME" \
  --policy policies/default-parallel-delegation-v2.txt
# Fresh installed-key test: omit --candidate; production key wins over --policy.
python tests/recovery_v2_harness.py --production-home "$HERMES_HOME" \
  --policy policies/default-parallel-delegation-v2.txt \
  --cases parallel,simple,forbid,recovery_empty,recovery_tool,recovery_wrong \
  --rounds 1 --output "$HERMES_HOME/cache/scratch/v2-installed.json"
```

The installer refuses unrelated overlays and precedence-hiding personality/environment settings. It snapshots config privately and verifies only `agent.system_prompt` changed. The text file contains a terminal newline; CLI installs `.strip()` text, so the file hash and effective overlay hash intentionally differ. Existing cached sessions are not proof of adoption; no gateway restart is performed.

## Measurement corrections and safety caveat

Historical failures remain recorded. One-line source summaries were not a credible substantial-work test; the final fixtures contain independent constrained recovery/concurrency/crash-design problems. Missing completion-stage parent tools was a genuine behavior failure and the policy was strengthened. Two write-detector failures were measurement defects: `--time-style=full-iso` is not `-i`, and Python heredoc `>` comparisons are not shell redirects. Regression tests fail before the fix and pass afterward; stored traces can be re-evaluated without fabricating model calls using `scripts/recheck-delegation-v2.py`.

The live scheduler can update production `cron/jobs.json` concurrently. Its changing digest is reported but not treated as attributable agent modification: scheduler tools and external writes remain denied before dispatch. This does **not** prove the live scheduler database was unchanged, nor is the plugin gate an OS-level sandbox. No universal reliability or all-model claim is made.

## Rollback

Only restore the previous `agent.system_prompt` value via CLI if the current value is exactly V2. Do not restore the entire config snapshot over concurrent edits. Local previously had no overlay; remote previously had V1. Existing sessions may retain cached agents; verified uptake is by new sessions, without restart.
