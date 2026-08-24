from __future__ import annotations

import unittest

from voiceid.adapters.api.rate_limit import FixedWindowRateLimiter


class RateLimiterTests(unittest.TestCase):
    def test_limits_each_key_and_resets_after_the_window(self) -> None:
        now = [10.0]
        limiter = FixedWindowRateLimiter(2, 5.0, clock=lambda: now[0])

        self.assertEqual(limiter.consume("client-a"), (True, 0))
        self.assertEqual(limiter.consume("client-a"), (True, 0))
        self.assertEqual(limiter.consume("client-a"), (False, 5))
        self.assertEqual(limiter.consume("client-b"), (True, 0))

        now[0] = 15.0
        self.assertEqual(limiter.consume("client-a"), (True, 0))

    def test_rejects_invalid_configuration(self) -> None:
        with self.assertRaises(ValueError):
            FixedWindowRateLimiter(0, 1.0)


if __name__ == "__main__":
    unittest.main()
