"""Legacy activation adapter backed by signed license verification."""

from __future__ import annotations

import getpass
import sys
from pathlib import Path

SRC_PATH = Path(__file__).resolve().parent / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from worklogger.license_schema import LicenseValidationResult
from worklogger.license_verifier import verify_license


def verify_activation_code(license_text: str) -> LicenseValidationResult:
    """Verify a signed license using the embedded public key only."""
    return verify_license(license_text, username=current_username())


def current_username() -> str:
    """Return the active local session username for license binding."""
    return getpass.getuser()
