from __future__ import annotations

import base64
import json
from datetime import timedelta
from pathlib import Path

from Activation import current_username
from worklogger.ed25519_py import public_key_from_seed
from worklogger.license_schema import encode_base64url, utc_now
from worklogger.license_signer import build_payload, sign_license
from worklogger.license_verifier import verify_license

TEST_PRIVATE_SEED = bytes(range(1, 33))
TEST_PUBLIC_KEY = public_key_from_seed(TEST_PRIVATE_SEED)


def test_verify_license_valid(tmp_path: Path) -> None:
    private_key, public_key = write_test_keys(tmp_path)
    payload = build_payload(make_fields(30, current_username()))
    license_text = sign_license(payload, str(private_key))
    result = verify_license(license_text, current_username(), public_key)
    assert result.status.value == "valid"
    assert result.remaining_days >= 29


def test_verify_license_expired(tmp_path: Path) -> None:
    private_key, public_key = write_test_keys(tmp_path)
    payload = build_payload(make_fields(-1, current_username()))
    license_text = sign_license(payload, str(private_key))
    result = verify_license(license_text, current_username(), public_key)
    assert result.status.value == "expired"


def test_verify_license_invalid_signature(tmp_path: Path) -> None:
    private_key, public_key = write_test_keys(tmp_path)
    payload = build_payload(make_fields(30, current_username()))
    license_text = sign_license(payload, str(private_key))
    result = verify_license(tamper_payload_segment(license_text), current_username(), public_key)
    assert result.status.value == "invalid_signature"


def test_verify_license_malformed(tmp_path: Path) -> None:
    _, public_key = write_test_keys(tmp_path)
    result = verify_license("not-a-license", current_username(), public_key)
    assert result.status.value == "malformed"


def test_verify_license_username_mismatch(tmp_path: Path) -> None:
    private_key, public_key = write_test_keys(tmp_path)
    payload = build_payload(make_fields(30, "different-user"))
    license_text = sign_license(payload, str(private_key))
    result = verify_license(license_text, current_username(), public_key)
    assert result.status.value == "username_mismatch"


def write_test_keys(tmp_path: Path) -> tuple[Path, Path]:
    private_key = tmp_path / "private.ed25519"
    public_key = tmp_path / "public.ed25519"
    private_key.write_text(encode_base64url(TEST_PRIVATE_SEED))
    public_key.write_text(encode_base64url(TEST_PUBLIC_KEY))
    return private_key, public_key


def make_fields(days: int, username: str) -> dict[str, object]:
    issued_at = utc_now()
    expires_at = issued_at + timedelta(days=days)
    return {
        "version": 1,
        "license_id": "lic-123",
        "customer_id": "cust-456",
        "product": "worklogger",
        "issued_at": issued_at.isoformat().replace("+00:00", "Z"),
        "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
        "features": ["jira-sync"],
        "username": username,
    }


def tamper_payload_segment(license_text: str) -> str:
    payload_segment, signature_segment = license_text.split(".")
    payload = json.loads(base64.urlsafe_b64decode(payload_segment + "==").decode("utf-8"))
    payload["product"] = "tampered-product"
    tampered_payload = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return f"{encode_base64url(tampered_payload)}.{signature_segment}"
