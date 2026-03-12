"""Data models for Jira worklog processing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class WorklogAction(str, Enum):
    """Supported operations for worklogs."""

    CREATE = "create"
    DELETE = "delete"
    LIST = "list"


@dataclass(frozen=True)
class WorklogEntry:
    """Represents a normalized worklog request payload.

    Attributes:
        issue_key: Jira issue key (e.g., PROJ-100).
        started_at: Start datetime with timezone.
        time_spent: Jira duration text (e.g., ``1h 30m``).
        comment: Optional worklog comment.
    """

    issue_key: str
    started_at: datetime
    time_spent: str
    comment: str = ""


@dataclass(frozen=True)
class ExistingWorklog:
    """Represents a worklog record returned by Jira."""

    issue_key: str
    worklog_id: str
    author_account_id: str
    started_at: datetime
    time_spent: str
    comment: str = ""
