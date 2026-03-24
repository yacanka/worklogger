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


## License Generation (ActivationCodeGenerator)

### 1) Generate Ed25519 keys

```bash
python ActivationCodeGenerator.py generate-keys --output-dir ./license_keys
```

This creates:
- `./license_keys/private_key.ed25519` (keep secret, generator side only)
- `./license_keys/public_key.ed25519` (embed in app at `src/worklogger/keys/public_key.ed25519`)

### 2) Create a signed license token

```bash
python ActivationCodeGenerator.py create-license \
  --private-key ./license_keys/private_key.ed25519 \
  --license-id LIC-2026-0001 \
  --customer-id CUST-100 \
  --product worklogger \
  --days 30 \
  --feature jira-sync \
  --username alice
```

Output:
1. Canonical JSON payload
2. Compact `payload.signature` license token (base64url)

### 3) Activate in application

Paste the generated token into the activation field in the app.

> Security note: never ship `private_key.ed25519` with the client.
