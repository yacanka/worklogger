"""Reusable utility helpers for the legacy workLogger GUI module."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, Optional, Tuple, Union

logger = logging.getLogger(__name__)
ISO_DATE_FORMAT = "%Y-%m-%d"
HOUR_MIN = 0
HOUR_MAX = 23
MINUTE_MIN = 0
MINUTE_MAX = 59
SUPPORTED_DATE_FORMATS = (
    "%d.%m.%Y",
    "%d/%m/%Y",
    "%Y-%m-%d",
    "%d-%m-%Y",
    "%d %m %Y",
    "%d %B %Y",
    "%d %b %Y",
)


class ActivationState(str, Enum):
    """Known activation outcomes."""

    VALID = "valid"
    EXPIRED = "expired"
    INVALID = "invalid"


@dataclass(slots=True, frozen=True)
class ActivationResult:
    """Activation result payload used by the legacy GUI code."""

    status: ActivationState
    value: int

    def to_dict(self) -> Dict[str, Union[int, str]]:
        """Return dict payload compatible with existing GUI flow."""
        return {"status": self.status.value, "value": self.value}


def parse_flexible_date(
    date_input: Union[str, datetime],
    to_string: bool = True,
) -> Optional[Union[datetime, str]]:
    """Parse supported date values and return normalized output."""
    if isinstance(date_input, datetime):
        return date_input.strftime(ISO_DATE_FORMAT) if to_string else date_input
    for date_format in SUPPORTED_DATE_FORMATS:
        try:
            parsed_date = datetime.strptime(date_input, date_format)
            return parsed_date.strftime(ISO_DATE_FORMAT) if to_string else parsed_date
        except ValueError:
            continue
    logger.warning("Unsupported date format: %s", date_input)
    return None


def parse_hour_minute(hour_value: object) -> tuple[int, int]:
    """Parse `xx:xx`, `xx.xx` or integer hour values safely."""
    normalized = str(hour_value).strip()
    parts = _split_time_parts(normalized)
    if parts is None:
        logger.warning("Invalid hour format: %s", hour_value)
        return HOUR_MIN, MINUTE_MIN
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        logger.warning("Hour parse failed: %s", hour_value)
        return HOUR_MIN, MINUTE_MIN
    return (hour, minute) if _is_valid_time(hour, minute) else (HOUR_MIN, MINUTE_MIN)


def _split_time_parts(normalized_value: str) -> Optional[Tuple[str, str]]:
    if ":" in normalized_value:
        parts = normalized_value.split(":")
        return (parts[0], parts[1]) if len(parts) == 2 else None
    if "." in normalized_value:
        parts = normalized_value.split(".")
        return (parts[0], parts[1]) if len(parts) == 2 else None
    try:
        return str(int(float(normalized_value))), "0"
    except ValueError:
        return None


def _is_valid_time(hour: int, minute: int) -> bool:
    return HOUR_MIN <= hour <= HOUR_MAX and MINUTE_MIN <= minute <= MINUTE_MAX


def check_activation_status(
    key: str,
    convert_code: Callable[[str], Optional[str]],
    check_status: Callable[[str], int],
) -> ActivationResult:
    """Evaluate activation key using injected conversion/status functions."""
    pure_key = convert_code(key)
    if not pure_key:
        return ActivationResult(status=ActivationState.INVALID, value=0)
    remaining_days = check_status(pure_key)
    if remaining_days >= 0:
        return ActivationResult(status=ActivationState.VALID, value=remaining_days)
    return ActivationResult(status=ActivationState.EXPIRED, value=remaining_days)
