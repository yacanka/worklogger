"""Public-key license verification for the client application."""

from __future__ import annotations

from pathlib import Path

from worklogger.ed25519_py import verify
from worklogger.license_schema import (
    LicenseStatus,
    LicenseValidationResult,
    decode_base64url,
    decode_license_segments,
    parse_payload,
    parse_utc_timestamp,
    utc_now,
)

DEFAULT_PUBLIC_KEY = Path(__file__).resolve().parent / "keys" / "public_key.ed25519"


def verify_license(
    license_text: str,
    username: str | None = None,
    public_key_path: str | Path | None = None,
) -> LicenseValidationResult:
    """Verify signature, expiry, and username binding for a license."""
    try:
        payload_bytes, signature = decode_license_segments(license_text)
        payload = parse_payload(payload_bytes)
        public_key = load_public_key(public_key_path or DEFAULT_PUBLIC_KEY)
    except Exception:
        return LicenseValidationResult(status=LicenseStatus.MALFORMED)
    if not verify(public_key, payload_bytes, signature):
        return LicenseValidationResult(status=LicenseStatus.INVALID_SIGNATURE)
    if _has_username_mismatch(payload, username):
        return LicenseValidationResult(status=LicenseStatus.USERNAME_MISMATCH, payload=payload)
    remaining_days = (parse_utc_timestamp(payload["expires_at"]).date() - utc_now().date()).days
    if remaining_days < 0:
        return LicenseValidationResult(LicenseStatus.EXPIRED, remaining_days, payload)
    return LicenseValidationResult(LicenseStatus.VALID, remaining_days, payload)


def load_public_key(public_key_path: str | Path) -> bytes:
    """Load a base64url-encoded 32-byte Ed25519 public key from disk."""
    public_key = decode_base64url(Path(public_key_path).read_text().strip())
    if len(public_key) != 32:
        raise ValueError("public key must be exactly 32 bytes")
    return public_key


def _has_username_mismatch(payload: dict, username: str | None) -> bool:
    return bool(payload.get("username") and payload["username"] != username)
