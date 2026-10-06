"""Validate public repository files without opening private evaluation data."""
from __future__ import annotations

import argparse
import collections
from datetime import date
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit

import yaml


class CheckFailure(ValueError):
    """A repository input violates a development check."""


class UniqueKeyLoader(yaml.SafeLoader):
    pass


def unique_mapping(loader: UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False) -> dict:
    values = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in values:
            raise CheckFailure(f"Duplicate YAML key: {key}")
        values[key] = loader.construct_object(value_node, deep=deep)
    return values


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping
)


def unique_json(pairs: list[tuple[str, object]]) -> dict:
    values = {}
    for key, value in pairs:
        if key in values:
            raise CheckFailure(f"Duplicate JSON key: {key}")
        values[key] = value
    return values


def structured_file(path: Path) -> object:
    try:
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".json":
            return json.loads(text, object_pairs_hook=unique_json)
        return yaml.load(text, Loader=UniqueKeyLoader)
    except (OSError, ValueError, yaml.YAMLError) as error:
        raise CheckFailure(f"{path.name}: {error}") from error


def public_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        capture_output=True, check=False,
    )
    if result.returncode:
        raise CheckFailure("Cannot list repository files; run this inside a Git checkout.")
    paths = []
    for name in sorted(set(result.stdout.decode("utf-8").split("\0")) - {""}):
        relative = Path(name)
        lowered = relative.name.lower()
        if (
            relative.parts[0].lower() in {"data", ".venv"}
            or (lowered.startswith(".env") and lowered != ".env.example")
            or lowered.endswith((".env", ".db", ".sqlite", ".sqlite3", ".db-wal", ".db-shm"))
        ):
            raise CheckFailure(f"Git includes private data that must remain ignored and untracked: {name}")
        path = root / relative
        if not path.resolve().is_relative_to(root.resolve()):
            raise CheckFailure(f"File resolves outside the repository: {name}")
        if path.is_file():
            paths.append(path)
    return paths


def markdown_body(text: str) -> str:
    lines = []
    fence: tuple[str, int] | None = None
    for line in text.splitlines():
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if marker:
            delimiter, remainder = marker.groups()
            if fence is None:
                fence = (delimiter[0], len(delimiter))
            elif delimiter[0] == fence[0] and len(delimiter) >= fence[1] and not remainder.strip():
                fence = None
            continue
        if fence is None:
            lines.append(line)
    if fence is not None:
        raise CheckFailure("Unclosed Markdown code fence")
    return "\n".join(lines)


def heading_anchors(body: str) -> set[str]:
    counts: collections.Counter[str] = collections.Counter()
    anchors = set()
    for heading in re.findall(r"^#{1,6}\s+(.+?)\s*#*\s*$", body, re.MULTILINE):
        slug = re.sub(r"[^\w -]", "", heading.lower()).replace(" ", "-")
        occurrence = counts[slug]
        counts[slug] += 1
        anchors.add(slug if occurrence == 0 else f"{slug}-{occurrence}")
    return anchors


def check_documents(root: Path, files: list[Path]) -> int:
    # Use the same resolved spelling for containment checks and error paths.
    root = root.resolve()
    public = {path.resolve() for path in files}
    bodies = {}
    for path in files:
        if path.suffix.lower() == ".md":
            try:
                bodies[path.resolve()] = markdown_body(path.read_text(encoding="utf-8"))
            except CheckFailure as error:
                raise CheckFailure(f"{path.resolve().relative_to(root)}: {error}") from error
    links = 0
    for path, body in bodies.items():
        for target in re.findall(r"\]\(([^)]+)\)", body):
            if urlsplit(target).scheme:
                continue
            filename, _, fragment = target.strip("<>").partition("#")
            destination = (path.parent / unquote(filename)).resolve() if filename else path
            if not destination.is_relative_to(root):
                raise CheckFailure(f"{path.relative_to(root)}: link outside repository: {target}")
            if destination not in public:
                raise CheckFailure(f"{path.relative_to(root)}: missing or ignored link: {target}")
            if fragment and destination.suffix.lower() == ".md":
                if unquote(fragment) not in heading_anchors(bodies[destination]):
                    raise CheckFailure(f"{path.relative_to(root)}: missing anchor: {target}")
            links += 1
    return links


def case_ids(data: dict, key: str) -> set[str]:
    cases = data.get(key)
    if not isinstance(cases, list) or not cases:
        raise CheckFailure(f"Expected a nonempty {key} list")
    identifiers = [case.get("id") for case in cases if isinstance(case, dict)]
    if len(identifiers) != len(cases) or any(not isinstance(value, str) or not value for value in identifiers):
        raise CheckFailure(f"Missing or invalid IDs in {key}")
    if len(set(identifiers)) != len(identifiers):
        raise CheckFailure(f"Duplicate IDs in {key}")
    return set(identifiers)


def check_contracts(root: Path) -> None:
    golden = structured_file(root / "evals/golden_questions.yaml")
    indexing = structured_file(root / "evals/indexing_cases.yaml")
    references = structured_file(root / "evals/fixtures/reference_queries.json")
    if not all(isinstance(data, dict) for data in (golden, indexing, references)):
        raise CheckFailure("Acceptance and reference files must contain mappings")
    for data in (golden, indexing):
        if type(data.get("version")) is not int or data["version"] < 1:
            raise CheckFailure("Acceptance version must be a positive integer")
    question_ids = case_ids(golden, "questions")
    baseline = golden.get("readiness_baseline")
    if not isinstance(baseline, dict):
        raise CheckFailure("Missing readiness baseline")
    try:
        date.fromisoformat(baseline["date"])
    except (KeyError, TypeError, ValueError):
        raise CheckFailure("Invalid readiness baseline date") from None
    if not isinstance(baseline.get("data_scope"), str) or not baseline["data_scope"].strip():
        raise CheckFailure("Missing readiness baseline data scope")
    readiness_tags = {
        "definition": {"specified", "decision-needed"},
        "data_coverage": {"available", "synthetic-needed", "profile-needed", "not-required"},
        "reference": {"exact-facts", "supporting-only", "review-needed", "behavior-specified"},
    }
    for question in golden["questions"]:
        readiness = question.get("readiness")
        if not isinstance(readiness, dict):
            raise CheckFailure(f"{question['id']}: missing readiness tags")
        for field, allowed in readiness_tags.items():
            value = readiness.get(field)
            if not isinstance(value, str) or value not in allowed:
                raise CheckFailure(f"{question['id']}: invalid readiness {field}")
    case_ids(indexing, "cases")
    if references.get("golden_questions_version") != golden["version"]:
        raise CheckFailure("Reference golden-question version does not match")
    reference_ids = case_ids(references, "references")
    unknown = reference_ids - question_ids
    if unknown:
        raise CheckFailure(f"References use unknown questions: {', '.join(sorted(unknown))}")
    for reference in references["references"]:
        if reference.get("status") not in {"exact_sql_reference", "supporting_evidence_only"}:
            raise CheckFailure(f"{reference['id']}: invalid reference status")
        if not isinstance(reference.get("sql"), str) or not reference["sql"].strip():
            raise CheckFailure(f"{reference['id']}: missing reference SQL")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        files = public_files(root)
        structured = [path for path in files if path.suffix.lower() in {".yaml", ".yml", ".json"}]
        for path in structured:
            structured_file(path)
        links = check_documents(root, files)
        check_contracts(root)
    except (CheckFailure, OSError) as error:
        print(f"Check failed: {error}", file=sys.stderr)
        return 1
    print(f"Public checks passed: {len(structured)} YAML/JSON files, {links} local links, acceptance/reference consistency.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
