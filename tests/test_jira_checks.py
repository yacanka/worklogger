from __future__ import annotations

from types import SimpleNamespace

from worklogger.jira_checks import extract_issue_keys, summarize_worklogs_by_day


def test_extract_issue_keys() -> None:
    issues = [SimpleNamespace(key="PROJ-1"), SimpleNamespace(key=" PROJ-2 "), SimpleNamespace()]
    assert extract_issue_keys(issues) == ["PROJ-1", "PROJ-2"]


def test_summarize_worklogs_by_day_filters_author() -> None:
    worklogs = [
        SimpleNamespace(
            started="2026-03-10T09:00:00.000+0000",
            timeSpentSeconds=3600,
            author=SimpleNamespace(accountId="u1"),
        ),
        SimpleNamespace(
            started="2026-03-10T10:00:00.000+0000",
            timeSpentSeconds=1800,
            author=SimpleNamespace(accountId="u2"),
        ),
        SimpleNamespace(
            started="2026-03-11T10:00:00.000+0000",
            timeSpentSeconds=7200,
            author=SimpleNamespace(accountId="u1"),
        ),
    ]
    result = summarize_worklogs_by_day(worklogs, author_ids={"u1"})
    assert result == {"2026-03-10": 1.0, "2026-03-11": 2.0}
