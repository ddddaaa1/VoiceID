#!/usr/bin/env python3
"""Compare a scored-trial manifest with a frozen score-distribution baseline."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from voiceid.adapters.evaluation.json_manifest import load_scored_trial_manifest
from voiceid.domain.drift import DriftBaseline, evaluate_score_drift
from voiceid.domain.evaluation import TrialPartition


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("scores", type=Path)
    parser.add_argument("--partition", default="evaluation", choices=("development", "evaluation"))
    parser.add_argument("--minimum-samples", type=int, default=30)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()

    payload = json.loads(arguments.baseline.read_text(encoding="utf-8"))
    if (
        set(payload)
        != {
            "schema_version",
            "model_id",
            "sample_count",
            "bin_edges",
            "expected_proportions",
            "source",
        }
        or payload["schema_version"] != "voiceid-score-drift-baseline/v1"
    ):
        parser.error("unsupported or malformed drift baseline")
    baseline = DriftBaseline(
        model_id=payload["model_id"],
        sample_count=payload["sample_count"],
        bin_edges=tuple(payload["bin_edges"]),
        expected_proportions=tuple(payload["expected_proportions"]),
    )
    manifest = load_scored_trial_manifest(arguments.scores)
    if manifest.model_id != baseline.model_id:
        parser.error("score model does not match the drift baseline")
    partition = TrialPartition(arguments.partition)
    report = evaluate_score_drift(
        baseline,
        tuple(trial.score for trial in manifest.trials_for(partition)),
        minimum_samples=arguments.minimum_samples,
    )
    rendered = (
        json.dumps(
            {
                "schema_version": "voiceid-score-drift-report/v1",
                "source": str(arguments.scores),
                "partition": partition.value,
                "report": asdict(report),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    if arguments.output:
        arguments.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
