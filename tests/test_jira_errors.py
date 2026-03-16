from __future__ import annotations

from types import SimpleNamespace

from worklogger.jira_errors import (
    build_auth_message,
    build_jira_connection_error,
    build_missing_fields_message,
)


class FakeJiraError(Exception):
    def __init__(self, status_code: int | None = None, response=None) -> None:
        super().__init__("jira error")
        self.status_code = status_code
        self.response = response


def test_missing_fields_message_includes_fields() -> None:
    message = build_missing_fields_message(["Jira Server", "Şifre"])
    assert message == "Zorunlu alanlar doldurulmalıdır: Jira Server, Şifre"


def test_auth_message_for_session() -> None:
    assert "JSESSIONID geçersiz" in build_auth_message(using_session=True)


def test_auth_message_for_username_password() -> None:
    assert "Jira kimlik bilgileri yanlış" in build_auth_message(using_session=False)


def test_connection_error_returns_auth_message_for_unauthorized() -> None:
    error = FakeJiraError(status_code=401)
    message = build_jira_connection_error(error, using_session=False)
    assert "Jira kimlik bilgileri yanlış" in message


def test_connection_error_uses_response_text_for_non_auth_errors() -> None:
    response = SimpleNamespace(text="rate limited", reason="Too Many Requests")
    error = FakeJiraError(status_code=429, response=response)
    message = build_jira_connection_error(error, using_session=True)
    assert message == "Jira bağlantı hatası: rate limited"
