#!/usr/bin/env python3
"""Evaluate ASVspoof 2021 LA CM scores with fixed official C012 coefficients."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from voiceid.adapters.evaluation.asvspoof2021 import load_la_scores
from voiceid.domain.tandem_metrics import TandemCoefficients, evaluate_tandem_cost


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("metadata", type=Path)
    parser.add_argument("scores", type=Path)
    parser.add_argument("--subset", default="eval", choices=("progress", "eval", "hidden"))
    parser.add_argument("--c0", type=float, required=True)
    parser.add_argument("--c1", type=float, required=True)
    parser.add_argument("--c2", type=float, required=True)
    parser.add_argument("--system-id", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    scores = load_la_scores(args.metadata, args.scores, subset=args.subset)
    result = evaluate_tandem_cost(
        scores.bonafide,
        scores.spoof,
        TandemCoefficients(args.c0, args.c1, args.c2),
    )
    report = {
        "schema_version": "voiceid-asvspoof2021-reference-report/v1",
        "track": "LA",
        "subset": scores.subset,
        "system_id": args.system_id,
        "score_direction": "higher_is_bonafide",
        "metadata_sha256": scores.metadata_sha256,
        "scores_sha256": scores.scores_sha256,
        "attacks": list(scores.attacks),
        "result": asdict(result),
        "interpretation": (
            "Reference-protocol reproduction; not VoiceID AASIST end-to-end performance."
        ),
    }
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
