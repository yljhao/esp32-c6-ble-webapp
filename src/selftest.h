/* SPDX-License-Identifier: Apache-2.0 */
#ifndef SELFTEST_H
#define SELFTEST_H

#include <stdbool.h>

/*
 * Self-test Stage: one 0->255->0 sweep of the User LED with a Duty readback
 * at 0, 128 and 255. Prints one "[LED]" Marker per readback and the result
 * Marker "[STAGE] selftest: done" or "... fail step=<n>" (main prints
 * "selftest: start"). Returns true on done. The boot continues either way;
 * the LED is left at 0 and main then applies Brightness 128.
 */
bool selftest_run(void);

#endif /* SELFTEST_H */
