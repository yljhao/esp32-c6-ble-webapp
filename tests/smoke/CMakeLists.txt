# SPDX-License-Identifier: Apache-2.0
# Trivial host suite: proves the native_sim test target runs and can go red.
cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(test_smoke)

target_sources(app PRIVATE src/main.c)
