from __future__ import annotations

from datetime import datetime

import pytest

from worklogger.legacy_utils import (
    ActivationState,
    check_activation_status,
    parse_flexible_date,
    parse_hour_minute,
)


@pytest.mark.parametrize("raw_date", ["12.05.2025", "12/05/2025", "2025-05-12", "12-05-2025"])
def test_parse_flexible_date_formats(raw_date: str) -> None:
    assert parse_flexible_date(raw_date) == "2025-05-12"


def test_parse_flexible_date_datetime_to_object() -> None:
    source = datetime(2025, 5, 12, 8, 0)
    parsed = parse_flexible_date(source, to_string=False)
    assert parsed == source


def test_parse_flexible_date_invalid_returns_none() -> None:
    assert parse_flexible_date("2025/99/99") is None


@pytest.mark.parametrize(
    ("hour_value", "expected"),
    [("9:30", (9, 30)), ("14.45", (14, 45)), ("7", (7, 0)), ("25:00", (0, 0))],
)
def test_parse_hour_minute(hour_value: str, expected: tuple[int, int]) -> None:
    assert parse_hour_minute(hour_value) == expected


def test_check_activation_status_valid() -> None:
    result = check_activation_status("abc", lambda _: "12.05.2025", lambda _: 4)
    assert result.status == ActivationState.VALID
    assert result.value == 4


def test_check_activation_status_invalid() -> None:
    result = check_activation_status("abc", lambda _: None, lambda _: 0)
    assert result.status == ActivationState.INVALID
    assert result.to_dict() == {"status": "invalid", "value": 0}


def test_check_activation_status_expired() -> None:
    result = check_activation_status("abc", lambda _: "12.05.2025", lambda _: -2)
    assert result.status == ActivationState.EXPIRED
    assert result.value == -2
