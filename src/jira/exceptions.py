"""Jira exception compatibility definitions."""


class JIRAError(Exception):
    """Simplified Jira error with optional status code."""

    def __init__(self, text: str = "", status_code: int | None = None) -> None:
        super().__init__(text)
        self.status_code = status_code
