"""Explicit privacy checks and projections for application-owned boundaries.

Callers classify and minimize content before invoking these helpers. No helper
discovers personal information, configures SDK capture, executes tools or sends
data. Sink integrations must use the prepared value, never the original payload.
"""

from dataclasses import dataclass, field
from enum import Enum
import math
import re
from typing import Any, Mapping
from urllib.parse import urlsplit


class PrivacyError(ValueError):
    """A classified privacy failure; messages contain no rejected input."""


class Boundary(Enum):
    """Separately authorized places where content is sent or retained."""

    MODEL = "model"
    EMBEDDING = "embedding"
    VECTOR = "vector"
    EVALUATOR = "evaluator"
    TRACE = "trace"
    LOG = "log"
    EXPORT = "export"
    CHECKPOINT = "checkpoint"


class ContentClass(Enum):
    """Caller-supplied provenance, never inferred from source text."""

    PRIVATE = "private"
    SYNTHETIC = "synthetic"


@dataclass(frozen=True)
class Destination:
    """An exact configured destination; public descriptions expose only origin.

    file:local identifies an application-owned local sink. Storage paths and
    credentials are configured separately; this record does not secure a file.
    """

    id: str
    endpoint: str = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", self.id):
            raise PrivacyError("invalid_destination")
        if not isinstance(self.endpoint, str):
            raise PrivacyError("invalid_destination")
        if self.endpoint == "file:local":
            return
        try:
            parsed = urlsplit(self.endpoint)
            valid = (
                parsed.scheme in {"http", "https"} and parsed.hostname
                and parsed.username is None and parsed.password is None
                and not parsed.query and not parsed.fragment
                and not any(character.isspace() or ord(character) < 32 for character in self.endpoint)
            )
            parsed.port  # Validate the port without exposing parsing errors.
        except ValueError:
            valid = False
        if not valid:
            raise PrivacyError("invalid_destination") from None

    def description(self) -> dict[str, str]:
        if self.endpoint == "file:local":
            origin = "file:local"
        else:
            parsed = urlsplit(self.endpoint)
            origin = f"{parsed.scheme}://{parsed.netloc}"
        return {"id": self.id, "origin": origin}


@dataclass(frozen=True)
class Grant:
    """Permission for one boundary, destination and content classification."""

    boundary: Boundary
    destination: Destination
    content: ContentClass

    def __post_init__(self) -> None:
        if (not isinstance(self.boundary, Boundary) or not isinstance(self.destination, Destination)
                or not isinstance(self.content, ContentClass)):
            raise PrivacyError("invalid_policy")


@dataclass(frozen=True)
class PrivacyPolicy:
    """Immutable application configuration; content access is denied by default."""

    grants: tuple[Grant, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.grants, tuple) or any(not isinstance(grant, Grant) for grant in self.grants):
            raise PrivacyError("invalid_policy")

    def require(self, boundary: Boundary, destination: Destination, content: ContentClass) -> None:
        if Grant(boundary, destination, content) not in self.grants:
            raise PrivacyError("destination_not_permitted")


_SECRET_KEYS = frozenset({
    "apikey", "apitoken", "accesskey", "secretkey", "clientsecret", "secret", "secrets",
    "password", "passwd", "token", "accesstoken", "refreshtoken", "idtoken",
    "authorization", "proxyauthorization", "cookie", "setcookie", "credentials",
    "credential", "privatekey", "xapikey",
})
_URL = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_AUTH = re.compile(r"\b(Bearer|Basic)\s+[^\s,;\"']+", re.IGNORECASE)


