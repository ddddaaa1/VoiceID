"""ASVspoof 2019 fixed-ASV t-DCF context and VoiceID report adapter."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

from voiceid.application.asvspoof2019_scoring import Asvspoof2019ScoreRecord
from voiceid.domain.evaluation import TrialPartition
from voiceid.domain.spoofing import SpoofLabel
from voiceid.domain.tandem_metrics import (
    TandemCoefficients,
    TandemEvaluation,
    evaluate_tandem_cost,
)

from .asvspoof2019_audio import Asvspoof2019CorpusError


@dataclass(frozen=True, slots=True)
class Asvspoof2019AsvContext:
    scores_sha256: str
    target_trials: int
    nontarget_trials: int
    spoof_trials: int
    observed_asv_eer: float
    asv_eer_threshold: float
    false_accept_rate: float
    miss_rate: float
    spoof_miss_rate: float
    coefficients: TandemCoefficients


@dataclass(frozen=True, slots=True)
class Asvspoof2019TandemReport:
    context: Asvspoof2019AsvContext
    pooled: TandemEvaluation
    attacks: dict[str, TandemEvaluation]


def evaluate_asvspoof2019_tandem(
    records: tuple[Asvspoof2019ScoreRecord, ...],
    asv_scores_path: Path,
) -> Asvspoof2019TandemReport:
    """Evaluate AASIST support scores with the organizer-provided fixed ASV system."""

    payload = _read_bounded(asv_scores_path, 100_000_000)
    target, nontarget, spoof = _parse_asv_scores(payload)
    asv_eer, threshold = _eer(target, nontarget)
    false_accept = sum(score >= threshold for score in nontarget) / len(nontarget)
    miss = sum(score < threshold for score in target) / len(target)
    spoof_miss = sum(score < threshold for score in spoof) / len(spoof)
    spoof_prior = 0.05
    target_prior = (1.0 - spoof_prior) * 0.99
    nontarget_prior = (1.0 - spoof_prior) * 0.01
    c1 = target_prior * (1.0 - miss) - nontarget_prior * 10.0 * false_accept
    c2 = 10.0 * spoof_prior * (1.0 - spoof_miss)
    coefficients = TandemCoefficients(c0=0.0, c1=c1, c2=c2)
    context = Asvspoof2019AsvContext(
        scores_sha256=hashlib.sha256(payload).hexdigest(),
        target_trials=len(target),
        nontarget_trials=len(nontarget),
        spoof_trials=len(spoof),
        observed_asv_eer=asv_eer,
        asv_eer_threshold=threshold,
        false_accept_rate=false_accept,
        miss_rate=miss,
        spoof_miss_rate=spoof_miss,
        coefficients=coefficients,
    )
    evaluation = tuple(
        record for record in records if record.partition is TrialPartition.EVALUATION
    )
    bonafide = tuple(
        record.bonafide_logit for record in evaluation if record.label is SpoofLabel.BONAFIDE
    )
    spoof_scores = tuple(
        record.bonafide_logit for record in evaluation if record.label is SpoofLabel.SPOOF
    )
    if not bonafide or not spoof_scores:
        raise Asvspoof2019CorpusError("t-DCF requires evaluation bonafide and spoof scores")
    attacks = sorted(
        {record.attack_id for record in evaluation if record.label is SpoofLabel.SPOOF}
    )
    return Asvspoof2019TandemReport(
        context=context,
        pooled=evaluate_tandem_cost(bonafide, spoof_scores, coefficients),
        attacks={
            attack_id: evaluate_tandem_cost(
                bonafide,
                tuple(
                    record.bonafide_logit
                    for record in evaluation
                    if record.label is SpoofLabel.SPOOF and record.attack_id == attack_id
                ),
                coefficients,
            )
            for attack_id in attacks
        },
    )


def tandem_report_payload(report: Asvspoof2019TandemReport) -> dict[str, object]:
    return {
        "schema_version": "voiceid-asvspoof2019-tandem-report/v1",
        "track": "LA",
        "partition": "evaluation",
        "score_direction": "higher_is_bonafide",
        "cost_model": {
            "spoof_prior": 0.05,
            "target_prior": 0.9405,
            "nontarget_prior": 0.0095,
            "asv_miss_cost": 1.0,
            "asv_false_accept_cost": 10.0,
            "countermeasure_miss_cost": 1.0,
            "countermeasure_false_accept_cost": 10.0,
        },
        "fixed_asv": asdict(report.context),
        "pooled": asdict(report.pooled),
        "attacks": {key: asdict(value) for key, value in report.attacks.items()},
        "interpretation": "End-to-end VoiceID AASIST result under the official fixed-ASV model.",
    }


def write_tandem_report(report: Asvspoof2019TandemReport, path: Path) -> bytes:
    payload = (json.dumps(tandem_report_payload(report), indent=2, sort_keys=True) + "\n").encode()
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)
    return payload


def _parse_asv_scores(payload: bytes) -> tuple[tuple[float, ...], ...]:
    grouped: dict[str, list[float]] = {"target": [], "nontarget": [], "spoof": []}
    try:
        lines = payload.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise Asvspoof2019CorpusError("ASV score file is not UTF-8") from error
    for line_number, line in enumerate(lines, 1):
        fields = line.split()
        if len(fields) != 3 or fields[1] not in grouped:
            raise Asvspoof2019CorpusError(f"invalid ASV score line {line_number}")
        try:
            score = float(fields[2])
        except ValueError as error:
            raise Asvspoof2019CorpusError("ASV score is not numeric") from error
        if not math.isfinite(score):
            raise Asvspoof2019CorpusError("ASV score must be finite")
        grouped[fields[1]].append(score)
    if any(not values for values in grouped.values()):
        raise Asvspoof2019CorpusError("ASV score file lacks required trial classes")
    return tuple(tuple(grouped[label]) for label in ("target", "nontarget", "spoof"))


def _eer(target: tuple[float, ...], nontarget: tuple[float, ...]) -> tuple[float, float]:
    labeled = [(score, 1) for score in target]
    labeled.extend((score, 0) for score in nontarget)
    labeled.sort(key=lambda item: item[0])
    target_seen = 0
    nontarget_remaining = len(nontarget)
    curve = [(0.0, 1.0, labeled[0][0] - 0.001)]
    for score, target_label in labeled:
        target_seen += target_label
        nontarget_remaining -= 1 - target_label
        curve.append((target_seen / len(target), nontarget_remaining / len(nontarget), score))
    miss, false_accept, threshold = min(curve, key=lambda item: abs(item[0] - item[1]))
    return (miss + false_accept) / 2.0, threshold


def _read_bounded(path: Path, maximum_bytes: int) -> bytes:
    try:
        if not path.is_file() or path.stat().st_size <= 0 or path.stat().st_size > maximum_bytes:
            raise Asvspoof2019CorpusError("ASV score file violates its size contract")
        return path.read_bytes()
    except OSError as error:
        raise Asvspoof2019CorpusError("ASV score file is unavailable") from error
