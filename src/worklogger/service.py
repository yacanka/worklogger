"""Core service layer for Jira worklog management."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Optional
from datetime import datetime

from jira import JIRA
from jira.exceptions import JIRAError

from .exceptions import AuthenticationError, ValidationError, WorklogOperationError
from .models import ExistingWorklog, WorklogEntry

logger = logging.getLogger(__name__)
MIN_ISSUE_KEY_PARTS = 2


@dataclass()
class JiraCredentials:
    """Authentication payload for Jira client."""

    server: str
    username: str
    password: str


class WorklogService:
    """Manage Jira worklogs with isolated business logic."""

    def __init__(self, client: JIRA) -> None:
        self._client = client

    @classmethod
    def from_credentials(cls, credentials: JiraCredentials) -> "WorklogService":
        """Create service with basic authentication.

        Args:
            credentials: Jira connection values.

        Returns:
            Initialized ``WorklogService``.

        Raises:
            AuthenticationError: If client creation fails.
        """
        try:
            client = JIRA(
                options={"server": credentials.server},
                basic_auth=(credentials.username, credentials.password),
                get_server_info=False,
            )
        except JIRAError as exc:
            raise AuthenticationError("Failed to authenticate to Jira") from exc
        return cls(client)

    def create_worklogs(self, entries: Iterable[WorklogEntry]) -> tuple[int, int]:
        """Create worklogs and return success/failure totals."""
        success_count = 0
        failure_count = 0
        for entry in entries:
            self._validate_entry(entry)
            try:
                self._client.add_worklog(
                    issue=entry.issue_key,
                    timeSpent=entry.time_spent,
                    started=entry.started_at,
                    comment=entry.comment,
                )
                success_count += 1
            except JIRAError:
                failure_count += 1
                logger.exception("Create worklog failed for %s", entry.issue_key)
        return success_count, failure_count

    def iter_worklogs(
        self,
        issue_keys: Iterable[str],
        author_account_id: Optional[str] = None,
    ) -> Iterator[ExistingWorklog]:
        """Yield worklogs lazily for provided issues."""
        for issue_key in issue_keys:
            self._validate_issue_key(issue_key)
            for worklog in self._client.worklogs(issue_key):
                normalized = self._to_existing_worklog(issue_key, worklog)
                if author_account_id and normalized.author_account_id != author_account_id:
                    continue
                yield normalized

    def delete_worklogs(self, worklogs: Iterable[ExistingWorklog]) -> tuple[int, int]:
        """Delete worklogs and return success/failure totals."""
        success_count = 0
        failure_count = 0
        for worklog in worklogs:
            try:
                self._client.worklog(worklog.issue_key, worklog.worklog_id).delete()
                success_count += 1
            except JIRAError:
                failure_count += 1
                logger.exception("Delete worklog failed for %s", worklog.worklog_id)
        return success_count, failure_count

    def _validate_entry(self, entry: WorklogEntry) -> None:
        if not entry.time_spent.strip():
            raise ValidationError("time_spent cannot be empty")
        self._validate_issue_key(entry.issue_key)
        if entry.started_at.tzinfo is None:
            raise ValidationError("started_at must be timezone-aware")

    def _validate_issue_key(self, issue_key: str) -> None:
        parts = issue_key.split("-")
        if len(parts) < MIN_ISSUE_KEY_PARTS:
            raise ValidationError(f"Invalid issue key: {issue_key}")

    def _to_existing_worklog(self, issue_key: str, worklog: object) -> ExistingWorklog:
        try:
            author = worklog.author.accountId
            started_at = datetime.strptime(worklog.started, "%Y-%m-%dT%H:%M:%S.%f%z")
            return ExistingWorklog(
                issue_key=issue_key,
                worklog_id=str(worklog.id),
                author_account_id=author,
                started_at=started_at,
                time_spent=str(worklog.timeSpent),
                comment=str(getattr(worklog, "comment", "")),
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise WorklogOperationError("Unexpected Jira worklog payload") from exc
