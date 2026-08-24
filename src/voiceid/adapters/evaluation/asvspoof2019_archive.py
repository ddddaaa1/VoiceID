"""Integrity and safe-extraction boundary for the official ASVspoof 2019 LA archive."""

from __future__ import annotations

import hashlib
import json
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath

from .asvspoof2019_audio import Asvspoof2019CorpusError

OFFICIAL_LA_ARCHIVE_BYTES = 7_640_952_520
OFFICIAL_LA_ARCHIVE_MD5 = "30c98f11d8b2bc21f2c257bfd78bb5c5"


def verify_archive(
    archive: Path,
    *,
    expected_bytes: int = OFFICIAL_LA_ARCHIVE_BYTES,
    expected_md5: str = OFFICIAL_LA_ARCHIVE_MD5,
) -> tuple[str, str]:
    try:
        if not archive.is_file() or archive.stat().st_size != expected_bytes:
            raise Asvspoof2019CorpusError("ASVspoof LA archive size does not match Zenodo")
        md5 = hashlib.md5(usedforsecurity=False)
        sha256 = hashlib.sha256()
        with archive.open("rb") as source:
            while chunk := source.read(8 * 1024 * 1024):
                md5.update(chunk)
                sha256.update(chunk)
    except OSError as error:
        raise Asvspoof2019CorpusError("ASVspoof LA archive is unavailable") from error
    if md5.hexdigest() != expected_md5:
        raise Asvspoof2019CorpusError("ASVspoof LA archive failed the official MD5 check")
    return md5.hexdigest(), sha256.hexdigest()


def extract_verified_archive(
    archive: Path,
    destination: Path,
    *,
    expected_bytes: int = OFFICIAL_LA_ARCHIVE_BYTES,
    expected_md5: str = OFFICIAL_LA_ARCHIVE_MD5,
    maximum_members: int = 150_000,
    maximum_uncompressed_bytes: int = 30_000_000_000,
) -> dict[str, object]:
    """Verify, validate every member, and atomically publish a new extraction root."""

    if destination.exists():
        raise Asvspoof2019CorpusError("ASVspoof extraction destination already exists")
    staging = destination.with_name(f".{destination.name}.extracting")
    if staging.exists():
        raise Asvspoof2019CorpusError("an incomplete ASVspoof extraction already exists")
    md5, sha256 = verify_archive(
        archive,
        expected_bytes=expected_bytes,
        expected_md5=expected_md5,
    )
    try:
        with zipfile.ZipFile(archive) as source:
            members = source.infolist()
            if not members or len(members) > maximum_members:
                raise Asvspoof2019CorpusError("ASVspoof archive member count is invalid")
            total = sum(member.file_size for member in members)
            if total <= 0 or total > maximum_uncompressed_bytes:
                raise Asvspoof2019CorpusError("ASVspoof archive expansion exceeds its limit")
            validated = tuple((member, _safe_member_path(member)) for member in members)
            staging.mkdir(parents=True)
            for member, relative in validated:
                target = staging.joinpath(*relative.parts)
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.open(member) as input_file, target.open("xb") as output_file:
                    shutil.copyfileobj(input_file, output_file, length=1024 * 1024)
        staging.replace(destination)
    except (OSError, zipfile.BadZipFile, RuntimeError) as error:
        raise Asvspoof2019CorpusError("ASVspoof LA archive extraction failed") from error
    provenance = {
        "schema_version": "voiceid-asvspoof2019-acquisition/v1",
        "source": "https://doi.org/10.7488/ds/2555",
        "zenodo_record": 6906306,
        "license": "ODC-By-1.0",
        "archive": {
            "bytes": expected_bytes,
            "md5": md5,
            "sha256": sha256,
        },
        "extraction": {
            "members": len(members),
            "uncompressed_bytes": total,
        },
    }
    (destination / "voiceid-acquisition.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return provenance


def _safe_member_path(member: zipfile.ZipInfo) -> PurePosixPath:
    path = PurePosixPath(member.filename)
    if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != "LA":
        raise Asvspoof2019CorpusError("ASVspoof archive contains an unsafe member path")
    mode = member.external_attr >> 16
    if stat.S_ISLNK(mode):
        raise Asvspoof2019CorpusError("ASVspoof archive contains a symbolic link")
    if not member.is_dir() and member.file_size <= 0:
        raise Asvspoof2019CorpusError("ASVspoof archive contains an empty file")
    return path
