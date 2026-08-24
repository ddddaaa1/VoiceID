from __future__ import annotations

import unittest

from voiceid.adapters.api.observability import OperationalMetrics


class OperationalMetricsTests(unittest.TestCase):
    def test_renders_prometheus_histograms_without_identity_cardinality(self) -> None:
        metrics = OperationalMetrics()
        metrics.observe("post", "/api/v1/identities/alice/verify", 200, 0.2)
        metrics.observe("post", "/api/v1/identities/bob/verify", 200, 0.6)

        rendered = metrics.render()

        self.assertIn('route="/api/v1/identities/{identity_id}/verify"', rendered)
        self.assertIn("voiceid_http_requests_total", rendered)
        self.assertNotIn("alice", rendered)
        self.assertNotIn("bob", rendered)
        self.assertIn('le="0.5"} 1', rendered)
        self.assertIn('le="+Inf"} 2', rendered)

    def test_rejects_invalid_duration(self) -> None:
        with self.assertRaises(ValueError):
            OperationalMetrics().observe("GET", "/", 200, -1.0)


if __name__ == "__main__":
    unittest.main()
