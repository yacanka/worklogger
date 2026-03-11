"""Helpers for Jira issue filtering and worklog day summaries."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set


JIRA_STARTED_FORMAT = "%Y-%m-%dT%H:%M:%S.%f%z"
SECONDS_PER_HOUR = 3600


def extract_issue_keys(issues: Sequence[Any]) -> List[str]:
    """Extract non-empty issue keys from Jira issue payloads."""
    return [str(issue.key).strip() for issue in issues if getattr(issue, "key", "")]


def summarize_worklogs_by_day(
    worklogs: Iterable[Any],
    author_ids: Optional[Set[str]] = None,
) -> Dict[str, float]:
    """Aggregate worklog durations per day as hours."""
    totals = defaultdict(float)
    for worklog in worklogs:
        if author_ids and not _is_author_allowed(worklog, author_ids):
            continue
        started = getattr(worklog, "started", None)
        seconds = int(getattr(worklog, "timeSpentSeconds", 0) or 0)
        if not started or seconds <= 0:
            continue
        day_key = datetime.strptime(started, JIRA_STARTED_FORMAT).date().isoformat()
        totals[day_key] += seconds / SECONDS_PER_HOUR
    return dict(sorted(totals.items(), key=lambda item: item[0]))


def _is_author_allowed(worklog: Any, author_ids: Set[str]) -> bool:
    author = getattr(worklog, "author", None)
    candidates = {
        str(getattr(author, "accountId", "")).strip(),
        str(getattr(author, "key", "")).strip(),
        str(getattr(author, "name", "")).strip(),
    }
    return any(candidate and candidate in author_ids for candidate in candidates)
