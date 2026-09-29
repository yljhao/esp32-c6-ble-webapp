# SPDX-License-Identifier: Apache-2.0
#
# XIAO ESP32-C6 BLE Web App. Out-of-tree Zephyr application
# (no west workspace, no sysbuild, no MCUboot: Espressif simple boot).

cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(c6_ble_webapp)

target_include_directories(app PRIVATE src)
target_sources(app PRIVATE
  src/main.c
  src/reset_reason.c
)
