"""Disposable synthetic analytics projection and opt-in private snapshot access.

This schema covers analytics fields, not every upstream column or constraint.
Task IDs on calls are test provenance; upstream background-task tables are not
replicated. Only job foreign keys and current-assessment uniqueness are enforced.
"""

import json
import hashlib
from datetime import date
from pathlib import Path
import sqlite3
from typing import Any

from tools.check_repository import structured_file


REFERENCE_DATE = "2026-10-07"
SOURCE_TIME = "2026-01-01 12:00:00"

_SCHEMA = """
CREATE TABLE jobs (
    id INTEGER PRIMARY KEY, company TEXT, job_title TEXT, location TEXT,
    date_added TEXT, application_status TEXT, user_decision TEXT,
    next_action TEXT, next_action_date TEXT, closure_reason TEXT, job_description TEXT,
    updated_at TEXT, assessment_input_updated_at TEXT
);
CREATE TABLE assessments (
    id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL UNIQUE REFERENCES jobs(id) ON DELETE CASCADE,
    status TEXT, decision TEXT, fit_score INTEGER, priority_score INTEGER,
    tech_bar_fit INTEGER, seniority_fit INTEGER, primary_role_family TEXT, secondary_role_family TEXT,
    role_snapshot TEXT, real_mandate TEXT, technical_bar TEXT, decision_reason TEXT,
    strong_fit_signals TEXT, red_flags TEXT, sustainability_risks TEXT, evidence_gaps TEXT,
    evidence_anchors TEXT, material_mandate_dimensions TEXT,
    updated_at TEXT, source_job_updated_at TEXT, prompt_version TEXT
);
CREATE TABLE llm_calls (
    id INTEGER PRIMARY KEY, job_id INTEGER REFERENCES jobs(id) ON DELETE CASCADE,
    task_id INTEGER, task_attempt_id INTEGER, operation TEXT, requested_model TEXT,
    resolved_model TEXT, provider TEXT, total_tokens INTEGER, duration_seconds REAL,
    pipeline_step TEXT, retry_number INTEGER, status TEXT, failure_category TEXT,
    version_metadata TEXT, started_at TEXT, cache_read_input_tokens INTEGER
);
"""

_JSON_FIELDS = {
    "strong_fit_signals", "red_flags", "sustainability_risks", "evidence_gaps",
    "evidence_anchors", "material_mandate_dimensions", "version_metadata",
}


