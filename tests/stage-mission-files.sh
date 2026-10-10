#!/usr/bin/env bash
# Stage ONLY this mission's files (no production config, no credentials).
set -euo pipefail
cd /home/hatch/workspace/repo-hermes-config

MISSION_FILES=(
  policies/default-parallel-delegation.txt
  policies/default-parallel-delegation.md
  tests/full_schema_delegation_harness.py
  tests/run-full-schema.sh
  tests/delegation_evidence.py
  tests/test_delegation_evidence.py
  tests/test_delegation_evidence_side_effects.py
  tests/test_delegation_evidence_strength.py
  tests/test_gate_tokenization.py
  tests/test_harness_r2_defects.py
  tests/test_failurerecovery_requires_delegation.py
  tests/test_pending_counts_all_dispatches.py
  tests/test_acceptance_sees_every_parent_call.py
  tests/test_terminal_write_is_invocation.py
  tests/test_policy_comes_from_config.py
  tests/test_abandoned_dispatch_leak.py
  tests/check_gate_adversarial.py
  tests/stage-mission-files.sh
)

for f in "${MISSION_FILES[@]}"; do
  if [ -f "$f" ]; then
    git add -- "$f"
  else
    echo "MISSING (not staged): $f" >&2
  fi
done

echo "--- staged ---"
git diff --cached --name-only
echo "--- nothing else staged ---"
