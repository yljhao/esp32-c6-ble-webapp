#!/usr/bin/env bash
# Acceptance Harness entry point: ./verify.sh [--flash] [--replay LOG] [--seconds N]
# (see tools/verify/verify.py). Never prompts; stdin is not read.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$("$ROOT/tools/venv.sh" python)"
exec "$PY" "$ROOT/tools/verify/verify.py" "$@" < /dev/null
