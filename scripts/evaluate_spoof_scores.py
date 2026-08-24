"""Calibrate and evaluate a versioned VoiceID anti-spoofing score manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from voiceid.adapters.evaluation.json_manifest import ManifestFormatError
from voiceid.adapters.evaluation.json_spoof_manifest import (
    load_spoof_score_manifest,
    spoof_evaluation_report_payload,
    write_spoof_evaluation_report,
)
from voiceid.application.spoof_evaluation import evaluate_spoof_scores
from voiceid.domain.spoof_metrics import CountermeasureCostModel


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="Versioned spoof-score JSON manifest")
    parser.add_argument("--output", type=Path, help="Optional JSON report destination")
    parser.add_argument("--spoof-prior", type=float, default=0.5)
    parser.add_argument("--bonafide-reject-cost", type=float, default=1.0)
    parser.add_argument("--spoof-accept-cost", type=float, default=1.0)
    parser.add_argument("--confidence-level", type=float, default=0.95)
    arguments = parser.parse_args()

    try:
        manifest = load_spoof_score_manifest(arguments.manifest)
        cost_model = CountermeasureCostModel(
            spoof_prior=arguments.spoof_prior,
            bonafide_reject_cost=arguments.bonafide_reject_cost,
            spoof_accept_cost=arguments.spoof_accept_cost,
        )
        report = evaluate_spoof_scores(
            manifest,
            cost_model,
            confidence_level=arguments.confidence_level,
        )
    except (ManifestFormatError, ValueError) as error:
        parser.error(str(error))

    if arguments.output:
        write_spoof_evaluation_report(report, arguments.output)
        print(f"report={arguments.output}")
    else:
        print(json.dumps(spoof_evaluation_report_payload(report), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
