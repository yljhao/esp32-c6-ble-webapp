# SPDX-License-Identifier: Apache-2.0
#
# XIAO ESP32-C6 BLE Web App. Out-of-tree Zephyr application
# (no west workspace, no sysbuild, no MCUboot: Espressif simple boot).

cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(c6_ble_led)

target_include_directories(app PRIVATE src)
target_sources(app PRIVATE
  src/main.c
  src/reset_reason.c
  src/duty_readback.c
  src/user_led.c
  src/selftest.c
  src/brightness.c
  src/watchdog.c
  src/heartbeat.c
  src/heartbeat_link.c
  src/ble.c
  src/led_command.c
  src/led_shell.c
  src/link_filter.c
  src/nus_chunk.c
  src/shell_nus.c
)
target_sources_ifdef(CONFIG_C6_HANG_CMD app PRIVATE src/debug_hang.c)
target_sources_ifdef(CONFIG_C6_HEAP_REPORT app PRIVATE src/debug_heap.c)
