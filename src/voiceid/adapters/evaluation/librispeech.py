"""Filesystem adapter that prepares a hash-locked LibriSpeech evaluation corpus."""

from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from voiceid.adapters.audio.energy_vad import EnergyVoiceActivityDetector
from voiceid.adapters.audio.wave_decoder import PcmWaveDecoder
from voiceid.adapters.evaluation.json_audio_manifest import write_audio_trial_manifest
from voiceid.application.librispeech import (
    CorpusPreparationError,
    LibriSpeechClip,
    LibriSpeechImportConfig,
    SelectedSpeaker,
    select_librispeech_clips,
)
from voiceid.application.preprocessing import AudioPreprocessor
from voiceid.domain.decision import evaluate_quality
from voiceid.domain.enrollment import EnrollmentPolicy
from voiceid.domain.evaluation import (
    AudioEnrollment,
    AudioFileReference,
    AudioTrial,
    AudioTrialManifest,
    TrialLabel,
    TrialPartition,
)
from voiceid.domain.models import VerificationPolicy

LIBRISPEECH_HOMEPAGE = "https://www.openslr.org/12/"
LIBRISPEECH_LICENSE = "CC BY 4.0"
PROVENANCE_SCHEMA_VERSION = "voiceid-corpus-provenance/v1"
_FLAC_NAME = re.compile(r"(?P<speaker>[0-9]+)-(?P<chapter>[0-9]+)-(?P<utterance>[0-9]+)\.flac")


class SoundFilePcmWaveTranscoder:
    """Inspect FLAC metadata and write mono 16 kHz signed 16-bit PCM WAVE."""

    def inspect(self, path: Path) -> float:
        soundfile = _soundfile()
        try:
            information = soundfile.info(path)
        except (OSError, RuntimeError) as error:
            raise CorpusPreparationError(f"could not inspect FLAC file: {path}") from error
        if information.channels != 1 or information.samplerate != 16_000:
            raise CorpusPreparationError(f"expected mono 16 kHz LibriSpeech audio: {path}")
        return information.frames / information.samplerate

    def convert(self, source: Path, destination: Path) -> None:
        payload = self.to_pcm_wave_bytes(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)

    def to_pcm_wave_bytes(self, source: Path) -> bytes:
        soundfile = _soundfile()
        try:
            audio, sample_rate = soundfile.read(source, dtype="int16", always_2d=True)
        except (OSError, RuntimeError) as error:
            raise CorpusPreparationError(f"could not decode FLAC file: {source}") from error
        if sample_rate != 16_000 or audio.shape[1] != 1:
            raise CorpusPreparationError(f"expected mono 16 kHz LibriSpeech audio: {source}")
        buffer = io.BytesIO()
        try:
            soundfile.write(
                buffer,
                audio[:, 0],
                sample_rate,
                format="WAV",
                subtype="PCM_16",
            )
        except (OSError, RuntimeError) as error:
            raise CorpusPreparationError(f"could not encode PCM WAVE: {source}") from error
        return buffer.getvalue()


