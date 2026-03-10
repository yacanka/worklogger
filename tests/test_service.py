from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from jira.exceptions import JIRAError

from worklogger.exceptions import ValidationError, WorklogOperationError
from worklogger.models import ExistingWorklog, WorklogEntry
from worklogger.service import WorklogService


@pytest.fixture
def jira_client() -> MagicMock:
    return MagicMock()


@pytest.fixture
def service(jira_client: MagicMock) -> WorklogService:
    return WorklogService(jira_client)


def test_create_worklogs_success(service: WorklogService, jira_client: MagicMock) -> None:
    entry = WorklogEntry("PROJ-1", datetime.now(tz=timezone.utc), "1h", "done")
    success, failed = service.create_worklogs([entry])
    assert (success, failed) == (1, 0)
    jira_client.add_worklog.assert_called_once()


def test_create_worklogs_handles_jira_error(service: WorklogService, jira_client: MagicMock) -> None:
    jira_client.add_worklog.side_effect = JIRAError(status_code=500)
    entry = WorklogEntry("PROJ-1", datetime.now(tz=timezone.utc), "1h")
    success, failed = service.create_worklogs([entry])
    assert (success, failed) == (0, 1)


@pytest.mark.parametrize("issue_key", ["", "INVALID", "A"]) 
def test_create_worklogs_rejects_invalid_issue_key(service: WorklogService, issue_key: str) -> None:
    entry = WorklogEntry(issue_key, datetime.now(tz=timezone.utc), "1h")
    with pytest.raises(ValidationError):
        service.create_worklogs([entry])


def test_create_worklogs_rejects_naive_datetime(service: WorklogService) -> None:
    entry = WorklogEntry("PROJ-1", datetime.now(), "1h")
    with pytest.raises(ValidationError):
        service.create_worklogs([entry])


def test_iter_worklogs_filters_by_author(service: WorklogService, jira_client: MagicMock) -> None:
    jira_client.worklogs.return_value = [
        SimpleNamespace(
            id="1",
            started="2025-01-01T09:00:00.000+0000",
            timeSpent="1h",
            comment="a",
            author=SimpleNamespace(accountId="user-1"),
        ),
        SimpleNamespace(
            id="2",
            started="2025-01-01T10:00:00.000+0000",
            timeSpent="2h",
            comment="b",
            author=SimpleNamespace(accountId="user-2"),
        ),
    ]
    worklogs = list(service.iter_worklogs(["PROJ-1"], author_account_id="user-1"))
    assert len(worklogs) == 1
    assert worklogs[0].worklog_id == "1"


def test_iter_worklogs_raises_for_invalid_payload(service: WorklogService, jira_client: MagicMock) -> None:
    jira_client.worklogs.return_value = [SimpleNamespace(id="1")]
    with pytest.raises(WorklogOperationError):
        list(service.iter_worklogs(["PROJ-1"]))


def test_delete_worklogs_success(service: WorklogService, jira_client: MagicMock) -> None:
    jira_client.worklog.return_value = SimpleNamespace(delete=MagicMock())
    worklog = ExistingWorklog(
        issue_key="PROJ-1",
        worklog_id="1001",
        author_account_id="u1",
        started_at=datetime.now(tz=timezone.utc),
        time_spent="1h",
    )
    success, failed = service.delete_worklogs([worklog])
    assert (success, failed) == (1, 0)


def test_delete_worklogs_handles_jira_error(service: WorklogService, jira_client: MagicMock) -> None:
    delete_mock = MagicMock(side_effect=JIRAError(status_code=403))
    jira_client.worklog.return_value = SimpleNamespace(delete=delete_mock)
    worklog = ExistingWorklog(
        issue_key="PROJ-1",
        worklog_id="1001",
        author_account_id="u1",
        started_at=datetime.now(tz=timezone.utc),
        time_spent="1h",
    )
    success, failed = service.delete_worklogs([worklog])
    assert (success, failed) == (0, 1)
