#!/usr/bin/env bash
# Developer loop for the XIAO ESP32-C6 (ADR-0003: flash only through esptool-build;
# this script pins --chip esp32c6 and the port; never upstream esptool).
#
#   ./build.sh build            esptool guard, west build
#   ./build.sh flash            esptool guard, write build/zephyr/zephyr.bin at the build's flash offset
#   ./build.sh identify         get-security-info, assert chip_id 13, then reset the board
#   ./build.sh serial [SECONDS] [--expect REGEX ...]
#                               exclusive port, reset through the shared helper, timestamped capture
#                               (default 30 s; 0 = until Ctrl-C). Each --expect is a marker that must
#                               appear; the capture ends once all were seen and exits 1 if one is missing
#   ./build.sh console [SECONDS] [--send TEXT] [--expect REGEX ...]
#                               same capture WITHOUT a reset; --send types a serial-shell command first
#   ./build.sh guard            run the esptool guard alone (spec: No upstream esptool)
#   ./build.sh test-tools       the Python unittest suites of tools/verify alone (Harness Check logic,
#                               Central line logic); project .venv, no board, no Bluetooth, no serial
#   ./build.sh test-web         the Web App logic tests (webapp/logic.js) in headless Google Chrome through
#                               Playwright (channel="chrome", no Web Bluetooth, no board); project .venv
#   ./build.sh test [ARGS...]   host unit suites: twister over tests/ on native_sim, no board, then the
#                               esptool guard's own red-path test, test-tools and test-web;
#                               exits non-zero on any failure.
#                               Extra ARGS go to twister, e.g. --sub-test c6.smoke.smoke.test_arithmetic_holds
#
# Environment: C6_PORT (default /dev/ttyACM0), C6_BUILD_DIR (default build),
# C6_EXTRA_CONF (extra Kconfig fragments), C6_EXTRA_DTC_OVERLAY (extra devicetree
# overlay for a scenario build; use a scenario C6_BUILD_DIR),
# C6_TEST_PLATFORM (default native_sim/native/64: this PC has no 32-bit multilib).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOARD="xiao_esp32c6/esp32c6/hpcore"
CHIP="esp32c6"
PORT="${C6_PORT:-/dev/ttyACM0}"
BUILD_DIR="${C6_BUILD_DIR:-$ROOT/build}"

ZEPHYR_BASE_DIR="$HOME/zephyrproject/zephyr"
ZEPHYR_SDK_DIR="$HOME/zephyr-sdk-1.0.1"
WEST_VENV="$HOME/zephyrproject/.venv"

die() { echo "build.sh: $*" >&2; exit 1; }

# Board work of every tool serialises on this lock; the Harness holds it for a
# whole run and sets C6_BOARD_LOCK_HELD=1 so its own build.sh calls do not deadlock.
board_lock() {
  if [[ "${C6_BOARD_LOCK_HELD:-0}" == "1" ]]; then
    "$@"
    return
  fi
  local rc=0
  flock -w 5 -E 75 "/tmp/$(echo "$PORT" | tr / _).lock" "$@" || rc=$?
  [[ $rc -ne 75 ]] || die "board busy: another tool holds /tmp/$(echo "$PORT" | tr / _).lock"
  return $rc
}

zephyr_env() {
  export ZEPHYR_BASE="$ZEPHYR_BASE_DIR"
  export ZEPHYR_SDK_INSTALL_DIR="$ZEPHYR_SDK_DIR"
  export ZEPHYR_TOOLCHAIN_VARIANT=zephyr
  # shellcheck disable=SC1091
  source "$WEST_VENV/bin/activate"
}

# The project .venv (pyserial for the board tools; the Harness tools join later).
# Never the Zephyr venv.
venv_python() {
  "$ROOT/tools/venv.sh" ensure >&2
  echo "$ROOT/.venv/bin/python"
}

config_value() {
  local key="$1" cfg="$BUILD_DIR/zephyr/.config"
  [[ -f "$cfg" ]] || die "$cfg not found; run ./build.sh build first"
  local line
  line="$(grep -E "^${key}=" "$cfg" || true)"
  [[ -n "$line" ]] || die "$key not set in $cfg"
  echo "${line#*=}" | tr -d '"'
}

esptool_guard() {
  "$ROOT/tools/esptool-guard.sh" "$@" || die "esptool guard failed; see the messages above (ADR-0003)"
}

