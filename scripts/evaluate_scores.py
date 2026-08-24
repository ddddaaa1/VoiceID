"""Calibrate and evaluate a versioned VoiceID scored-trial manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from voiceid.adapters.evaluation.json_manifest import (
    ManifestFormatError,
    evaluation_report_payload,
    load_scored_trial_manifest,
    write_evaluation_report,
)
from voiceid.application.evaluation import evaluate_scored_trials
from voiceid.domain.metrics import DetectionCostModel


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="Versioned scored-trial JSON manifest")
    parser.add_argument("--output", type=Path, help="Optional JSON report destination")
    parser.add_argument("--target-probability", type=float, default=0.01)
    parser.add_argument("--false-accept-cost", type=float, default=1.0)
    parser.add_argument("--false-reject-cost", type=float, default=1.0)
    arguments = parser.parse_args()

    try:
        manifest = load_scored_trial_manifest(arguments.manifest)
        cost_model = DetectionCostModel(
            target_probability=arguments.target_probability,
            false_accept_cost=arguments.false_accept_cost,
            false_reject_cost=arguments.false_reject_cost,
        )
        report = evaluate_scored_trials(manifest, cost_model)
    except (ManifestFormatError, ValueError) as error:
        parser.error(str(error))

    if arguments.output:
        write_evaluation_report(report, arguments.output)
        print(f"report={arguments.output}")
    else:
        print(json.dumps(evaluation_report_payload(report), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
