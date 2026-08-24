"""Strict JSON adapter for hashed PCM WAVE evaluation manifests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from voiceid.domain.evaluation import (
    AudioEnrollment,
    AudioFileReference,
    AudioTrial,
    AudioTrialManifest,
    EvaluationProtocolError,
    TrialLabel,
    TrialPartition,
)

from .json_manifest import ManifestFormatError


def load_audio_trial_manifest(path: Path) -> AudioTrialManifest:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ManifestFormatError(f"could not read manifest: {path}") from error
    except json.JSONDecodeError as error:
        raise ManifestFormatError(f"manifest is not valid JSON: {error.msg}") from error

    root = _object(payload, "manifest")
    _exact_keys(
        root,
        {"schema_version", "dataset", "enrollments", "trials"},
        "manifest",
    )
    dataset = _object(root["dataset"], "dataset")
    _exact_keys(dataset, {"id", "version", "consent_attestation"}, "dataset")
    enrollments = _array(root["enrollments"], "enrollments")
    trials = _array(root["trials"], "trials")

    try:
        return AudioTrialManifest(
            schema_version=_string(root["schema_version"], "schema_version"),
            dataset_id=_string(dataset["id"], "dataset.id"),
            dataset_version=_string(dataset["version"], "dataset.version"),
            consent_attestation=_string(
                dataset["consent_attestation"], "dataset.consent_attestation"
            ),
            enrollments=tuple(
                _parse_enrollment(value, index) for index, value in enumerate(enrollments)
            ),
            trials=tuple(_parse_trial(value, index) for index, value in enumerate(trials)),
        )
    except (EvaluationProtocolError, ValueError) as error:
        raise ManifestFormatError(str(error)) from error


def audio_trial_manifest_payload(manifest: AudioTrialManifest) -> dict[str, Any]:
    return {
        "schema_version": manifest.schema_version,
        "dataset": {
            "id": manifest.dataset_id,
            "version": manifest.dataset_version,
            "consent_attestation": manifest.consent_attestation,
        },
        "enrollments": [
            {
                "identity_id": enrollment.identity_id,
                "speaker_id": enrollment.speaker_id,
                "partition": enrollment.partition.value,
                "samples": [
                    {"path": sample.path, "sha256": sample.sha256} for sample in enrollment.samples
                ],
            }
            for enrollment in manifest.enrollments
        ],
        "trials": [
            {
                "trial_id": trial.trial_id,
                "partition": trial.partition.value,
                "label": trial.label.value,
                "claimed_identity_id": trial.claimed_identity_id,
                "probe_speaker_id": trial.probe_speaker_id,
                "sample": {"path": trial.sample.path, "sha256": trial.sample.sha256},
                "condition": trial.condition,
            }
            for trial in manifest.trials
        ],
    }


def write_audio_trial_manifest(manifest: AudioTrialManifest, path: Path) -> None:
    payload = json.dumps(audio_trial_manifest_payload(manifest), indent=2, sort_keys=True)
    path.write_text(f"{payload}\n", encoding="utf-8")


def _parse_enrollment(value: object, index: int) -> AudioEnrollment:
    location = f"enrollments[{index}]"
    enrollment = _object(value, location)
    _exact_keys(
        enrollment,
        {"identity_id", "speaker_id", "partition", "samples"},
        location,
    )
    samples = _array(enrollment["samples"], f"{location}.samples")
    return AudioEnrollment(
        identity_id=_string(enrollment["identity_id"], f"{location}.identity_id"),
        speaker_id=_string(enrollment["speaker_id"], f"{location}.speaker_id"),
        partition=_partition(enrollment["partition"], f"{location}.partition"),
        samples=tuple(
            _parse_reference(sample, f"{location}.samples[{sample_index}]")
            for sample_index, sample in enumerate(samples)
        ),
    )


def _parse_trial(value: object, index: int) -> AudioTrial:
    location = f"trials[{index}]"
    trial = _object(value, location)
    _exact_keys(
        trial,
        {
            "trial_id",
            "partition",
            "label",
            "claimed_identity_id",
            "probe_speaker_id",
            "sample",
            "condition",
        },
        location,
    )
    try:
        label = TrialLabel(_string(trial["label"], f"{location}.label"))
    except ValueError as error:
        raise ManifestFormatError(f"{location}.label is invalid") from error
    return AudioTrial(
        trial_id=_string(trial["trial_id"], f"{location}.trial_id"),
        partition=_partition(trial["partition"], f"{location}.partition"),
        label=label,
        claimed_identity_id=_string(
            trial["claimed_identity_id"], f"{location}.claimed_identity_id"
        ),
        probe_speaker_id=_string(trial["probe_speaker_id"], f"{location}.probe_speaker_id"),
        sample=_parse_reference(trial["sample"], f"{location}.sample"),
        condition=_string(trial["condition"], f"{location}.condition"),
    )


def _parse_reference(value: object, location: str) -> AudioFileReference:
    reference = _object(value, location)
    _exact_keys(reference, {"path", "sha256"}, location)
    return AudioFileReference(
        path=_string(reference["path"], f"{location}.path"),
        sha256=_string(reference["sha256"], f"{location}.sha256"),
    )


def _partition(value: object, location: str) -> TrialPartition:
    try:
        return TrialPartition(_string(value, location))
    except ValueError as error:
        raise ManifestFormatError(f"{location} is invalid") from error


def _object(value: object, location: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ManifestFormatError(f"{location} must be an object")
    return value


def _array(value: object, location: str) -> list[object]:
    if not isinstance(value, list):
        raise ManifestFormatError(f"{location} must be an array")
    return value


def _string(value: object, location: str) -> str:
    if not isinstance(value, str) or not value:
        raise ManifestFormatError(f"{location} must be a non-empty string")
    return value


def _exact_keys(value: dict[str, object], expected: set[str], location: str) -> None:
    actual = set(value)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing or unknown:
        parts = []
        if missing:
            parts.append(f"missing: {', '.join(missing)}")
        if unknown:
            parts.append(f"unknown: {', '.join(unknown)}")
        raise ManifestFormatError(f"{location} fields are invalid ({'; '.join(parts)})")
