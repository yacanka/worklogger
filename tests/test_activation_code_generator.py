from __future__ import annotations

from pathlib import Path

from ActivationCodeGenerator import generate_keys
from worklogger.license_schema import decode_base64url


def test_generate_keys_writes_expected_files(tmp_path: Path) -> None:
    private_path, public_path = generate_keys(str(tmp_path))
    assert private_path.exists()
    assert public_path.exists()
    assert len(decode_base64url(private_path.read_text().strip())) == 32
    assert len(decode_base64url(public_path.read_text().strip())) == 32
