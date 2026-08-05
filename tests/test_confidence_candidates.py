from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from scripts.create_confidence_candidates import EXPECTED_NAMES, create_candidate


def _source(path: Path) -> Path:
    source = path / "output"
    source.mkdir()
    for index, name in enumerate(EXPECTED_NAMES, start=1):
        (source / name).write_text(
            json.dumps(
                {
                    "case_id": f"EC_{index:03d}",
                    "assessment": {"primary_issue": "test", "confidence": 1.0},
                    "untouched": {"value": index},
                }
            ),
            encoding="utf-8",
        )
    return source


def test_candidate_changes_only_confidence_and_builds_flat_zip(tmp_path: Path) -> None:
    source = _source(tmp_path)
    experiments = tmp_path / "experiments"

    manifest = create_candidate(source, experiments, 0.95)

    candidate = experiments / "confidence_095"
    assert manifest["file_count"] == 50
    for name in EXPECTED_NAMES:
        original = json.loads((source / name).read_text(encoding="utf-8"))
        changed = json.loads((candidate / name).read_text(encoding="utf-8"))
        assert changed["assessment"]["confidence"] == 0.95
        changed["assessment"]["confidence"] = original["assessment"]["confidence"]
        assert changed == original
    with zipfile.ZipFile(experiments / "confidence_095.zip") as archive:
        assert sorted(archive.namelist()) == EXPECTED_NAMES


def test_candidate_rejects_invalid_confidence(tmp_path: Path) -> None:
    source = _source(tmp_path)
    with pytest.raises(ValueError, match="within"):
        create_candidate(source, tmp_path / "experiments", 1.1)
