"""Calibrate a spoof countermeasure on development and report held-out results."""

from __future__ import annotations

from dataclasses import dataclass

from voiceid.domain.evaluation import TrialPartition
from voiceid.domain.metrics import BinomialConfidenceInterval, wilson_score_interval
from voiceid.domain.spoof_metrics import (
    CountermeasureCostMetrics,
    CountermeasureCostModel,
    CountermeasureRates,
    countermeasure_cost,
    countermeasure_rates,
    estimate_countermeasure_eer,
    minimum_countermeasure_cost,
)
from voiceid.domain.spoofing import (
    AttackCategory,
    SpoofLabel,
    SpoofScoreManifest,
    SpoofScoreTrial,
)


@dataclass(frozen=True, slots=True)
class SpoofPartitionEvaluation:
    bonafide_trials: int
    spoof_trials: int
    rates_at_selected_threshold: CountermeasureRates
    observed_eer: CountermeasureRates
    minimum_cost: CountermeasureCostMetrics
    cost_at_selected_threshold: CountermeasureCostMetrics
    bonafide_reject_interval: BinomialConfidenceInterval
    spoof_accept_interval: BinomialConfidenceInterval


@dataclass(frozen=True, slots=True)
class AttackEvaluation:
    attack_category: AttackCategory
    attack_ids: tuple[str, ...]
    spoof_trials: int
    spoof_accepts: int
    spoof_accept_rate: float
    spoof_accept_interval: BinomialConfidenceInterval


@dataclass(frozen=True, slots=True)
class SpoofEvaluationReport:
    schema_version: str
    dataset_id: str
    dataset_version: str
    countermeasure_model_id: str
    pipeline_id: str
    threshold_source: str
    selected_threshold: float
    cost_model: CountermeasureCostModel
    development: SpoofPartitionEvaluation
    evaluation: SpoofPartitionEvaluation
    evaluation_attacks: tuple[AttackEvaluation, ...]


def evaluate_spoof_scores(
    manifest: SpoofScoreManifest,
    cost_model: CountermeasureCostModel | None = None,
    confidence_level: float = 0.95,
) -> SpoofEvaluationReport:
    model = cost_model or CountermeasureCostModel()
    development = manifest.trials_for(TrialPartition.DEVELOPMENT)
    evaluation = manifest.trials_for(TrialPartition.EVALUATION)
    development_bonafide, development_spoof = _scores(development)
    selected = minimum_countermeasure_cost(development_bonafide, development_spoof, model)
    threshold = selected.rates.threshold
    return SpoofEvaluationReport(
        schema_version="voiceid-spoof-evaluation-report/v1",
        dataset_id=manifest.dataset_id,
        dataset_version=manifest.dataset_version,
        countermeasure_model_id=manifest.countermeasure_model_id,
        pipeline_id=manifest.pipeline_id,
        threshold_source="development_minimum_countermeasure_cost",
        selected_threshold=threshold,
        cost_model=model,
        development=_evaluate_partition(development, threshold, model, confidence_level),
        evaluation=_evaluate_partition(evaluation, threshold, model, confidence_level),
        evaluation_attacks=_evaluate_attacks(evaluation, threshold, confidence_level),
    )


def _scores(
    trials: tuple[SpoofScoreTrial, ...],
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    bonafide = tuple(
        trial.spoof_probability for trial in trials if trial.label is SpoofLabel.BONAFIDE
    )
    spoof = tuple(trial.spoof_probability for trial in trials if trial.label is SpoofLabel.SPOOF)
    return bonafide, spoof


def _evaluate_partition(
    trials: tuple[SpoofScoreTrial, ...],
    threshold: float,
    cost_model: CountermeasureCostModel,
    confidence_level: float,
) -> SpoofPartitionEvaluation:
    bonafide, spoof = _scores(trials)
    locked = countermeasure_rates(bonafide, spoof, threshold)
    return SpoofPartitionEvaluation(
        bonafide_trials=len(bonafide),
        spoof_trials=len(spoof),
        rates_at_selected_threshold=locked,
        observed_eer=estimate_countermeasure_eer(bonafide, spoof),
        minimum_cost=minimum_countermeasure_cost(bonafide, spoof, cost_model),
        cost_at_selected_threshold=countermeasure_cost(locked, cost_model),
        bonafide_reject_interval=wilson_score_interval(
            locked.bonafide_rejects, locked.bonafide_trials, confidence_level
        ),
        spoof_accept_interval=wilson_score_interval(
            locked.spoof_accepts, locked.spoof_trials, confidence_level
        ),
    )


def _evaluate_attacks(
    trials: tuple[SpoofScoreTrial, ...],
    threshold: float,
    confidence_level: float,
) -> tuple[AttackEvaluation, ...]:
    reports = []
    categories = sorted(
        {trial.attack_category for trial in trials if trial.label is SpoofLabel.SPOOF},
        key=lambda category: category.value,
    )
    for category in categories:
        category_trials = tuple(
            trial
            for trial in trials
            if trial.label is SpoofLabel.SPOOF and trial.attack_category is category
        )
        accepts = sum(trial.spoof_probability < threshold for trial in category_trials)
        reports.append(
            AttackEvaluation(
                attack_category=category,
                attack_ids=tuple(sorted({trial.attack_id for trial in category_trials})),
                spoof_trials=len(category_trials),
                spoof_accepts=accepts,
                spoof_accept_rate=accepts / len(category_trials),
                spoof_accept_interval=wilson_score_interval(
                    accepts, len(category_trials), confidence_level
                ),
            )
        )
    return tuple(reports)
