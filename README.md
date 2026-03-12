# Worklogger

Jira üzerinde worklog oluşturma, silme ve listeleme iş akışlarını yönetmek için çekirdek servis katmanı.

## Kurulum

```bash
python -m venv .venv
source .venv/bin/activate
pip install jira pytest pytest-cov
```

## Test

```bash
pytest --cov=src/worklogger --cov-report=term-missing
```

## Kullanım

```python
from datetime import datetime, timezone
from worklogger.service import JiraCredentials, WorklogService
from worklogger.models import WorklogEntry

credentials = JiraCredentials(
    server="https://jira.example.com",
    username="user",
    password="secret",
)
service = WorklogService.from_credentials(credentials)

entry = WorklogEntry(
    issue_key="PROJ-123",
    started_at=datetime.now(timezone.utc),
    time_spent="1h",
    comment="Daily update",
)
service.create_worklogs([entry])
```
