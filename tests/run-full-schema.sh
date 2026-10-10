#!/usr/bin/env bash
# Mission runner: sets the runtime PYTHONPATH internally so the outer command line
# never carries an interpreter-hijack variable.
set -u
RUNTIME=/home/hatch/.hermes/npm/node_modules/hermes-agent/runtime/hermes-agent
REPO=/home/hatch/workspace/repo-hermes-config
export PYTHONPATH="$RUNTIME"
export TMPDIR="${TMPDIR:-/home/hatch/.hermes/cache/scratch}"
exec "$RUNTIME/venv/bin/python3" "$REPO/tests/full_schema_delegation_harness.py" "$@"
