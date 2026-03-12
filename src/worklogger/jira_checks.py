"""Helpers for Jira issue filtering and worklog day summaries."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from worklogger.legacy_utils import parse_flexible_date


JIRA_STARTED_FORMAT = "%Y-%m-%dT%H:%M:%S.%f%z"
SECONDS_PER_HOUR = 3600


def extract_issue_keys(issues: Sequence[Any]) -> List[str]:
    """Extract non-empty issue keys from Jira issue payloads."""
    return [str(issue.key).strip() for issue in issues if getattr(issue, "key", "")]


def summarize_worklogs_by_day(
    worklogs: Iterable[Any],
    date_range: Tuple[str, str],
    author_ids: Optional[Set[str]] = None,
) -> Dict[str, float]:
    """Aggregate worklog durations per day as hours, including empty days."""

    start_date_str, end_date_str = date_range
    start_date = parse_flexible_date(start_date_str, to_string=False).date()
    end_date = parse_flexible_date(end_date_str, to_string=False).date()

    totals = defaultdict(float)

    for worklog in worklogs:
        if author_ids and not _is_author_allowed(worklog, author_ids):
            continue

        started = getattr(worklog, "started", None)
        seconds = int(getattr(worklog, "timeSpentSeconds", 0) or 0)

        if not started or seconds <= 0:
            continue

        worklog_date = datetime.strptime(started, JIRA_STARTED_FORMAT).date()

        if not (start_date <= worklog_date <= end_date):
            continue

        totals[worklog_date.isoformat()] += seconds / SECONDS_PER_HOUR

    current = start_date
    while current <= end_date:
        key = current.isoformat()
        totals.setdefault(key, 0.0)
        current += timedelta(days=1)

    return dict(sorted(totals.items()))


def _is_author_allowed(worklog: Any, author_ids: Set[str]) -> bool:
    author = getattr(worklog, "author", None)
    candidates = {
        str(getattr(author, "accountId", "")).strip(),
        str(getattr(author, "key", "")).strip(),
        str(getattr(author, "name", "")).strip(),
    }
    return any(candidate and candidate in author_ids for candidate in candidates)
