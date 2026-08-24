"""Frozen public artifacts for an end-to-end ASVspoof 2019 AASIST run."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from voiceid.adapters.evaluation.asvspoof2019_audio import Asvspoof2019LaProtocol
from voiceid.adapters.evaluation.json_spoof_manifest import spoof_evaluation_report_payload
from voiceid.adapters.models.aasist import AasistRuntime
from voiceid.application.asvspoof2019_scoring import Asvspoof2019ScoreRecord
from voiceid.application.spoof_evaluation import evaluate_spoof_scores
from voiceid.domain.spoofing import (
    AttackCategory,
    SpoofLabel,
    SpoofScoreManifest,
    SpoofScoreTrial,
)

from .asvspoof2019_tandem import evaluate_asvspoof2019_tandem, tandem_report_payload

_SYNTHETIC_ATTACKS = {
    "A01",
    "A02",
    "A03",
    "A04",
    "A07",
    "A08",
    "A09",
    "A10",
    "A11",
    "A12",
    "A16",
}
_VOICE_CONVERSION_ATTACKS = {
    "A05",
    "A06",
    "A13",
    "A14",
    "A15",
    "A17",
    "A18",
    "A19",
}


@dataclass(frozen=True, slots=True)
class Asvspoof2019OutputArtifacts:
    inventory_sha256: str
    scores_sha256: str
    report_sha256: str
    official_scores_sha256: str
    tandem_report_sha256: str
    provenance_sha256: str


def write_asvspoof2019_outputs(
    records: tuple[Asvspoof2019ScoreRecord, ...],
    protocol: Asvspoof2019LaProtocol,
    output_directory: Path,
    *,
    asv_scores_path: Path,
    countermeasure_model_id: str,
    pipeline_id: str,
) -> Asvspoof2019OutputArtifacts:
    if len(records) != len(protocol.trials):
        raise ValueError("cannot publish an incomplete ASVspoof scoring run")
    if any(record.sequence != index for index, record in enumerate(records)):
        raise ValueError("ASVspoof score records are not in exact protocol order")
    if any(
        record.trial_id != protocol.trials[index].trial_id for index, record in enumerate(records)
    ):
        raise ValueError("ASVspoof scores do not match the frozen protocol")
    output_directory.mkdir(parents=True, exist_ok=True)

    inventory_payload = _inventory_payload(records, protocol)
    inventory_hash = hashlib.sha256(inventory_payload).hexdigest()
    dataset_version = f"doi-10.7488-ds-2555+inventory-{inventory_hash[:16]}"
    manifest = SpoofScoreManifest(
        dataset_id="asvspoof2019-la",
        dataset_version=dataset_version,
        countermeasure_model_id=countermeasure_model_id,
        pipeline_id=pipeline_id,
        trials=tuple(
            SpoofScoreTrial(
                trial_id=record.trial_id,
                partition=record.partition,
                speaker_id=record.speaker_id,
                label=record.label,
                attack_category=_attack_category(record.attack_id, record.label),
                attack_id=record.attack_id,
                spoof_probability=record.spoof_probability,
                condition="logical_access_flac_16khz",
            )
            for record in records
        ),
    )
    score_payload = (
        json.dumps(_score_manifest_payload(manifest), indent=2, sort_keys=True) + "\n"
    ).encode()
    report_payload = (
        json.dumps(
            spoof_evaluation_report_payload(evaluate_spoof_scores(manifest)),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode()
    official_score_payload = "".join(
        f"{record.trial_id} {record.attack_id if record.label is SpoofLabel.SPOOF else '-'} "
        f"{record.label.value} {record.bonafide_logit:.12g}\n"
        for record in records
    ).encode()
    tandem_payload = (
        json.dumps(
            tandem_report_payload(evaluate_asvspoof2019_tandem(records, asv_scores_path)),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode()

    artifact_payloads = {
        "source-inventory.jsonl": inventory_payload,
        "spoof-scores.json": score_payload,
        "countermeasure-report.json": report_payload,
        "official-cm-scores.txt": official_score_payload,
        "tandem-report.json": tandem_payload,
    }
    for name, payload in artifact_payloads.items():
        _write_atomic(output_directory / name, payload)
    artifact_hashes = {
        name: hashlib.sha256(payload).hexdigest() for name, payload in artifact_payloads.items()
    }
    provenance = {
        "schema_version": "voiceid-asvspoof2019-aasist-provenance/v1",
        "dataset": {
            "id": "asvspoof2019-la",
            "version": dataset_version,
            "doi": "10.7488/ds/2555",
            "license": "ODC-By-1.0",
            "audio_committed": False,
        },
        "protocols": {
            "development_sha256": protocol.development_protocol_sha256,
            "evaluation_sha256": protocol.evaluation_protocol_sha256,
        },
        "system": {
            "countermeasure_model_id": countermeasure_model_id,
            "checkpoint_sha256": AasistRuntime.EXPECTED_WEIGHTS_SHA256,
            "pipeline_id": pipeline_id,
            "score_direction": {
                "spoof_probability": "higher_is_spoof",
                "official_cm_score": "higher_is_bonafide",
            },
        },
        "trial_count": len(records),
        "artifacts": artifact_hashes,
        "interpretation": (
            "End-to-end VoiceID AASIST research evidence; not proof of identity or liveness."
        ),
    }
    provenance_payload = (json.dumps(provenance, indent=2, sort_keys=True) + "\n").encode()
    _write_atomic(output_directory / "provenance.json", provenance_payload)
    return Asvspoof2019OutputArtifacts(
        inventory_sha256=inventory_hash,
        scores_sha256=artifact_hashes["spoof-scores.json"],
        report_sha256=artifact_hashes["countermeasure-report.json"],
        official_scores_sha256=artifact_hashes["official-cm-scores.txt"],
        tandem_report_sha256=artifact_hashes["tandem-report.json"],
        provenance_sha256=hashlib.sha256(provenance_payload).hexdigest(),
    )


def _inventory_payload(
    records: tuple[Asvspoof2019ScoreRecord, ...], protocol: Asvspoof2019LaProtocol
) -> bytes:
    lines = [
        json.dumps(
            {
                "schema_version": "voiceid-asvspoof2019-source-inventory/v1",
                "development_protocol_sha256": protocol.development_protocol_sha256,
                "evaluation_protocol_sha256": protocol.evaluation_protocol_sha256,
                "trial_count": len(records),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    ]
    lines.extend(
        json.dumps(
            {
                "audio_bytes": record.audio_bytes,
                "audio_path": record.audio_relative_path,
                "audio_sha256": record.audio_sha256,
                "sequence": record.sequence,
                "trial_id": record.trial_id,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        for record in records
    )
    return ("\n".join(lines) + "\n").encode()


def _score_manifest_payload(manifest: SpoofScoreManifest) -> dict[str, object]:
    return {
        "schema_version": manifest.schema_version,
        "dataset": {"id": manifest.dataset_id, "version": manifest.dataset_version},
        "system": {
            "countermeasure_model_id": manifest.countermeasure_model_id,
            "pipeline_id": manifest.pipeline_id,
        },
        "trials": [
            {
                "trial_id": trial.trial_id,
                "partition": trial.partition.value,
                "speaker_id": trial.speaker_id,
                "label": trial.label.value,
                "attack_category": trial.attack_category.value,
                "attack_id": trial.attack_id,
                "spoof_probability": trial.spoof_probability,
                "condition": trial.condition,
            }
            for trial in manifest.trials
        ],
    }


def _attack_category(attack_id: str, label: SpoofLabel) -> AttackCategory:
    if label is SpoofLabel.BONAFIDE:
        return AttackCategory.BONAFIDE
    if attack_id in _SYNTHETIC_ATTACKS:
        return AttackCategory.SYNTHETIC
    if attack_id in _VOICE_CONVERSION_ATTACKS:
        return AttackCategory.VOICE_CONVERSION
    return AttackCategory.UNKNOWN


def _write_atomic(path: Path, payload: bytes) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)
