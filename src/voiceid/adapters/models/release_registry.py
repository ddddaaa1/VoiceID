"""Strict, hash-verifying model release registry adapter."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from voiceid.adapters.models.aasist import AasistSpoofDetector
from voiceid.adapters.models.speechbrain_ecapa import SpeechBrainEcapaEmbedder


class ModelReleaseError(ValueError):
    """Raised when a model release cannot be trusted."""


@dataclass(frozen=True, slots=True)
class VerifiedModelRelease:
    release_id: str
    application_version: str
    status: str
    model_ids: tuple[str, ...]
    verified_local_artifacts: int
    verified_evidence: int


def verify_model_release(path: Path, repository_root: Path) -> VerifiedModelRelease:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ModelReleaseError("model release is unavailable or invalid JSON") from error
    root = _object(payload, "release")
    _exact(
        root,
        {
            "schema_version",
            "release_id",
            "application_version",
            "created_at",
            "status",
            "models",
        },
        "release",
    )
    if root["schema_version"] != "voiceid-model-release/v1":
        raise ModelReleaseError("unsupported model release schema")
    if root["status"] not in {"experimental", "candidate", "active", "retired"}:
        raise ModelReleaseError("invalid model release status")
    models = root["models"]
    if not isinstance(models, list) or not models:
        raise ModelReleaseError("model release requires models")
    model_ids: list[str] = []
    local_count = 0
    evidence_count = 0
    roles: set[str] = set()
    expected_models = {
        "speaker": (
            SpeechBrainEcapaEmbedder.MODEL_ID,
            SpeechBrainEcapaEmbedder.MODEL_REVISION,
            True,
        ),
        "countermeasure": (
            AasistSpoofDetector.MODEL_ID,
            AasistSpoofDetector.SOURCE_REVISION,
            False,
        ),
    }
    for index, value in enumerate(models):
        location = f"models[{index}]"
        model = _object(value, location)
        _exact(
            model,
            {
                "role",
                "model_id",
                "source_revision",
                "deployment_enabled",
                "artifacts",
                "evidence",
            },
            location,
        )
        role = _string(model["role"], f"{location}.role")
        if role not in {"speaker", "countermeasure"} or role in roles:
            raise ModelReleaseError("release roles must be unique and supported")
        roles.add(role)
        model_id = _string(model["model_id"], f"{location}.model_id")
        model_ids.append(model_id)
        if not isinstance(model["deployment_enabled"], bool):
            raise ModelReleaseError("deployment_enabled must be boolean")
        expected_id, expected_revision, expected_enabled = expected_models[role]
        if model_id != expected_id:
            raise ModelReleaseError(f"{role} model ID does not match the runtime adapter")
        if _string(model["source_revision"], f"{location}.source_revision") != expected_revision:
            raise ModelReleaseError(f"{role} source revision does not match the runtime adapter")
        if model["deployment_enabled"] is not expected_enabled:
            raise ModelReleaseError(f"{role} deployment state is not approved")
        artifacts = model["artifacts"]
        evidence = model["evidence"]
        if not isinstance(artifacts, list) or not artifacts or not isinstance(evidence, list):
            raise ModelReleaseError("model artifacts and evidence must be arrays")
        if expected_enabled and not evidence:
            raise ModelReleaseError("deployment-enabled model requires evaluation evidence")
        for artifact_index, artifact_value in enumerate(artifacts):
            artifact = _object(artifact_value, f"{location}.artifacts[{artifact_index}]")
            _exact(artifact, {"uri", "local_path", "sha256"}, "artifact")
            digest = _digest(artifact["sha256"], "artifact.sha256")
            uri = _string(artifact["uri"], "artifact.uri")
            if not uri.startswith("https://") or expected_revision not in uri:
                raise ModelReleaseError("model artifact URI must bind the approved HTTPS revision")
            local_path = artifact["local_path"]
            if local_path is not None:
                target = _safe_local_path(repository_root, local_path)
                _verify_digest(target, digest)
                local_count += 1
        for evidence_index, evidence_value in enumerate(evidence):
            evidence_item = _object(evidence_value, f"{location}.evidence[{evidence_index}]")
            _exact(evidence_item, {"path", "sha256"}, "evidence")
            target = _safe_local_path(repository_root, evidence_item["path"])
            _verify_digest(target, _digest(evidence_item["sha256"], "evidence.sha256"))
            evidence_count += 1

    return VerifiedModelRelease(
        release_id=_string(root["release_id"], "release_id"),
        application_version=_string(root["application_version"], "application_version"),
        status=str(root["status"]),
        model_ids=tuple(model_ids),
        verified_local_artifacts=local_count,
        verified_evidence=evidence_count,
    )


def _safe_local_path(root: Path, value: object) -> Path:
    relative = Path(_string(value, "local path"))
    if relative.is_absolute() or ".." in relative.parts:
        raise ModelReleaseError("local release paths must stay inside the repository")
    resolved_root = root.resolve()
    resolved = (resolved_root / relative).resolve()
    if not resolved.is_relative_to(resolved_root) or not resolved.is_file():
        raise ModelReleaseError("local release artifact is unavailable")
    return resolved


def _verify_digest(path: Path, expected: str) -> None:
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ModelReleaseError(f"release artifact failed integrity check: {path.name}")


def _digest(value: object, location: str) -> str:
    digest = _string(value, location)
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ModelReleaseError(f"{location} must be lowercase SHA-256")
    return digest


def _object(value: object, location: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ModelReleaseError(f"{location} must be an object")
    return value


def _string(value: object, location: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ModelReleaseError(f"{location} must be a non-empty string")
    return value


def _exact(value: dict[str, object], expected: set[str], location: str) -> None:
    if set(value) != expected:
        raise ModelReleaseError(f"{location} fields are invalid")
