/* SPDX-License-Identifier: Apache-2.0 */
/* Trivial suite for the host test target (ticket 01). */

#include <zephyr/ztest.h>

ZTEST_SUITE(smoke, NULL, NULL, NULL, NULL, NULL);

ZTEST(smoke, test_arithmetic_holds)
{
	zassert_equal(2 + 2, 4, "2 + 2 must be 4");
}
