"""Auditable fusion of speaker, anti-spoofing and quality signals."""

from __future__ import annotations

from typing import Protocol

from .models import Decision, QualityReport, VerificationPolicy, VerificationResult


class QualityPolicy(Protocol):
    min_speech_seconds: float
    min_speech_ratio: float
    max_clipping_ratio: float
    min_snr_db: float


def evaluate_quality(quality: QualityReport, policy: QualityPolicy) -> tuple[str, ...]:
    reasons: list[str] = []
    if quality.speech_seconds < policy.min_speech_seconds:
        reasons.append("insufficient_speech")
    if quality.speech_ratio < policy.min_speech_ratio:
        reasons.append("low_speech_ratio")
    if quality.clipping_ratio > policy.max_clipping_ratio:
        reasons.append("excessive_clipping")
    if quality.estimated_snr_db < policy.min_snr_db:
        reasons.append("low_snr")
    return tuple(reasons)


def decide(
    *,
    speaker_score: float | None,
    spoof_probability: float | None,
    quality: QualityReport,
    policy: VerificationPolicy | None = None,
) -> VerificationResult:
    policy = policy or VerificationPolicy()
    if speaker_score is not None and not -1.0 <= speaker_score <= 1.0:
        raise ValueError("speaker_score must be between -1 and 1")
    if spoof_probability is not None and not 0.0 <= spoof_probability <= 1.0:
        raise ValueError("spoof_probability must be between 0 and 1")

    quality_reasons = evaluate_quality(quality, policy)
    if quality_reasons:
        return VerificationResult(
            Decision.REVIEW, speaker_score, spoof_probability, quality_reasons
        )

    if speaker_score is None:
        return VerificationResult(
            Decision.REVIEW,
            None,
            spoof_probability,
            ("speaker_score_unavailable",),
        )

    if spoof_probability is not None and spoof_probability > policy.max_spoof_probability:
        return VerificationResult(
            Decision.REJECT, speaker_score, spoof_probability, ("suspected_spoof",)
        )

    if spoof_probability is None and policy.require_spoof_check:
        return VerificationResult(
            Decision.REVIEW,
            speaker_score,
            None,
            ("spoof_check_required",),
        )

    distance = speaker_score - policy.speaker_threshold
    if distance >= 0:
        decision = Decision.ACCEPT
        reasons = (
            ("speaker_match", "bonafide_audio")
            if spoof_probability is not None
            else ("speaker_match", "spoof_check_not_run")
        )
    elif distance >= -policy.review_margin:
        decision = Decision.REVIEW
        reasons = (
            ("borderline_speaker_score", "spoof_check_not_run")
            if spoof_probability is None
            else ("borderline_speaker_score",)
        )
    else:
        decision = Decision.REJECT
        reasons = (
            ("speaker_mismatch", "spoof_check_not_run")
            if spoof_probability is None
            else ("speaker_mismatch",)
        )

    return VerificationResult(decision, speaker_score, spoof_probability, reasons)
