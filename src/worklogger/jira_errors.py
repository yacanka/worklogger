"""User-facing Jira error message helpers."""

from __future__ import annotations

from typing import Any, Iterable

AUTH_STATUS_CODES = {401, 403}


def build_missing_fields_message(missing_fields: Iterable[str]) -> str:
    """Build a consistent missing-required-fields message."""
    normalized_fields = [field for field in missing_fields if str(field).strip()]
    if not normalized_fields:
        return "Zorunlu alanlar doldurulmalıdır."
    return f"Zorunlu alanlar doldurulmalıdır: {', '.join(normalized_fields)}"


def build_auth_message(using_session: bool) -> str:
    """Return a clear authentication error message for UI flows."""
    if using_session:
        return "JSESSIONID geçersiz. Lütfen geçerli bir SessionID girin."
    return "Jira kimlik bilgileri yanlış. Kullanıcı adı/şifreyi kontrol edin."


def extract_jira_error_detail(error: Any) -> str:
    """Extract human-readable detail from Jira SDK exceptions."""
    response = getattr(error, "response", None)
    if response is None:
        return str(error)
    text = getattr(response, "text", "") or ""
    if text and len(text) < 250:
        return text
    reason = getattr(response, "reason", "") or ""
    return reason or str(error)


def build_jira_connection_error(error: Any, using_session: bool) -> str:
    """Map Jira exceptions to user-friendly authentication/connection messages."""
    if getattr(error, "status_code", None) in AUTH_STATUS_CODES:
        return build_auth_message(using_session)
    detail = extract_jira_error_detail(error)
    return f"Jira bağlantı hatası: {detail}"
