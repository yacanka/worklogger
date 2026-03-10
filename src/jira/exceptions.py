"""Jira exception compatibility definitions."""


from typing import Optional


class JIRAError(Exception):
    """Simplified Jira error with optional status code."""

    def __init__(self, text: str = "", status_code: Optional[int] = None) -> None:
        super().__init__(text)
        self.status_code = status_code
