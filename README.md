# Worklogger

Jira üzerinde worklog oluşturma, silme ve listeleme iş akışlarını yönetmek için çekirdek servis katmanı.

## Kurulum

```bash
python -m venv .venv
source .venv/bin/activate
pip install jira pytest pytest-cov
```

## Windows executable oluşturma

Build işlemini, uygulamanın çalışacağı mimariyle aynı (genellikle 64-bit) güncel
bir CPython kurulumu ve temiz bir sanal ortam kullanarak yapın:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install pyinstaller pillow PyQt5 pandas requests jira certifi cryptography
python -c "import ssl, _ssl; print(ssl.OPENSSL_VERSION)"
build.bat
```

Build öncesinde uygulama ikonunu `icon.png` adıyla proje köküne koyun. İkon
bulunamazsa build script'i anlaşılır bir hata vererek durur. Dağıtılacak dosya
`dist/workLogger.exe` altında tek dosya ve konsol penceresi olmadan oluşur.
Windows binary stripping özellikle `_ssl.pyd` ve bağlı OpenSSL DLL'lerini
bozabildiği için kapalıdır. Kuruma özel
`JIRA_Chain.crt` kullanılıyorsa onu da build öncesinde proje köküne koyun; spec
dosyası sertifikayı executable içine ekler.

Sertifika dosyası, Python'un SSL modülünün veya OpenSSL DLL'lerinin yerine
geçmez. `SSL module is not available` hatası sertifikanın güncelliğinden değil,
build içinde `_ssl` modülü ya da onun OpenSSL DLL'leri bulunmadığından oluşur.
Spec bu modülleri ve gerekli runtime dosyalarını açıkça toplar.

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
