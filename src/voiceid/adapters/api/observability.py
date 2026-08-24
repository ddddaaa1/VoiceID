"""Low-cardinality Prometheus metrics for the API boundary."""

from __future__ import annotations

import math
import re
import threading
from dataclasses import dataclass

_IDENTITY_PATH = re.compile(r"(/api/v1/identities/)[^/]+")


@dataclass(frozen=True, slots=True)
class RequestMetricKey:
    method: str
    route: str
    status: int


class OperationalMetrics:
    LATENCY_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

    def __init__(self) -> None:
        self._counts: dict[RequestMetricKey, int] = {}
        self._duration_sums: dict[RequestMetricKey, float] = {}
        self._buckets: dict[tuple[RequestMetricKey, float], int] = {}
        self._lock = threading.Lock()

    def observe(self, method: str, path: str, status: int, duration_seconds: float) -> None:
        if not math.isfinite(duration_seconds) or duration_seconds < 0:
            raise ValueError("request duration must be finite and non-negative")
        route = _low_cardinality_route(path)
        key = RequestMetricKey(method.upper(), route, status)
        with self._lock:
            self._counts[key] = self._counts.get(key, 0) + 1
            self._duration_sums[key] = self._duration_sums.get(key, 0.0) + duration_seconds
            for bucket in self.LATENCY_BUCKETS:
                if duration_seconds <= bucket:
                    item = (key, bucket)
                    self._buckets[item] = self._buckets.get(item, 0) + 1

    def render(self) -> str:
        lines = [
            "# HELP voiceid_http_requests_total Completed HTTP requests.",
            "# TYPE voiceid_http_requests_total counter",
        ]
        with self._lock:
            keys = sorted(
                self._counts,
                key=lambda key: (key.route, key.method, key.status),
            )
            for key in keys:
                labels = _labels(key)
                count = self._counts[key]
                lines.append(f"voiceid_http_requests_total{{{labels}}} {count}")
            lines.extend(
                (
                    "# HELP voiceid_http_request_duration_seconds HTTP request latency.",
                    "# TYPE voiceid_http_request_duration_seconds histogram",
                )
            )
            for key in keys:
                labels = _labels(key)
                for bucket in self.LATENCY_BUCKETS:
                    count = self._buckets.get((key, bucket), 0)
                    lines.append(
                        "voiceid_http_request_duration_seconds_bucket"
                        f'{{{labels},le="{bucket:g}"}} {count}'
                    )
                lines.append(
                    "voiceid_http_request_duration_seconds_bucket"
                    f'{{{labels},le="+Inf"}} {self._counts[key]}'
                )
                lines.append(
                    f"voiceid_http_request_duration_seconds_sum{{{labels}}} "
                    f"{self._duration_sums[key]:.9f}"
                )
                lines.append(
                    f"voiceid_http_request_duration_seconds_count{{{labels}}} {self._counts[key]}"
                )
        return "\n".join(lines) + "\n"


def _low_cardinality_route(path: str) -> str:
    normalized = _IDENTITY_PATH.sub(r"\1{identity_id}", path)
    if normalized.startswith("/assets/"):
        return "/assets/{asset}"
    return normalized


def _labels(key: RequestMetricKey) -> str:
    route = key.route.replace("\\", "\\\\").replace('"', '\\"')
    return f'method="{key.method}",route="{route}",status="{key.status}"'
