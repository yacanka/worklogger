"""Reusable utility helpers for the legacy workLogger GUI module."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, Optional, Tuple, Union

from worklogger.license_schema import LicenseStatus, LicenseValidationResult

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
    INVALID_SIGNATURE = "invalid_signature"
    MALFORMED = "malformed"
    USERNAME_MISMATCH = "username_mismatch"


@dataclass(frozen=True)
class ActivationResult:
    """Activation result payload used by the legacy GUI code."""

    status: ActivationState
    value: int

    def to_dict(self) -> Dict[str, Union[int, str]]:
        """Return dict payload compatible with existing GUI flow."""
        return {"status": self.status.value, "value": self.value}


STATUS_MAP = {
    LicenseStatus.VALID: ActivationState.VALID,
    LicenseStatus.EXPIRED: ActivationState.EXPIRED,
    LicenseStatus.INVALID_SIGNATURE: ActivationState.INVALID_SIGNATURE,
    LicenseStatus.MALFORMED: ActivationState.MALFORMED,
    LicenseStatus.USERNAME_MISMATCH: ActivationState.USERNAME_MISMATCH,
}


def parse_flexible_date(date_input: Union[str, datetime], to_string: bool = True) -> Optional[Union[datetime, str]]:
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


def check_activation_status(key: str, verifier: Callable[[str], LicenseValidationResult]) -> ActivationResult:
    """Evaluate activation key using the signed-license verifier."""
    verification = verifier(key)
    return ActivationResult(status=STATUS_MAP[verification.status], value=verification.remaining_days)
