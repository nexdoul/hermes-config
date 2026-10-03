#!/usr/bin/env bash
# 中文帮助：--help；生产仅 SSH 别名，不依赖 venv。
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec /usr/bin/python3 "$SCRIPT_DIR/remote_dev.py" rollback "$@"
