# SPDX-License-Identifier: Apache-2.0
# Host unit suite for the Brightness to pulse conversion (src/led_pulse.h), native_sim.
cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(test_led_pulse)

set(APP_SRC ${CMAKE_CURRENT_SOURCE_DIR}/../../src)
target_include_directories(app PRIVATE ${APP_SRC})
target_sources(app PRIVATE src/main.c)
# Run with ./build.sh test (twister over tests/ on native_sim/native/64).