cmd_build() {
  zephyr_env
  esptool_guard "$BUILD_DIR"
  local extra=()
  [[ -n "${C6_EXTRA_CONF:-}" ]] && extra+=("-DEXTRA_CONF_FILE=${C6_EXTRA_CONF}")
  [[ -n "${C6_EXTRA_DTC_OVERLAY:-}" ]] && extra+=("-DEXTRA_DTC_OVERLAY_FILE=${C6_EXTRA_DTC_OVERLAY}")
  if [[ ${#extra[@]} -gt 0 ]]; then
    west build -p auto -b "$BOARD" -d "$BUILD_DIR" "$ROOT" -- "${extra[@]}"
  else
    west build -p auto -b "$BOARD" -d "$BUILD_DIR" "$ROOT"
  fi
  esptool_guard --require-cache "$BUILD_DIR"   # the configure step has now cached the esptool it found
  [[ -s "$BUILD_DIR/zephyr/zephyr.bin" ]] || die "build produced no zephyr.bin"
  echo "build.sh: $BUILD_DIR/zephyr/zephyr.bin ($(stat -c %s "$BUILD_DIR/zephyr/zephyr.bin") bytes)"
}

cmd_flash() {
  local bin="$BUILD_DIR/zephyr/zephyr.bin"
  [[ -s "$bin" ]] || die "$bin missing; run ./build.sh build first"
  zephyr_env
  esptool_guard --require-cache "$BUILD_DIR"
  local offset mode freq size_mb
  offset="$(config_value CONFIG_FLASH_LOAD_OFFSET)"
  mode="$(config_value CONFIG_ESPTOOLPY_FLASHMODE)"
  freq="$(config_value CONFIG_ESPTOOLPY_FLASHFREQ)"
  size_mb="$(( $(config_value CONFIG_FLASH_SIZE) / 1048576 ))MB"
  echo "build.sh: flashing $bin at offset $offset (mode $mode, freq $freq, size $size_mb) on $PORT"
  board_lock esptool --chip "$CHIP" --port "$PORT" --before default-reset --after hard-reset \
    write-flash --flash-mode "$mode" --flash-freq "$freq" --flash-size "$size_mb" "$offset" "$bin"
}

cmd_identify() {
  local out
  zephyr_env
  esptool_guard "$BUILD_DIR"
  # esptool-build (f22af07 and later) honours --after, default hard-reset, so
  # the app restarts by itself after get-security-info; no reset.py needed.
  out="$(board_lock esptool --chip "$CHIP" --port "$PORT" get-security-info)" || die "get-security-info failed"
  echo "$out"
  local chip_id
  chip_id="$(echo "$out" | sed -nE 's/^ *chip_id: *([0-9]+).*/\1/p' | head -n1)"
  [[ "$chip_id" == "13" ]] || die "expected chip_id 13 (ESP32-C6), got '${chip_id:-none}'"
  echo "build.sh: identify OK (chip_id 13); esptool reset the board after reading"
}

cmd_serial() {
  local py seconds=30
  py="$(venv_python)"
  if [[ "${1:-}" =~ ^[0-9.]+$ ]]; then seconds="$1"; shift; fi
  board_lock "$py" "$ROOT/tools/board/console.py" --port "$PORT" --seconds "$seconds" --reset "$@"
}

# Capture without a reset (the board keeps running); extra args go to
# console.py, e.g. --send "led get" to type a serial-shell command.
cmd_console() {
  local py seconds=30
  py="$(venv_python)"
  if [[ "${1:-}" =~ ^[0-9.]+$ ]]; then seconds="$1"; shift; fi
  board_lock "$py" "$ROOT/tools/board/console.py" --port "$PORT" --seconds "$seconds" "$@"
}

# Host unit suites (spec: Testing Decisions, host rung). One twister run over
# tests/; every suite is a ztest app on native_sim, so no board and no lock are
# involved. Twister exits non-zero when any test fails. Then the esptool guard's
# own red-path test (a fake esptool first on PATH, an importable esptool module...).
cmd_test() {
  zephyr_env
  local out="$ROOT/twister-out"
  west twister --testsuite-root "$ROOT/tests" --platform "${C6_TEST_PLATFORM:-native_sim/native/64}" \
    --outdir "$out" --clobber-output --inline-logs --no-detailed-test-id "$@"
  echo "build.sh: host suites passed (report: $out/twister.json)"
  "$ROOT/tools/test_esptool_guard.sh"
  cmd_test_tools
  cmd_test_web
}

# Harness Check logic and Central line logic (Python unittest, project venv). Touches neither
# the board nor the PC's Bluetooth adapter nor a serial port.
cmd_test_tools() {
  "$(venv_python)" -m unittest discover -s "$ROOT/tools/verify" -v
}

# Web App logic module in headless Chrome (spec: Testing Decisions; this PC has no Node.js).
# tools/webtest/run.py serves the repo root on 127.0.0.1 and exits non-zero on any failed
# assertion or page error. No Web Bluetooth, no board, no serial port, no Bluetooth adapter.
cmd_test_web() {
  local py
  py="$(venv_python)"
  "$py" -m unittest discover -s "$ROOT/tools/webtest" -v
  "$py" "$ROOT/tools/webtest/run.py"
}

case "${1:-}" in
  build)    cmd_build ;;
  flash)    cmd_flash ;;
  identify) cmd_identify ;;
  guard)    zephyr_env; esptool_guard --require-cache "$BUILD_DIR" ;;
  serial)   shift; cmd_serial "$@" ;;
  console)  shift; cmd_console "$@" ;;
  test)     shift; cmd_test "$@" ;;
  test-tools) cmd_test_tools ;;
  test-web) cmd_test_web ;;
  *)        sed -n '2,27p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
