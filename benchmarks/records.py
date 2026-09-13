"""Write and validate append-only TASK-001 experiment records."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import jsonschema


SCHEMA_DIR = Path(__file__).with_name("schemas")


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_json(name: str, payload: dict[str, Any]) -> None:
    schema_path = SCHEMA_DIR / f"{name}.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(payload)


def validate_record(directory: str | Path) -> None:
    directory = Path(directory)
    for name in ("config", "metrics", "system"):
        path = directory / f"{name}.json"
        if not path.is_file():
            raise ValueError(f"missing required record file: {path}")
        validate_json(name, json.loads(path.read_text(encoding="utf-8")))

    metrics = json.loads((directory / "metrics.json").read_text(encoding="utf-8"))
    if metrics["status"] == "completed" and not (directory / "stdout.log").is_file():
        raise ValueError("completed record is missing stdout.log")
    manifest = directory / "artifacts" / "manifest.json"
    if manifest.is_file():
        for item in json.loads(manifest.read_text(encoding="utf-8")):
            artifact = directory / item["path"]
            if not artifact.is_file() or artifact.stat().st_size != item["bytes"] or sha256_file(artifact) != item["sha256"]:
                raise ValueError(f"artifact manifest mismatch: {item['path']}")