@dataclass(frozen=True)
class SecretRedactor:
    """Copy JSON-compatible values while removing configured and labelled secrets.

    Known values must be supplied by trusted credential configuration. This is
    defense in depth, not a classifier or proof that arbitrary text is safe.
    """

    secrets: tuple[str, ...] = field(default=(), repr=False)

    def __post_init__(self) -> None:
        if (not isinstance(self.secrets, tuple)
                or any(not isinstance(secret, str) or not secret for secret in self.secrets)):
            raise PrivacyError("invalid_redaction_config")

    def _text(self, value: str) -> str:
        for secret in sorted(set(self.secrets), key=len, reverse=True):
            value = value.replace(secret, "[REDACTED]")
        value = _AUTH.sub(lambda match: f"{match[1]} [REDACTED]", value)

        def safe_url(match: re.Match[str]) -> str:
            try:
                parsed = urlsplit(match[0])
                host = parsed.hostname
                if not host:
                    return "[REDACTED]"
                if parsed.username is None and not parsed.query and not parsed.fragment:
                    parsed.port
                    return match[0]
                if ":" in host:
                    host = f"[{host}]"
                port = f":{parsed.port}" if parsed.port is not None else ""
                return f"{parsed.scheme}://{host}{port}"
            except ValueError:
                return "[REDACTED]"

        return _URL.sub(safe_url, value)

    def redact(self, value: Any) -> Any:
        return self._copy(value, 0)

    def _copy(self, value: Any, depth: int) -> Any:
        if depth > 30:
            raise PrivacyError("unsafe_payload")
        if value is None or isinstance(value, (bool, int)):
            return value
        if isinstance(value, float) and math.isfinite(value):
            return value
        if isinstance(value, str):
            return self._text(value)
        if isinstance(value, (list, tuple)):
            return [self._copy(item, depth + 1) for item in value]
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                if not isinstance(key, str):
                    raise PrivacyError("unsafe_payload")
                safe_key = self._text(key)
                if safe_key in result:
                    raise PrivacyError("unsafe_payload")
                normalized = re.sub(r"[^a-z0-9]", "", key.lower())
                result[safe_key] = ("[REDACTED]" if normalized in _SECRET_KEYS
                                    else self._copy(item, depth + 1))
            return result
        raise PrivacyError("unsafe_payload")


_METADATA_KEYS = frozenset({
    "operation", "pipeline_step", "task", "profile", "provider", "model", "model_revision",
    "prompt_version", "schema_version", "generation_id", "status", "failure_category",
    "latency_seconds", "provider_duration_seconds", "input_tokens", "output_tokens", "total_tokens",
    "retry_number", "attempt_index", "invocation_reason", "fallback_outcome", "capability", "tool",
    "cost_amount", "cost_currency", "cost_basis", "usage_provenance",
})


def diagnostic_metadata(metadata: Mapping[str, Any], redactor: SecretRedactor) -> dict[str, Any]:
    """Project trusted operational metadata for logs/traces; omit all content.

    Callers must not place free-text evidence in allowlisted metadata fields.
    Raw exceptions and SDK objects are never serialized or stringified here.
    """
    result = {}
    for key in _METADATA_KEYS.intersection(metadata):
        value = metadata[key]
        if value is not None and not isinstance(value, (str, int, float, bool)):
            raise PrivacyError("unsafe_metadata")
        if isinstance(value, float) and not math.isfinite(value):
            raise PrivacyError("unsafe_metadata")
        result[key] = redactor.redact(value)
    return result


def prepare_content(
    policy: PrivacyPolicy, redactor: SecretRedactor, boundary: Boundary,
    destination: Destination, content: ContentClass, payload: Mapping[str, Any],
    selected_fields: tuple[str, ...],
) -> dict[str, Any]:
    """Check permission, select task-required fields and redact before a sink call.

    Classification, grants and field selection come from application code, not
    a model or retrieved text. The returned content remains private when its
    input is private; redaction never changes its classification.
    """
    policy.require(boundary, destination, content)
    if (not isinstance(selected_fields, tuple) or not selected_fields
            or any(not isinstance(key, str) or key not in payload for key in selected_fields)
            or len(set(selected_fields)) != len(selected_fields)):
        raise PrivacyError("invalid_projection")
    return redactor.redact({key: payload[key] for key in selected_fields})


_FAILURES = {
    "timeout": "The operation timed out.",
    "rate_limit": "The service rate limit was reached.",
    "service_unavailable": "The service is unavailable.",
    "credential_error": "Service credentials are unavailable or invalid.",
    "configuration_error": "The operation configuration is invalid.",
    "invalid_output": "The output did not pass validation.",
    "refused": "The provider refused the request.",
    "cancelled": "The operation was cancelled.",
    "safety_violation": "The operation violated a safety restriction.",
    "generation_mismatch": "The data generations do not match.",
    "invalid_source_evidence": "Source evidence did not pass validation.",
    "destination_not_permitted": "The data destination is not permitted.",
    "provider_failure": "The provider operation failed.",
}


def safe_failure(category: str) -> dict[str, str]:
    """Return fixed public failure text; never accept raw exception messages."""
    if category not in _FAILURES:
        raise PrivacyError("invalid_failure_category")
    return {"failure_category": category, "message": _FAILURES[category]}