class SyntheticDatabase:
    """Create an isolated fixture; each edit commits so SQLite backup can capture it."""

    def __init__(self) -> None:
        self.connection = sqlite3.connect(":memory:", isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.executescript(_SCHEMA)
        self.columns = {
            table: {row[1] for row in self.connection.execute(f"PRAGMA table_info({table})")}
            for table in ("jobs", "assessments", "llm_calls")
        }

    def __enter__(self) -> "SyntheticDatabase":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def close(self) -> None:
        self.connection.close()

    def _values(self, table: str, values: dict[str, Any]) -> dict[str, Any]:
        if table not in self.columns or values.keys() - self.columns[table]:
            raise ValueError("Unknown fixture table or columns")
        return {key: json.dumps(value, sort_keys=True) if key in _JSON_FIELDS and isinstance(value, (list, dict))
                else value for key, value in values.items()}

    def _insert(self, table: str, values: dict[str, Any]) -> None:
        values = self._values(table, values)
        self.connection.execute(
            f"INSERT INTO {table} ({', '.join(values)}) VALUES ({', '.join('?' for _ in values)})",
            tuple(values.values()),
        )

    def job(self, identifier: int, **overrides: Any) -> None:
        self._insert("jobs", dict({
            "id": identifier, "company": "Synthetic employer", "job_title": "Synthetic role",
            "location": "FR", "date_added": "2026-01-01", "user_decision": "UNDECIDED",
            "job_description": "Build data tools", "updated_at": SOURCE_TIME,
            "assessment_input_updated_at": SOURCE_TIME,
        }, **overrides))

    def assessment(self, identifier: int, job_id: int, **overrides: Any) -> None:
        self._insert("assessments", dict({
            "id": identifier, "job_id": job_id, "status": "ASSESSED", "decision": "NO_GO",
            "fit_score": 10, "tech_bar_fit": 8, "seniority_fit": 5,
            "role_snapshot": "Technical delivery role", "real_mandate": "Build a capability",
            "decision_reason": "Frequent travel", "red_flags": ["Travel"],
            "sustainability_risks": ["Weekly travel"], "updated_at": SOURCE_TIME,
            "source_job_updated_at": SOURCE_TIME, "prompt_version": "synthetic-current",
        }, **overrides))

    def call(self, identifier: int, **overrides: Any) -> None:
        self._insert("llm_calls", dict({
            "id": identifier, "operation": "ASSESSMENT", "resolved_model": "actual",
            "requested_model": "requested", "status": "SUCCEEDED", "retry_number": 0,
            "pipeline_step": "assessment", "duration_seconds": 1.0,
            "started_at": SOURCE_TIME, "version_metadata": {"prompt_version": "synthetic-old"},
            "cache_read_input_tokens": 0,
        }, **overrides))

    def update(self, table: str, identifier: int, **changes: Any) -> None:
        """Change exactly the supplied fields, including timestamps only if supplied."""
        changes = self._values(table, changes)
        if not changes or "id" in changes:
            raise ValueError("Supply changes without replacing the source ID")
        cursor = self.connection.execute(
            f"UPDATE {table} SET {', '.join(key + ' = ?' for key in changes)} WHERE id = ?",
            (*changes.values(), identifier),
        )
        if cursor.rowcount != 1:
            raise ValueError("Fixture record does not exist")

    def delete_job(self, identifier: int) -> None:
        self.connection.execute("DELETE FROM jobs WHERE id = ?", (identifier,))


def open_private_snapshot(path: Path) -> sqlite3.Connection:
    """Reuse an explicitly selected existing snapshot; never create or refresh it.

    Read-only access is not private-pack version/label validation. Callers must
    verify compatibility before treating historical results as an answer key.
    The input must remain frozen; live WAL/journal databases require a separately
    prepared SQLite-native backup rather than this snapshot reader.
    """
    path = path.resolve(strict=True)
    if not path.is_file():
        raise ValueError("Snapshot must be an existing file")
    if any(Path(str(path) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
        raise ValueError("Snapshot must be frozen without SQLite sidecars")
    # Immutable reads cannot create sidecars or include unhashed journal content.
    connection = sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _pack_path(directory: Path, name: str) -> Path:
    if not isinstance(name, str) or not name:
        raise ValueError("Invalid private pack artifact path")
    path = (directory / name).resolve()
    if Path(name).is_absolute() or not path.is_relative_to(directory):
        raise ValueError("Artifact resolves outside the private pack")
    return path


def open_private_pack(directory: Path, repository_root: Path) -> sqlite3.Connection:
    """Validate an opt-in existing pack's versions/hashes, then open its snapshot.

    Integrity and definition compatibility do not establish reviewed semantic
    labels or passing runtime acceptance. No refresh, export or upload occurs.
    """
    directory = directory.resolve(strict=True)
    manifest = structured_file(directory / "manifest.json")
    if not isinstance(manifest, dict) or not isinstance(manifest.get("contracts"), dict):
        raise ValueError("Missing private pack contract metadata")
    contracts = manifest["contracts"]
    for name, relative in (("golden_questions", "evals/golden_questions.yaml"),
                           ("indexing_cases", "evals/indexing_cases.yaml")):
        path = repository_root / relative
        current = structured_file(path)
        if (contracts.get(name + "_version") != current["version"]
                or contracts.get(name + "_sha256") != _sha256(path)):
            raise ValueError("Private pack contract version/hash mismatch; explicit refresh required")
    if contracts.get("reference_definition_sha256") != _sha256(repository_root / "evals/fixtures/reference_queries.json"):
        raise ValueError("Private pack reference contract hash mismatch; explicit refresh required")
    try:
        date.fromisoformat(manifest["reference_date"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("Private pack requires a fixed reference date") from None
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("Private pack requires artifact hashes")
    names = set()
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise ValueError("Invalid private pack artifact")
        path = _pack_path(directory, artifact.get("name"))
        if path in names:
            raise ValueError("Duplicate private pack artifact")
        names.add(path)
        if artifact.get("sha256") != _sha256(path):
            raise ValueError("Private pack artifact hash mismatch")
    snapshot = manifest.get("snapshot")
    if not isinstance(snapshot, dict):
        raise ValueError("Private pack requires a snapshot")
    path = _pack_path(directory, snapshot.get("path"))
    if path not in names or snapshot.get("sha256") != _sha256(path):
        raise ValueError("Private pack snapshot hash mismatch")
    return open_private_snapshot(path)
