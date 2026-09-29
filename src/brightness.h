/* SPDX-License-Identifier: Apache-2.0 */
#ifndef BRIGHTNESS_H
#define BRIGHTNESS_H

#include <stdint.h>

/*
 * Brightness (glue): the User LED level 0..255, 128 at boot after the
 * Self-test, kept in RAM only (never persisted, unchanged by a disconnect).
 *
 * brightness_set() applies a value to the User LED immediately with no ramp,
 * takes the Duty readback and prints the Serial marker
 * "[LED] brightness=<n> duty=<pct>% freq=<hz>". Every applied Brightness
 * goes through it. Returns 0, or -errno when the LED could not be driven
 * (the remembered Brightness is then unchanged and no marker is printed).
 * A failed readback still applies the value and prints the marker.
 */
int brightness_set(uint8_t brightness);

/* The Brightness last applied by brightness_set(); 0 until the first call. */
uint8_t brightness_get(void);

/* Level the boot ends at (spec: Brightness rules). */
#define BRIGHTNESS_BOOT 128

#endif /* BRIGHTNESS_H */
