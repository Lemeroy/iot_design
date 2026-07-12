"""Deterministic and atomic persistence for local profile YAML."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile

import yaml

from .profile_loader import ProfileFile


def dump_profile_yaml(profile: ProfileFile) -> str:
    return yaml.safe_dump(
        profile.model_dump(mode="json"),
        allow_unicode=True,
        sort_keys=False,
    )


def save_profile_atomic(path: str | Path, profile: ProfileFile) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", dir=target.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(dump_profile_yaml(profile))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, target)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise
