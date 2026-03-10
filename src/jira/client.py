"""Minimal JIRA client stub used by tests."""

from __future__ import annotations

from .exceptions import JIRAError


class JIRA:
    """Stub Jira client.

    This local class exists for environments where the external `jira` package
    is unavailable. Runtime methods intentionally raise until replaced by mocks.
    """

    def __init__(self, *args, **kwargs) -> None:
        self._args = args
        self._kwargs = kwargs

    def add_worklog(self, *args, **kwargs):
        raise JIRAError("Not implemented in local stub")

    def worklogs(self, issue_key: str):
        raise JIRAError(f"Not implemented for issue {issue_key}")

    def worklog(self, issue_key: str, worklog_id: str):
        raise JIRAError(f"Not implemented for issue {issue_key} worklog {worklog_id}")
