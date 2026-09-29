#!/usr/bin/env bash
# Red-path test for tools/esptool-guard.sh: the guard passes on the real setup
# and fails, with the right message, for each way upstream esptool could be
# picked up. No board involved. Run by ./build.sh test.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GUARD="$ROOT/tools/esptool-guard.sh"
WEST_VENV="${C6_WEST_VENV:-$HOME/zephyrproject/.venv}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

REAL_PATH="$WEST_VENV/bin:$PATH"
LAUNCHER="$WEST_VENV/bin/esptool"
failed=0

# expect NAME WANT_RC WANT_TEXT -- command...
expect() {
  local name="$1" want_rc="$2" want_text="$3"; shift 4
  local out rc
  out="$("$@" 2>&1)"; rc=$?
  if [[ $rc -eq $want_rc && "$out" == *"$want_text"* ]]; then
    echo "  ok   $name (rc=$rc)"
  else
    echo "  FAIL $name: want rc=$want_rc with '$want_text', got rc=$rc:" >&2
    echo "$out" | sed 's/^/       /' >&2
    failed=$((failed + 1))
  fi
}

echo "esptool guard test:"

# A cache that names the real launcher, a cache that names something else.
mkdir -p "$TMP/good" "$TMP/faked" "$TMP/other" "$TMP/nocache"
echo "ESPTOOL_EXECUTABLE:FILEPATH=$LAUNCHER" > "$TMP/good/CMakeCache.txt"

# 1. green path
expect "real setup passes" 0 "esptool-guard: OK" -- \
  env PATH="$REAL_PATH" "$GUARD" --require-cache "$TMP/good"

# 2. fake esptool first on PATH
mkdir -p "$TMP/fakebin"
printf '#!/bin/sh\necho upstream\n' > "$TMP/fakebin/esptool"; chmod +x "$TMP/fakebin/esptool"
expect "fake esptool first on PATH" 1 "not an esptool-build launcher" -- \
  env PATH="$TMP/fakebin:$REAL_PATH" "$GUARD" "$TMP/nocache"

# 3. no esptool on PATH at all (bash and coreutils stay reachable through /usr/bin)
expect "no esptool on PATH" 1 "no 'esptool' on PATH" -- \
  env PATH="/usr/bin:/bin" "$GUARD" "$TMP/nocache"

# 4. the build cached a different (non-launcher) esptool
echo "ESPTOOL_EXECUTABLE:FILEPATH=$TMP/fakebin/esptool" > "$TMP/faked/CMakeCache.txt"
expect "build cached a non-launcher esptool" 1 "cached ESPTOOL_EXECUTABLE=" -- \
  env PATH="$REAL_PATH" "$GUARD" "$TMP/faked"

# 5. the build cached another launcher than the one PATH finds now
cp "$LAUNCHER" "$TMP/other/esptool"
echo "ESPTOOL_EXECUTABLE:FILEPATH=$TMP/other/esptool" > "$TMP/other/CMakeCache.txt"
expect "build cached a different launcher" 1 "must be the same launcher" -- \
  env PATH="$REAL_PATH" "$GUARD" "$TMP/other"

# 6. a Python can import an esptool module
mkdir -p "$TMP/pylib"; echo "" > "$TMP/pylib/esptool.py"
expect "importable esptool module" 1 "can import an 'esptool' module" -- \
  env PATH="$REAL_PATH" PYTHONPATH="$TMP/pylib" "$GUARD" "$TMP/good"

# 7. flash without a build
expect "no build cache for flash" 1 "run ./build.sh build first" -- \
  env PATH="$REAL_PATH" "$GUARD" --require-cache "$TMP/nocache"

if [[ $failed -ne 0 ]]; then
  echo "esptool guard test: $failed FAILED" >&2
  exit 1
fi
echo "esptool guard test: all passed"
