#!/usr/bin/env bash
# The "No upstream esptool" guard (ADR-0003, spec). Passes only when
#   1. `command -v esptool` is an esptool-build launcher,
#   2. the build's cached ESPTOOL_EXECUTABLE (CMakeCache.txt) is that same launcher, and
#   3. neither the Zephyr venv Python, the system Python nor the project .venv Python
#      can `import esptool` (a pip-installed upstream esptool would silently win on PATH).
# Run it with the PATH the build will use (build.sh activates the Zephyr venv first).
#
#   tools/esptool-guard.sh [--require-cache] [BUILD_DIR]
#
# --require-cache: fail when BUILD_DIR has no CMakeCache.txt (flash needs a build).
# Without it, a missing cache is skipped (the first configure has not happened yet).
# Prints one line per problem and a final "esptool-guard: OK" / "esptool-guard: FAIL".
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WEST_VENV="${C6_WEST_VENV:-$HOME/zephyrproject/.venv}"
require_cache=0
if [[ "${1:-}" == "--require-cache" ]]; then require_cache=1; shift; fi
BUILD_DIR="${1:-${C6_BUILD_DIR:-$ROOT/build}}"

problems=()
fail() { problems+=("$1"); }

# An esptool-build launcher is a small Python file that imports esptool_build.cli.
is_launcher() {
  [[ -f "$1" ]] && grep -q '^from esptool_build\.cli import' "$1"
}

path_tool="$(command -v esptool || true)"
if [[ -z "$path_tool" ]]; then
  fail "no 'esptool' on PATH (install the esptool-build launcher: esptool-build/install.sh)"
elif ! is_launcher "$path_tool"; then
  fail "'esptool' on PATH is $path_tool, which is not an esptool-build launcher (upstream esptool?); fix PATH or remove it"
fi

cache="$BUILD_DIR/CMakeCache.txt"
if [[ -f "$cache" ]]; then
  cached="$(sed -n 's/^ESPTOOL_EXECUTABLE:[A-Z]*=//p' "$cache" | head -n1)"
  if [[ -z "$cached" ]]; then
    fail "$cache has no ESPTOOL_EXECUTABLE entry; rebuild (rm -rf $BUILD_DIR)"
  elif ! is_launcher "$cached"; then
    fail "the build cached ESPTOOL_EXECUTABLE=$cached, which is not an esptool-build launcher; rm -rf $BUILD_DIR and rebuild"
  elif [[ -n "$path_tool" && "$(realpath "$cached")" != "$(realpath "$path_tool")" ]]; then
    fail "the build cached ESPTOOL_EXECUTABLE=$cached but PATH has $path_tool; they must be the same launcher (rm -rf $BUILD_DIR and rebuild)"
  fi
elif [[ $require_cache -eq 1 ]]; then
  fail "$cache not found; run ./build.sh build first"
fi

pythons=("$WEST_VENV/bin/python" "/usr/bin/python3")
[[ -x "$ROOT/.venv/bin/python" ]] && pythons+=("$ROOT/.venv/bin/python")
for py in "${pythons[@]}"; do
  [[ -x "$py" ]] || continue
  # cwd is / so a stray esptool.py in the current directory cannot mask or fake the result
  if (cd / && "$py" -c 'import esptool' >/dev/null 2>&1); then
    where="$(cd / && "$py" -c 'import esptool; print(esptool.__file__)' 2>/dev/null)"
    fail "$py can import an 'esptool' module ($where); uninstall it (pip uninstall esptool): it would shadow esptool-build"
  fi
done

if [[ ${#problems[@]} -gt 0 ]]; then
  for p in "${problems[@]}"; do echo "esptool-guard: $p" >&2; done
  echo "esptool-guard: FAIL (${#problems[@]} problem(s)); refusing to build or flash (ADR-0003)" >&2
  exit 1
fi
echo "esptool-guard: OK (esptool-build launcher $path_tool; no importable esptool module)"
