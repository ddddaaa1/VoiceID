"""Auditable fusion of speaker, anti-spoofing and quality signals."""

from __future__ import annotations

from .models import Decision, QualityReport, VerificationPolicy, VerificationResult


def evaluate_quality(quality: QualityReport, policy: VerificationPolicy) -> tuple[str, ...]:
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
    speaker_score: float,
    spoof_probability: float,
    quality: QualityReport,
    policy: VerificationPolicy | None = None,
) -> VerificationResult:
    policy = policy or VerificationPolicy()
    if not -1.0 <= speaker_score <= 1.0:
        raise ValueError("speaker_score must be between -1 and 1")
    if not 0.0 <= spoof_probability <= 1.0:
        raise ValueError("spoof_probability must be between 0 and 1")

    quality_reasons = evaluate_quality(quality, policy)
    if quality_reasons:
        return VerificationResult(
            Decision.REVIEW, speaker_score, spoof_probability, quality_reasons
        )

    if spoof_probability > policy.max_spoof_probability:
        return VerificationResult(
            Decision.REJECT, speaker_score, spoof_probability, ("suspected_spoof",)
        )

    distance = speaker_score - policy.speaker_threshold
    if distance >= 0:
        decision, reasons = Decision.ACCEPT, ("speaker_match", "bonafide_audio")
    elif distance >= -policy.review_margin:
        decision, reasons = Decision.REVIEW, ("borderline_speaker_score",)
    else:
        decision, reasons = Decision.REJECT, ("speaker_mismatch",)

    return VerificationResult(decision, speaker_score, spoof_probability, reasons)
