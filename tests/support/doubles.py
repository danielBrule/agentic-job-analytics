"""Recording service doubles; scripts are test inputs, not relevance judgments."""

from collections import deque
from copy import deepcopy
import hashlib
from typing import Any


class EmbeddingDouble:
    """Produce stable hash vectors, with no claim of semantic similarity."""

    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[list[str]] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        if self.error is not None:
            raise self.error
        return [[byte / 255 for byte in hashlib.sha256(text.encode("utf-8")).digest()[:8]] for text in texts]


class ModelDouble:
    """Return scripted structured outputs or raise scripted failures in order."""

    def __init__(self, responses: list[Any]) -> None:
        self.responses = deque(deepcopy(responses))
        self.calls: list[dict[str, Any]] = []

    def invoke(self, request: dict[str, Any]) -> Any:
        self.calls.append(deepcopy(request))
        if not self.responses:
            raise RuntimeError("Model response script exhausted")
        response = self.responses.popleft()
        if isinstance(response, Exception):
            raise response
        return deepcopy(response)


class VectorDouble:
    """Record writes and return prescribed hits without computing ranking."""

    def __init__(self, *, search_results: list[Any] | None = None) -> None:
        self.records: dict[str, dict[str, Any]] = {}
        self.calls: list[dict[str, Any]] = []
        self.failures: dict[str, Exception] = {}
        self.search_results = deque(deepcopy(search_results or []))

    def _record(self, operation: str, **inputs: Any) -> None:
        self.calls.append(deepcopy({"operation": operation, **inputs}))
        if operation in self.failures:
            raise self.failures[operation]

    def upsert(self, records: list[dict[str, Any]]) -> None:
        self._record("upsert", records=records)
        replacements = {record["semantic_unit_id"]: deepcopy(record) for record in records}
        self.records.update(replacements)

    def delete(self, identifiers: list[str]) -> None:
        self._record("delete", identifiers=identifiers)
        for identifier in identifiers:
            self.records.pop(identifier, None)

    def search(self, embedding: list[float], **filters: Any) -> list[dict[str, Any]]:
        self._record("search", embedding=embedding, filters=filters)
        if not self.search_results:
            raise RuntimeError("Vector search script exhausted")
        response = self.search_results.popleft()
        if isinstance(response, Exception):
            raise response
        return deepcopy(response)
