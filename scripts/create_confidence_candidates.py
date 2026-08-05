"""Create isolated confidence-only leaderboard candidates and ZIP files."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_NAMES = [f"EC_{index:03d}.json" for index in range(1, 51)]


def _hash_without_confidence(payload: dict[str, Any]) -> str:
    clone = json.loads(json.dumps(payload))
    clone.get("assessment", {}).pop("confidence", None)
    encoded = json.dumps(clone, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def create_candidate(source_dir: Path, experiment_dir: Path, confidence: float) -> dict[str, Any]:
    if not 0 <= confidence <= 1:
        raise ValueError("confidence must be within [0, 1]")
    source_files = sorted(path.name for path in source_dir.glob("EC_*.json"))
    if source_files != EXPECTED_NAMES:
        raise ValueError("source must contain exactly EC_001.json through EC_050.json")
    try:
        experiment_dir.resolve().relative_to(source_dir.resolve())
    except ValueError:
        pass
    else:
        raise ValueError("experiment directory must not be inside source output directory")

    candidate_name = f"confidence_{int(round(confidence * 100)):03d}"
    candidate_dir = experiment_dir / candidate_name
    if candidate_dir.exists():
        shutil.rmtree(candidate_dir)
    candidate_dir.mkdir(parents=True)
    changed: list[dict[str, Any]] = []
    for name in EXPECTED_NAMES:
        source = json.loads((source_dir / name).read_text(encoding="utf-8"))
        before_hash = _hash_without_confidence(source)
        old_confidence = source["assessment"]["confidence"]
        source["assessment"]["confidence"] = confidence
        after_hash = _hash_without_confidence(source)
        if before_hash != after_hash:
            raise AssertionError(f"non-confidence content changed for {name}")
        (candidate_dir / name).write_text(
            json.dumps(source, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        changed.append({"file": name, "from": old_confidence, "to": confidence})

    zip_path = experiment_dir / f"{candidate_name}.zip"
    zip_path.unlink(missing_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in EXPECTED_NAMES:
            archive.write(candidate_dir / name, arcname=name)
    with zipfile.ZipFile(zip_path) as archive:
        if sorted(archive.namelist()) != EXPECTED_NAMES:
            raise AssertionError("candidate ZIP manifest is invalid")

    manifest = {
        "candidate": candidate_name,
        "confidence": confidence,
        "file_count": len(changed),
        "only_field_changed": "assessment.confidence",
        "zip": zip_path.name,
        "changes": changed,
    }
    (candidate_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=ROOT / "output")
    parser.add_argument(
        "--experiment-dir", type=Path, default=ROOT / "experiments" / "confidence"
    )
    parser.add_argument("--values", type=float, nargs="+", default=[0.92, 0.95, 0.98])
    args = parser.parse_args()
    manifests = [
        create_candidate(args.source_dir, args.experiment_dir, value)
        for value in args.values
    ]
    print(
        json.dumps(
            [
                {
                    "candidate": item["candidate"],
                    "confidence": item["confidence"],
                    "file_count": item["file_count"],
                    "zip": item["zip"],
                }
                for item in manifests
            ],
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
