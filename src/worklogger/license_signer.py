"""Asymmetric license signing helpers for the generator only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from worklogger.ed25519_py import sign
from worklogger.license_schema import canonicalize_payload, decode_base64url, encode_license


def build_payload(fields: dict[str, Any]) -> dict[str, Any]:
    """Build a canonical payload with stable key ordering."""
    payload = {
        "version": fields["version"],
        "license_id": fields["license_id"],
        "customer_id": fields["customer_id"],
        "product": fields["product"],
        "issued_at": fields["issued_at"],
        "expires_at": fields["expires_at"],
        "features": list(fields.get("features", [])),
    }
    username = fields.get("username")
    if username:
        payload["username"] = username
    return payload


def sign_license(payload: dict[str, Any], private_key_path: str) -> str:
    """Sign the canonical payload with an Ed25519 private key seed file."""
    payload_bytes = canonicalize_payload(payload)
    private_seed = load_private_seed(private_key_path)
    return encode_license(payload_bytes, sign(private_seed, payload_bytes))


def load_private_seed(private_key_path: str) -> bytes:
    """Load a base64url-encoded 32-byte Ed25519 seed from disk."""
    private_seed = decode_base64url(Path(private_key_path).read_text().strip())
    if len(private_seed) != 32:
        raise ValueError("private key seed must be exactly 32 bytes")
    return private_seed


def payload_to_pretty_json(payload: dict[str, Any]) -> str:
    """Render the payload for operator review."""
    return json.dumps(payload, indent=2, sort_keys=True)
