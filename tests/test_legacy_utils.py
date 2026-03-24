from __future__ import annotations

from datetime import datetime

import pytest

from worklogger.legacy_utils import ActivationState, check_activation_status, parse_flexible_date, parse_hour_minute
from worklogger.license_schema import LicenseStatus, LicenseValidationResult


@pytest.mark.parametrize("raw_date", ["12.05.2025", "12/05/2025", "2025-05-12", "12-05-2025"])
def test_parse_flexible_date_formats(raw_date: str) -> None:
    assert parse_flexible_date(raw_date) == "2025-05-12"


def test_parse_flexible_date_datetime_to_object() -> None:
    source = datetime(2025, 5, 12, 8, 0)
    assert parse_flexible_date(source, to_string=False) == source


def test_parse_flexible_date_invalid_returns_none() -> None:
    assert parse_flexible_date("2025/99/99") is None


@pytest.mark.parametrize(
    ("hour_value", "expected"),
    [("9:30", (9, 30)), ("14.45", (14, 45)), ("7", (7, 0)), ("25:00", (0, 0))],
)
def test_parse_hour_minute(hour_value: str, expected: tuple[int, int]) -> None:
    assert parse_hour_minute(hour_value) == expected


@pytest.mark.parametrize(
    ("license_status", "expected_state", "remaining_days"),
    [
        (LicenseStatus.VALID, ActivationState.VALID, 4),
        (LicenseStatus.EXPIRED, ActivationState.EXPIRED, -2),
        (LicenseStatus.INVALID_SIGNATURE, ActivationState.INVALID_SIGNATURE, 0),
        (LicenseStatus.MALFORMED, ActivationState.MALFORMED, 0),
        (LicenseStatus.USERNAME_MISMATCH, ActivationState.USERNAME_MISMATCH, 0),
    ],
)
def test_check_activation_status_maps_verification_result(
    license_status: LicenseStatus,
    expected_state: ActivationState,
    remaining_days: int,
) -> None:
    result = check_activation_status("abc", lambda _: LicenseValidationResult(license_status, remaining_days))
    assert result.status == expected_state
    assert result.value == remaining_days
