#!/usr/bin/env bash
# The project's own Python environment (.venv at the repo root), used by the
# board tools and the Harness. Never the Zephyr venv.
#   tools/venv.sh ensure   create .venv and install tools/requirements.txt if needed
#   tools/venv.sh python   print the interpreter path (after ensure)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/.venv"
REQ="$ROOT/tools/requirements.txt"
STAMP="$VENV/.requirements.sha256"

ensure() {
  if [[ ! -x "$VENV/bin/python" ]]; then
    echo "venv.sh: creating $VENV"
    python3 -m venv "$VENV"
  fi
  local want
  want="$(sha256sum "$REQ" | cut -d' ' -f1)"
  if [[ ! -f "$STAMP" || "$(cat "$STAMP")" != "$want" ]]; then
    echo "venv.sh: installing $REQ"
    "$VENV/bin/python" -m pip install --quiet --upgrade pip
    "$VENV/bin/python" -m pip install --quiet -r "$REQ"
    echo "$want" > "$STAMP"
  fi
}

case "${1:-ensure}" in
  ensure) ensure ;;
  python) ensure >&2; echo "$VENV/bin/python" ;;
  *) echo "usage: tools/venv.sh ensure|python" >&2; exit 2 ;;
esac
