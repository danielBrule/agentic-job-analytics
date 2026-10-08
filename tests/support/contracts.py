"""Load acceptance definitions while preserving their heterogeneous payloads."""

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
import math
from typing import Any

from tools.check_repository import case_ids, structured_file
from .text_fixtures import TEXT_FIXTURES


@dataclass
class ContractSuite:
    """Versioned definitions indexed by their original stable IDs."""

    metadata: dict[str, Any]
    by_id: dict[str, dict[str, Any]]


def load_suite(path: Path, collection: str) -> ContractSuite:
    data = structured_file(path)
    if not isinstance(data, dict):
        raise ValueError(f"{path.name}: expected a mapping")
    if type(data.get("version")) is not int or data["version"] < 1:
        raise ValueError(f"{path.name}: version must be a positive integer")
    case_ids(data, collection)
    return ContractSuite(
        {key: value for key, value in data.items() if key != collection},
        {case["id"]: case for case in data[collection]},
    )


def load_references(path: Path, golden: ContractSuite) -> dict[str, dict[str, Any]]:
    data = structured_file(path)
    if not isinstance(data, dict) or data.get("golden_questions_version") != golden.metadata["version"]:
        raise ValueError("Reference golden-question version does not match")
    identifiers = case_ids(data, "references")
    if identifiers - golden.by_id.keys():
        raise ValueError("References use unknown question IDs")
    for reference in data["references"]:
        if reference.get("status") not in {"exact_sql_reference", "supporting_evidence_only"}:
            raise ValueError(f"{reference['id']}: invalid reference status")
        if not isinstance(reference.get("sql"), str) or not reference["sql"].strip():
            raise ValueError(f"{reference['id']}: missing reference SQL")
    return {reference["id"]: reference for reference in data["references"]}


def resolve_text_fixtures(value: Any) -> Any:
    """Expand named descriptions in a copy, leaving source cases unchanged."""
    if isinstance(value, list):
        return [resolve_text_fixtures(item) for item in value]
    if not isinstance(value, dict):
        return deepcopy(value)
    result = {key: resolve_text_fixtures(item) for key, item in value.items()}
    if "job_description_fixture" in result:
        name = result.pop("job_description_fixture")
        if not isinstance(name, str) or name not in TEXT_FIXTURES:
            raise ValueError(f"Unknown text fixture: {name}")
        if "job_description" in result:
            raise ValueError("Both a description and a description fixture were supplied")
        result["job_description"] = TEXT_FIXTURES[name]
    return result


def assert_reference_rows(
    actual: list[dict[str, Any]], expected: list[dict[str, Any]], *,
    ordered: bool = False, float_tolerance: float = 0.000001,
) -> None:
    """Compare facts, preserving NULL and multiplicity; opt into meaningful order.

    Expected integers compare exactly. Expected floats use absolute tolerance. Unordered
    matching allows ties without imposing reference SQL's secondary ordering.
    Callers compare only semantic columns, not generated SQL or answer prose.
    """
    def equal(left: dict[str, Any], right: dict[str, Any]) -> bool:
        if left.keys() != right.keys():
            return False
        for key, value in left.items():
            other = right[key]
            if type(value) is bool or type(other) is bool:
                if type(value) is not type(other) or value != other:
                    return False
            elif type(value) in (int, float) and type(other) is float:
                if not math.isclose(value, other, rel_tol=0, abs_tol=float_tolerance):
                    return False
            elif value != other:
                return False
        return True

    if len(actual) != len(expected):
        raise AssertionError("Reference row count differs")
    if ordered:
        if not all(equal(left, right) for left, right in zip(actual, expected)):
            raise AssertionError("Ordered reference facts differ")
        return
    # Reassign earlier matches if overlapping tolerance ranges have alternatives.
    matches: dict[int, int] = {}
    def match(index: int, visited: set[int]) -> bool:
        for candidate, row in enumerate(expected):
            if candidate in visited or not equal(actual[index], row):
                continue
            visited.add(candidate)
            if candidate not in matches or match(matches[candidate], visited):
                matches[candidate] = index
                return True
        return False
    if not all(match(index, set()) for index in range(len(actual))):
        raise AssertionError("Unordered reference facts differ")
