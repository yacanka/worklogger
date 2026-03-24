"""Canonical license payload serialization helpers."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class LicenseStatus(str, Enum):
    """Explicit license verification outcomes."""

    VALID = "valid"
    EXPIRED = "expired"
    INVALID_SIGNATURE = "invalid_signature"
    MALFORMED = "malformed"
    USERNAME_MISMATCH = "username_mismatch"


@dataclass(frozen=True)
class LicenseValidationResult:
    """Normalized verification result."""

    status: LicenseStatus
    remaining_days: int = 0
    payload: dict[str, Any] | None = None


def canonicalize_payload(payload: dict[str, Any]) -> bytes:
    """Serialize a payload as deterministic canonical JSON bytes."""
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


def decode_license_segments(license_text: str) -> tuple[bytes, bytes]:
    """Decode compact base64url `payload.signature` license segments."""
    payload_segment, signature_segment = _split_license(license_text.strip())
    return decode_base64url(payload_segment), decode_base64url(signature_segment)


def encode_license(payload_bytes: bytes, signature: bytes) -> str:
    """Encode payload and signature as compact base64url segments."""
    return f"{encode_base64url(payload_bytes)}.{encode_base64url(signature)}"


def encode_base64url(raw_bytes: bytes) -> str:
    """Encode bytes as padding-free base64url text."""
    return base64.urlsafe_b64encode(raw_bytes).decode("ascii").rstrip("=")


def decode_base64url(value: str) -> bytes:
    """Decode padding-free base64url text."""
    return base64.urlsafe_b64decode(f"{value}{'=' * (-len(value) % 4)}")


def parse_payload(payload_bytes: bytes) -> dict[str, Any]:
    """Parse JSON payload bytes and validate the minimum structure."""
    payload = json.loads(payload_bytes.decode("utf-8"))
    required = {"version", "license_id", "customer_id", "product", "issued_at", "expires_at", "features"}
    if not isinstance(payload, dict) or not required.issubset(payload):
        raise ValueError("payload is missing required fields")
    if not isinstance(payload["features"], list):
        raise ValueError("features must be a list")
    username = payload.get("username")
    if username is not None and not isinstance(username, str):
        raise ValueError("username must be a string")
    return payload


def parse_utc_timestamp(value: str) -> datetime:
    """Parse an ISO-8601 timestamp into a timezone-aware UTC datetime."""
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def utc_now() -> datetime:
    """Return the current UTC time."""
    return datetime.now(timezone.utc)


def _split_license(license_text: str) -> tuple[str, str]:
    parts = license_text.split(".")
    if len(parts) != 2 or not all(parts):
        raise ValueError("license must contain payload.signature segments")
    return parts[0], parts[1]
