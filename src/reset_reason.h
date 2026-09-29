/* SPDX-License-Identifier: Apache-2.0 */
#ifndef RESET_REASON_H
#define RESET_REASON_H

/*
 * Reset reason as a fixed lowercase word for the "[BOOT] reason=<reason>"
 * Serial marker: poweron, pin, software, watchdog, brownout,
 * panic, deepsleep, usb, jtag or unknown.
 */
const char *reset_reason_string(void);

#endif /* RESET_REASON_H */