class LibriSpeechCorpusPreparer:
    def __init__(self, transcoder: Any | None = None) -> None:
        self._transcoder = transcoder or SoundFilePcmWaveTranscoder()
        self._preprocessor = AudioPreprocessor(PcmWaveDecoder(), EnergyVoiceActivityDetector())

    def prepare(
        self,
        development_root: Path,
        evaluation_root: Path,
        output_directory: Path,
        *,
        dataset_version: str,
        config: LibriSpeechImportConfig,
    ) -> AudioTrialManifest:
        if not dataset_version or dataset_version != dataset_version.strip():
            raise CorpusPreparationError("dataset version must be non-empty and trimmed")
        if output_directory.exists():
            raise CorpusPreparationError("output directory must not already exist")

        development_clips = self._scan(development_root)
        evaluation_clips = self._scan(evaluation_root)
        validated_payloads: dict[Path, bytes] = {}
        rejected_candidates: dict[str, tuple[str, ...]] = {}

        def validate_clip(clip: LibriSpeechClip) -> bool:
            payload = self._transcoder.to_pcm_wave_bytes(clip.source_path)
            try:
                preprocessing = self._preprocessor.process(payload)
            except ValueError:
                rejected_candidates[clip.utterance_id] = ("invalid_audio",)
                return False
            reasons = tuple(
                sorted(
                    set(evaluate_quality(preprocessing.quality, EnrollmentPolicy()))
                    | set(evaluate_quality(preprocessing.quality, VerificationPolicy()))
                )
            )
            if reasons:
                rejected_candidates[clip.utterance_id] = reasons
                return False
            validated_payloads[clip.source_path] = payload
            return True

        selections = select_librispeech_clips(
            development_clips,
            evaluation_clips,
            config,
            validate_clip,
        )

        output_parent = output_directory.parent.resolve()
        output_parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{output_directory.name}.", dir=output_parent))
        try:
            manifest = self._materialize(selections, validated_payloads, staging, dataset_version)
            manifest_path = staging / "audio-trials.json"
            write_audio_trial_manifest(manifest, manifest_path)
            self._write_provenance(
                staging / "provenance.json",
                manifest_path,
                selections,
                dataset_version,
                config,
                rejected_candidates,
            )
            staging.rename(output_directory)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        return manifest

    def _scan(self, root: Path) -> tuple[LibriSpeechClip, ...]:
        root = root.resolve()
        if not root.is_dir():
            raise CorpusPreparationError(f"LibriSpeech subset directory not found: {root}")
        clips = []
        for path in sorted(root.rglob("*.flac")):
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                raise CorpusPreparationError(f"unsafe source audio path: {path}")
            match = _FLAC_NAME.fullmatch(path.name)
            if match is None or path.parent.parent.name != match["speaker"]:
                raise CorpusPreparationError(f"unexpected LibriSpeech path: {path}")
            clips.append(
                LibriSpeechClip(
                    source_path=path,
                    speaker_id=match["speaker"],
                    utterance_id=path.stem,
                    duration_seconds=self._transcoder.inspect(path),
                )
            )
        if not clips:
            raise CorpusPreparationError(f"no FLAC recordings found under: {root}")
        return tuple(clips)

    def _materialize(
        self,
        selections: tuple[SelectedSpeaker, ...],
        validated_payloads: dict[Path, bytes],
        staging: Path,
        dataset_version: str,
    ) -> AudioTrialManifest:
        references: dict[str, AudioFileReference] = {}
        enrollments = []
        for selection in selections:
            for clip in (*selection.enrollment_clips, *selection.probe_clips):
                relative = Path(
                    "audio",
                    selection.partition.value,
                    selection.speaker_id,
                    f"{clip.utterance_id}.wav",
                )
                destination = staging / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                payload = validated_payloads[clip.source_path]
                destination.write_bytes(payload)
                references[clip.utterance_id] = AudioFileReference(
                    path=relative.as_posix(),
                    sha256=hashlib.sha256(payload).hexdigest(),
                )
            enrollments.append(
                AudioEnrollment(
                    identity_id=_identity_id(selection),
                    speaker_id=_speaker_id(selection),
                    partition=selection.partition,
                    samples=tuple(
                        references[clip.utterance_id] for clip in selection.enrollment_clips
                    ),
                )
            )

        trials = []
        by_partition = {
            partition: [item for item in selections if item.partition is partition]
            for partition in TrialPartition
        }
        for partition, speakers in by_partition.items():
            for index, selection in enumerate(speakers):
                impostor_claim = speakers[(index + 1) % len(speakers)]
                for probe_index, clip in enumerate(selection.probe_clips, start=1):
                    reference = references[clip.utterance_id]
                    trials.extend(
                        (
                            AudioTrial(
                                trial_id=f"{partition.value}-genuine-{selection.speaker_id}-{probe_index:02d}",
                                partition=partition,
                                label=TrialLabel.GENUINE,
                                claimed_identity_id=_identity_id(selection),
                                probe_speaker_id=_speaker_id(selection),
                                sample=reference,
                                condition=f"librispeech-{_subset_name(partition)}",
                            ),
                            AudioTrial(
                                trial_id=f"{partition.value}-impostor-{selection.speaker_id}-{probe_index:02d}",
                                partition=partition,
                                label=TrialLabel.IMPOSTOR,
                                claimed_identity_id=_identity_id(impostor_claim),
                                probe_speaker_id=_speaker_id(selection),
                                sample=reference,
                                condition=f"librispeech-{_subset_name(partition)}",
                            ),
                        )
                    )

        return AudioTrialManifest(
            dataset_id="openslr-librispeech-clean-voiceid",
            dataset_version=dataset_version,
            consent_attestation=(
                "LibriSpeech is distributed under CC BY 4.0. This records dataset-level "
                "authorization for research use, not individual consent for biometric deployment."
            ),
            enrollments=tuple(enrollments),
            trials=tuple(trials),
        )

    @staticmethod
    def _write_provenance(
        path: Path,
        manifest_path: Path,
        selections: tuple[SelectedSpeaker, ...],
        dataset_version: str,
        config: LibriSpeechImportConfig,
        rejected_candidates: dict[str, tuple[str, ...]],
    ) -> None:
        payload = {
            "schema_version": PROVENANCE_SCHEMA_VERSION,
            "dataset": {
                "id": "openslr-librispeech-clean-voiceid",
                "version": dataset_version,
            },
            "source": {
                "name": "LibriSpeech ASR corpus",
                "homepage": LIBRISPEECH_HOMEPAGE,
                "license": LIBRISPEECH_LICENSE,
                "archives": {
                    "dev-clean.tar.gz": "42e2234ba48799c1f50f24a7926300a1",
                    "test-clean.tar.gz": "32fa31d27d2e1cad72775fee3f4849a9",
                },
            },
            "protocol": {
                **asdict(config),
                "development_subset": "dev-clean",
                "evaluation_subset": "test-clean",
                "impostor_pairing": "next-selected-speaker",
                "eligibility_pipeline_id": "pcm-wave-linear-energy-vad-v1",
                "quality_filter": {
                    "enrollment_policy": asdict(EnrollmentPolicy()),
                    "verification_policy": asdict(VerificationPolicy()),
                    "rejected_candidates": {
                        key: list(value) for key, value in sorted(rejected_candidates.items())
                    },
                },
            },
            "selected_speakers": {
                partition.value: [
                    selection.speaker_id
                    for selection in selections
                    if selection.partition is partition
                ]
                for partition in TrialPartition
            },
            "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "limitations": [
                "Read English speech is not representative of every deployment condition.",
                "Public-corpus licensing is not individual consent for biometric deployment.",
                "The upstream corpus was created for automatic speech recognition.",
            ],
        }
        path.write_text(f"{json.dumps(payload, indent=2, sort_keys=True)}\n", encoding="utf-8")


def _identity_id(selection: SelectedSpeaker) -> str:
    return f"librispeech-{selection.partition.value}-{selection.speaker_id}"


def _speaker_id(selection: SelectedSpeaker) -> str:
    return _identity_id(selection)


def _subset_name(partition: TrialPartition) -> str:
    return "dev-clean" if partition is TrialPartition.DEVELOPMENT else "test-clean"


def _soundfile() -> Any:
    try:
        import soundfile
    except ImportError as error:
        raise CorpusPreparationError(
            "soundfile is required; install the ML environment with `uv sync --extra ml`"
        ) from error
    return soundfile
