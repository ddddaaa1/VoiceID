"""Calibrate on development trials and report once on held-out evaluation trials."""

from __future__ import annotations

from dataclasses import dataclass

from voiceid.domain.evaluation import (
    ScoredTrial,
    ScoredTrialManifest,
    TrialLabel,
    TrialPartition,
)
from voiceid.domain.metrics import (
    BinomialConfidenceInterval,
    DetectionCostMetrics,
    DetectionCostModel,
    ThresholdMetrics,
    detection_cost,
    estimate_eer,
    minimum_detection_cost,
    rates_at_threshold,
    wilson_score_interval,
)


@dataclass(frozen=True, slots=True)
class PartitionEvaluation:
    genuine_trials: int
    impostor_trials: int
    rates_at_selected_threshold: ThresholdMetrics
    observed_eer: ThresholdMetrics
    minimum_dcf: DetectionCostMetrics
    cost_at_selected_threshold: DetectionCostMetrics
    false_accept_interval: BinomialConfidenceInterval
    false_reject_interval: BinomialConfidenceInterval


@dataclass(frozen=True, slots=True)
class ConditionEvaluation:
    condition: str
    genuine_trials: int
    impostor_trials: int
    rates_at_selected_threshold: ThresholdMetrics | None
    false_accept_interval: BinomialConfidenceInterval | None
    false_reject_interval: BinomialConfidenceInterval | None


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    schema_version: str
    dataset_id: str
    dataset_version: str
    model_id: str
    pipeline_id: str
    threshold_source: str
    selected_threshold: float
    cost_model: DetectionCostModel
    development: PartitionEvaluation
    evaluation: PartitionEvaluation
    evaluation_conditions: tuple[ConditionEvaluation, ...]


def evaluate_scored_trials(
    manifest: ScoredTrialManifest,
    cost_model: DetectionCostModel | None = None,
    confidence_level: float = 0.95,
) -> EvaluationReport:
    """Select on development minDCF and lock the threshold for evaluation."""
    model = cost_model or DetectionCostModel()
    development_trials = manifest.trials_for(TrialPartition.DEVELOPMENT)
    evaluation_trials = manifest.trials_for(TrialPartition.EVALUATION)
    development_genuine, development_impostor = _scores(development_trials)
    selected = minimum_detection_cost(development_genuine, development_impostor, model)
    threshold = selected.rates.threshold

    return EvaluationReport(
        schema_version="voiceid-evaluation-report/v2",
        dataset_id=manifest.dataset_id,
        dataset_version=manifest.dataset_version,
        model_id=manifest.model_id,
        pipeline_id=manifest.pipeline_id,
        threshold_source="development_min_dcf",
        selected_threshold=threshold,
        cost_model=model,
        development=_evaluate_partition(
            development_trials, threshold, model, confidence_level
        ),
        evaluation=_evaluate_partition(
            evaluation_trials, threshold, model, confidence_level
        ),
        evaluation_conditions=_evaluate_conditions(
            evaluation_trials, threshold, confidence_level
        ),
    )


def _scores(trials: tuple[ScoredTrial, ...]) -> tuple[tuple[float, ...], tuple[float, ...]]:
    genuine = tuple(trial.score for trial in trials if trial.label is TrialLabel.GENUINE)
    impostor = tuple(trial.score for trial in trials if trial.label is TrialLabel.IMPOSTOR)
    return genuine, impostor


def _evaluate_partition(
    trials: tuple[ScoredTrial, ...],
    threshold: float,
    cost_model: DetectionCostModel,
    confidence_level: float,
) -> PartitionEvaluation:
    genuine, impostor = _scores(trials)
    locked_rates = rates_at_threshold(genuine, impostor, threshold)
    return PartitionEvaluation(
        genuine_trials=len(genuine),
        impostor_trials=len(impostor),
        rates_at_selected_threshold=locked_rates,
        observed_eer=estimate_eer(genuine, impostor),
        minimum_dcf=minimum_detection_cost(genuine, impostor, cost_model),
        cost_at_selected_threshold=detection_cost(locked_rates, cost_model),
        false_accept_interval=wilson_score_interval(
            locked_rates.false_accepts, locked_rates.impostor_trials, confidence_level
        ),
        false_reject_interval=wilson_score_interval(
            locked_rates.false_rejects, locked_rates.genuine_trials, confidence_level
        ),
    )


def _evaluate_conditions(
    trials: tuple[ScoredTrial, ...], threshold: float, confidence_level: float
) -> tuple[ConditionEvaluation, ...]:
    reports: list[ConditionEvaluation] = []
    for condition in sorted({trial.condition for trial in trials}):
        condition_trials = tuple(trial for trial in trials if trial.condition == condition)
        genuine, impostor = _scores(condition_trials)
        locked_rates = (
            rates_at_threshold(genuine, impostor, threshold)
            if genuine and impostor
            else None
        )
        reports.append(
            ConditionEvaluation(
                condition=condition,
                genuine_trials=len(genuine),
                impostor_trials=len(impostor),
                rates_at_selected_threshold=locked_rates,
                false_accept_interval=(
                    wilson_score_interval(
                        locked_rates.false_accepts,
                        locked_rates.impostor_trials,
                        confidence_level,
                    )
                    if locked_rates
                    else None
                ),
                false_reject_interval=(
                    wilson_score_interval(
                        locked_rates.false_rejects,
                        locked_rates.genuine_trials,
                        confidence_level,
                    )
                    if locked_rates
                    else None
                ),
            )
        )
    return tuple(reports)
