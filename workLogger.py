import sys
import logging
import json
from pathlib import Path
from typing import Optional, Dict, Any, Union
from enum import Enum

from PyQt5 import QtCore, QtWidgets, QtGui
from PyQt5.QtCore import pyqtSignal, QThread

import pandas as pd
import os
from requests.exceptions import RequestException
from urllib.parse import urlparse
from datetime import datetime, timedelta, timezone, date

# Windows registry için
try:
    import winreg
except ImportError:
    winreg = None

# jira kütüphanesi
from jira import JIRA
from jira.exceptions import JIRAError

# activation
from Activation import ConvertActivationCode, CheckActivationStatus
SRC_PATH = Path(__file__).resolve().parent / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from worklogger.legacy_utils import check_activation_status, parse_flexible_date, parse_hour_minute
from worklogger.jira_checks import extract_issue_keys, summarize_worklogs_by_day

# ----- Logging Setup -----
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ----- Constants -----
REG_PATH = r"Software\YaCanKa\Worklogger"
LOCAL_TZ = timezone(timedelta(hours=3))  # UTC+3
WEEKDAYS = 5  # Pazartesi-Cuma
DEFAULT_TIMEZONE_OFFSET = 3  # saat
JIRA_CONNECTION_TIMEOUT_SECONDS = 10
JIRA_CLIENT_MAX_RETRIES = 0

class WorklogMode(Enum):
    """Worklog işlem modları"""
    CREATE = "create"
    DELETE = "delete"

# ----- Resource -----
def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

# ------------ Convert -------------

def date_to_iso_date(date_input: Union[str, datetime], toString: bool = True) -> Optional[Union[datetime, str]]:
    """Tarihi ISO formatına çevir."""
    return parse_flexible_date(date_input, to_string=toString)

def parse_jira_started(started: str) -> datetime:
    """JIRA formatındaki başlangıç zamanını datetime'a çevirme"""
    return datetime.strptime(started, "%Y-%m-%dT%H:%M:%S.%f%z")


def in_range(day: date, start_date: datetime, end_date: datetime) -> bool:
    """Verilen günün tarih aralığında olup olmadığını kontrol et"""
    return start_date.date() <= day <= end_date.date()

def parse_JIRA_error(e: JIRAError) -> str:
    """Parse a dictionary into a JIRAError."""
    response = getattr(e, "response", None)
    if response is not None:
        body = (response.text or "").strip()
        if body and len(body) < 180:
            return body
        if response.reason:
            return str(response.reason)
        if response.status_code:
            return f"HTTP {response.status_code}"
    return str(getattr(e, "text", "") or str(e) or "Bilinmeyen JIRA hatası")


def build_jira_options(server: str, cert: Union[str, bool]) -> dict[str, Union[str, bool]]:
    """Create Jira options for server and certificate validation."""
    return {
        "server": server,
        "verify": cert,
    }


def is_valid_server_url(server: str) -> bool:
    """Return True only for absolute http/https server URLs."""
    parsed = urlparse(server.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

# ===================== AKTİVASYON =====================

def check_activation(key: str) -> Dict[str, Any]:
    """Aktivasyon kodunu kontrol et."""
    result = check_activation_status(
        key=key,
        convert_code=ConvertActivationCode,
        check_status=CheckActivationStatus,
    )
    return result.to_dict()

# ----- Worker Thread -----

class WorklogWorker(QThread):
    """Tablo verisinden Jira workloglarını yönetmek için worker thread"""
    
    startedSignal = pyqtSignal(str)
    statusSignal = pyqtSignal(str)
    progressSignal = pyqtSignal(int)
    errorSignal = pyqtSignal(str)
    finishedSignal = pyqtSignal(int, int)  # (success_count, fail_count)

    def __init__(
        self,
        jira_server: str,
        table_data: pd.DataFrame,
        jsession_id: str,
        username: str,
        password: str,
        start_date: str,
        end_date: str,
        worklog_mode: str,
        include_weekends: bool,
        parent=None
    ):
        super().__init__(parent)
        self.jira_server = jira_server
        self.table_data = table_data.copy()
        self.jsession_id = jsession_id
        self.username = username
        self.password = password
        self.start_date = start_date
        self.end_date = end_date
        self.worklog_mode = worklog_mode
        self.include_weekends = include_weekends
        self._cancel = False
        self._jira: Optional[JIRA] = None

    def cancel(self):
        """İşlemi iptal et"""
        self._cancel = True

    def _parse_hour_time(self, hour_str: str) -> tuple[int, int]:
        """Saati parse et ve (hour, minute) döndür."""
        return parse_hour_minute(hour_str)

    def _setup_jira_connection(self) -> Optional[JIRA]:
        """Jira bağlantısını kur ve doğrula"""
        try:
            if not is_valid_server_url(self.jira_server):
                self.errorSignal.emit("JIRA sunucu URL'i geçersiz. Örnek: https://jira.example.com")
                return None

            cert = False
            if os.path.exists(resource_path("JIRA_Chain.crt")):
                cert = resource_path("JIRA_Chain.crt")

            # JSESSIONID varsa, token ile; yoksa username/password ile bağlan
            options = build_jira_options(self.jira_server, cert)
            if self.jsession_id:
                jira = JIRA(
                    options=options,
                    get_server_info=False,
                    timeout=JIRA_CONNECTION_TIMEOUT_SECONDS,
                    max_retries=JIRA_CLIENT_MAX_RETRIES,
                )
                
                # Session ID'yi ayarla
                jira._session.cookies.set(
                    "JSESSIONID",
                    self.jsession_id,
                    domain=urlparse(self.jira_server).netloc,
                    path="/"
                )
                jira._session.headers.update({
                    "Accept": "application/json",
                    "X-Atlassian-Token": "no-check"
                })
            else:
                # Username ve password ile bağlan
                jira = JIRA(
                    options=options,
                    basic_auth=(self.username, self.password),
                    get_server_info=True,
                    timeout=JIRA_CONNECTION_TIMEOUT_SECONDS,
                    max_retries=JIRA_CLIENT_MAX_RETRIES,
                )

            return jira
        except JIRAError as e:
            logger.error(f"Jira bağlantısı kurulamadı: {e}")
            status_code = getattr(getattr(e, "response", None), "status_code", None)
            if status_code == 401 and not self.jsession_id:
                self.errorSignal.emit("Geçersiz giriş.")
            else:
                self.errorSignal.emit(f"Jira bağlantı hatası: {parse_JIRA_error(e)}")
            return None
        except RequestException as e:
            logger.error(f"Jira bağlantısı timeout/ağ hatası: {e}")
            self.errorSignal.emit(
                f"Jira bağlantısı {JIRA_CONNECTION_TIMEOUT_SECONDS} saniyede zaman aşımına uğradı veya ağ hatası oluştu."
            )
            return None
        except Exception as e:
            logger.error(f"Jira bağlantısı sırasında bir hata oluştu: {e}")
            self.errorSignal.emit(f"Jira bağlantısı sırasında bir hata oluştu: {str(e)}")
            return None

    def _validate_excel_columns(self, df: pd.DataFrame, mode: str) -> bool:
        """Excel kolon doğrulaması"""
        required_columns = {
            WorklogMode.CREATE.value: {"issueKey", "startHour", "timeSpent", "comment"},
            WorklogMode.DELETE.value: {"issueKey"}
        }
        
        cols = set(df.columns)
        missing = required_columns.get(mode, set()) - cols
        
        if missing:
            error_msg = f"Excel'de eksik kolon(lar): {', '.join(missing)}"
            logger.error(error_msg)
            self.errorSignal.emit(error_msg)
            return False
        
        return True

    def _process_create_mode(self, df: pd.DataFrame, jira: JIRA, my_account_id: str, start_date: datetime, end_date: datetime) -> tuple:
        """Worklog oluştur modu işlemesi"""
        ok_count = 0
        fail_count = 0
        total = len(df)

        self.statusSignal.emit("Worklog ekleniyor...")
        self.statusSignal.emit("- - - - -")

        current_date = start_date
        while current_date.date() <= end_date.date():
            if self._cancel:
                self.statusSignal.emit("İşlem iptal edildi.")
                break

            if self.include_weekends or current_date.weekday() < WEEKDAYS:
                self.statusSignal.emit(f"Mevcut tarih: {current_date.strftime('%d.%m.%Y')}")
                
                for i, (_, row) in enumerate(df.iterrows()):
                    if self._cancel:
                        break

                    try:
                        issue_key = str(row["issueKey"]).strip()
                        comment = str(row["comment"]) if not pd.isna(row["comment"]) else ""
                        
                        # Saati parse et (xx:xx veya xx.xx formatı desteklenir)
                        hour, minute = self._parse_hour_time(row["startHour"])
                        
                        start_time = current_date.replace(
                            hour=hour,
                            minute=minute,
                            second=0,
                            microsecond=0
                        ).replace(tzinfo=LOCAL_TZ)

                        time_spent = None
                        if "timeSpent" in df.columns and not pd.isna(row.get("timeSpent")):
                            time_spent = str(row["timeSpent"]).strip()

                        self.statusSignal.emit(f"[{i+1}/{total}] {issue_key} için worklog ekleniyor...")

                        jira.add_worklog(
                            issue=issue_key,
                            timeSpent=time_spent,
                            started=start_time,
                            comment=comment,
                            adjustEstimate="auto"
                        )
                        ok_count += 1
                        self.statusSignal.emit(f"✓ {issue_key} -> eklendi.")
                        
                    except JIRAError as e:
                        fail_count += 1
                        logger.error(f"JIRA hatası: {e}")
                        self.statusSignal.emit(f"✗ {issue_key} -> JIRA HATASI: {str(e)}")
                    except Exception as e:
                        fail_count += 1
                        logger.error(f"Beklenmeyen hata: {e}", exc_info=True)
                        self.statusSignal.emit(f"✗ {issue_key} -> HATA: {str(e)}")

                    # İlerleme güncelle
                    pct = int(((i + 1) / total) * 100)
                    self.progressSignal.emit(pct)

                self.statusSignal.emit("- - - - -")

            current_date += timedelta(days=1)

        return ok_count, fail_count

    def _process_delete_mode(self, df: pd.DataFrame, jira: JIRA, my_account_id: str, start_date: datetime, end_date: datetime) -> tuple:
        """Worklog silme modu işlemesi"""
        ok_count = 0
        fail_count = 0
        total_items = len(df)

        self.statusSignal.emit("Worklog siliniyor...")

        for issue_idx, (_, row) in enumerate(df.iterrows()):
            if self._cancel:
                self.statusSignal.emit("İşlem iptal edildi.")
                break

            try:
                issue_key = str(row["issueKey"]).strip()
                
                worklogs = jira.worklogs(issue_key)
                worklogs_to_delete = []

                # Silinecek worklogları filtrele
                for wl in worklogs:
                    try:
                        author = getattr(wl, "author", None)
                        if not author:
                            continue
                            
                        author_account_id = getattr(author, "key", None)
                        
                        # Sadece mevcut kullanıcının worklogları
                        if author_account_id != my_account_id:
                            continue

                        started_str = getattr(wl, "started", None)
                        if not started_str:
                            continue

                        started_dt = parse_jira_started(started_str)
                        if not in_range(started_dt.date(), start_date, end_date):
                            continue

                        worklogs_to_delete.append(wl)
                    except Exception as e:
                        logger.warning(f"Worklog filtresi hatası: {e}")
                        continue

                # Worklogları sil
                for del_idx, wl in enumerate(worklogs_to_delete):
                    try:
                        wl.delete()
                        ok_count += 1
                        time_spent = getattr(wl, "timeSpent", "Unknown")
                        comment = getattr(wl, "comment", "")
                        self.statusSignal.emit(
                            f"✓ {issue_key} -> {wl.id} - {time_spent} -> silindi: {comment}"
                        )
                    except JIRAError as e:
                        fail_count += 1
                        logger.error(f"JIRA silme hatası: {e}")
                        self.statusSignal.emit(f"✗ {issue_key} -> JIRA HATASI: {str(e)}")
                    except Exception as e:
                        fail_count += 1
                        logger.error(f"Silme hatası: {e}")
                        self.statusSignal.emit(f"✗ {issue_key} -> HATA: {str(e)}")

                    # İlerleme güncelle
                    if worklogs_to_delete:
                        pct = int(((del_idx + 1) / len(worklogs_to_delete)) * 100)
                        self.progressSignal.emit(pct)

            except Exception as e:
                fail_count += 1
                logger.error(f"Issue işleme hatası: {e}", exc_info=True)
                self.statusSignal.emit(f"✗ Sorun oluştu: {str(e)}")

        return ok_count, fail_count

    def run(self):
        """Ana thread işlemi"""
        try:
            logger.info("Worklog işlemesi başlatılıyor")
            self.statusSignal.emit("Tablo verisi hazırlanıyor...")

            df = self.table_data.copy()

            # Kolon doğrulaması
            if not self._validate_excel_columns(df, self.worklog_mode):
                return

            total = len(df.index)
            if total == 0:
                self.statusSignal.emit("Excel boş görünüyor, işlenecek satır yok.")
                self.progressSignal.emit(100)
                self.finishedSignal.emit(0, 0)
                return

            self.statusSignal.emit(f"{total} satır bulundu.")

            # Jira bağlantısı kur
            self.statusSignal.emit("Jira bağlantısı kuruluyor...")
            jira = self._setup_jira_connection()
            if not jira:
                return

            # Kullanıcı bilgisi al
            try:
                me = jira.myself()
                my_account_id = me.get("key")
                if not my_account_id:
                    raise RuntimeError("Kullanıcı hesap ID'si alınamadı.")
                self.statusSignal.emit(f"{me.get('displayName')} olarak bağlandı.")
            except JIRAError as e:
                logger.error(f"Kullanıcı bilgisi hatası: {e}")
                message = parse_JIRA_error(e)
                status_code = getattr(getattr(e, "response", None), "status_code", None)
                if status_code == 401 and not self.jsession_id:
                    self.errorSignal.emit("Geçersiz giriş.")
                elif status_code == 401:
                    self.errorSignal.emit("JSESSIONID geçersiz veya süresi dolmuş.")
                else:
                    self.errorSignal.emit(f"Kullanıcı bilgisi alınamadı: {message}")
                return
            except Exception as e:
                logger.error(f"Kullanıcı bilgisi hatası: {e}")
                self.errorSignal.emit(f"Kullanıcı bilgisi alınamadı: {str(e)}")
                return

            # Tarih aralığını ayrıştır
            start_date = date_to_iso_date(self.start_date, toString=False)
            end_date = date_to_iso_date(self.end_date, toString=False)
            
            if not start_date or not end_date:
                self.errorSignal.emit("Tarih formatı hatalı.")
                return

            # Moda göre işlemi çalıştır
            if self.worklog_mode == WorklogMode.CREATE.value:
                ok_count, fail_count = self._process_create_mode(df, jira, my_account_id, start_date, end_date)
            elif self.worklog_mode == WorklogMode.DELETE.value:
                ok_count, fail_count = self._process_delete_mode(df, jira, my_account_id, start_date, end_date)
            else:
                raise ValueError(f"Bilinmeyen mod: {self.worklog_mode}")

            logger.info(f"İşlem tamamlandı: {ok_count} başarılı, {fail_count} başarısız")
            self.finishedSignal.emit(ok_count, fail_count)

        except Exception as e:
            logger.error(f"Kritik hata: {e}", exc_info=True)
            self.errorSignal.emit(f"Kritik hata: {str(e)}")


class AssigneeIssueCheckWorker(QThread):
    """Assignee issue kontrolü ve worklog özeti için worker thread."""

    statusSignal = pyqtSignal(str)
    errorSignal = pyqtSignal(str)
    finishedSignal = pyqtSignal(object)

    def __init__(
        self,
        jira_server: str,
        jsession_id: str,
        username: str,
        password: str,
        start_date: str,
        end_date: str,
        parent=None,
    ):
        super().__init__(parent)
        self.jira_server = jira_server
        self.jsession_id = jsession_id
        self.username = username
        self.password = password
        self.start_date = start_date
        self.end_date = end_date

    def _setup_jira_connection(self) -> JIRA:
        try:
            if not is_valid_server_url(self.jira_server):
                self.errorSignal.emit("JIRA sunucu URL'i geçersiz. Örnek: https://jira.example.com")
                return None

            cert = False
            if os.path.exists(resource_path("JIRA_Chain.crt")):
                cert = resource_path("JIRA_Chain.crt")

            # JSESSIONID varsa, token ile; yoksa username/password ile bağlan
            options = build_jira_options(self.jira_server, cert)
            if self.jsession_id:
                jira = JIRA(
                    options=options,
                    get_server_info=False,
                    timeout=JIRA_CONNECTION_TIMEOUT_SECONDS,
                    max_retries=JIRA_CLIENT_MAX_RETRIES,
                )
                
                # Session ID'yi ayarla
                jira._session.cookies.set(
                    "JSESSIONID",
                    self.jsession_id,
                    domain=urlparse(self.jira_server).netloc,
                    path="/"
                )
                jira._session.headers.update({
                    "Accept": "application/json",
                    "X-Atlassian-Token": "no-check"
                })
            else:
                # Username ve password ile bağlan
                jira = JIRA(
                    options=options,
                    basic_auth=(self.username, self.password),
                    get_server_info=True,
                    timeout=JIRA_CONNECTION_TIMEOUT_SECONDS,
                    max_retries=JIRA_CLIENT_MAX_RETRIES,
                )

            return jira
        except JIRAError as e:
            logger.error(f"Jira bağlantısı kurulamadı: {e}")
            status_code = getattr(getattr(e, "response", None), "status_code", None)
            if status_code == 401 and not self.jsession_id:
                self.errorSignal.emit("Geçersiz giriş.")
            else:
                self.errorSignal.emit(f"Jira bağlantı hatası: {parse_JIRA_error(e)}")
            return None
        except RequestException as e:
            logger.error(f"Jira bağlantısı timeout/ağ hatası: {e}")
            self.errorSignal.emit(
                f"Jira bağlantısı {JIRA_CONNECTION_TIMEOUT_SECONDS} saniyede zaman aşımına uğradı veya ağ hatası oluştu."
            )
            return None
        except Exception as e:
            logger.error(f"Jira bağlantısı kurulamadı: {e}")
            self.errorSignal.emit(f"Jira bağlantı hatası: {str(e)}")
            return None
        
    def _fetch_filtered_issues(self, jira: JIRA) -> list:
        jql = (
            'assignee = currentUser() AND issuetype = Sub-task '
            'AND status = "In Progress" AND duedate > startOfDay()'
        )
        return jira.search_issues(jql, maxResults=300)

    def _collect_issue_worklogs(self, jira: JIRA, issue_keys: list) -> tuple[list, list]:
        worklogs = []
        warnings = []
        for issue_key in issue_keys:
            try:
                worklogs.extend(jira.worklogs(issue_key))
            except Exception as exc:
                logger.warning(f"Worklog alınamadı {issue_key}: {exc}")
                warnings.append(f"⚠ {issue_key} için worklog okunamadı")
        return worklogs, warnings

    def run(self):
        try:
            self.statusSignal.emit("🔎 Uygun issue'lar sorgulanıyor...")
            jira = self._setup_jira_connection()
            me = jira.myself()
            issues = self._fetch_filtered_issues(jira)
            issue_keys = extract_issue_keys(issues)
            self.statusSignal.emit("🗓 Worklog takvimi inceleniyor...")
            worklogs, warnings = self._collect_issue_worklogs(jira, issue_keys)
            author_ids = {
                str(me.get("accountId", "")).strip(),
                str(me.get("key", "")).strip(),
                str(me.get("name", "")).strip(),
            }
            daily_totals = summarize_worklogs_by_day(
                worklogs,
                (self.start_date, self.end_date),
                author_ids=author_ids,
            )
            self.finishedSignal.emit(
                {
                    "issue_keys": issue_keys,
                    "daily_totals": daily_totals,
                    "warnings": warnings,
                }
            )
        except Exception as exc:
            logger.error(f"Kontrol işlemi hatası: {exc}", exc_info=True)
            self.errorSignal.emit(f"Kontrol işlemi başarısız: {exc}")


# ---------- UI ----------

class MultilineTableDelegate(QtWidgets.QStyledItemDelegate):
    """Multiline metin desteği olan table delegate"""
    
    def sizeHint(self, option, index):
        """Hücrenin boyutunu belirle"""
        size = super().sizeHint(option, index)
        text = index.data()
        if text:
            # Metni sarar ve yüksekliği hesapla
            doc = QtGui.QTextDocument()
            doc.setTextWidth(size.width())
            doc.setPlainText(str(text))
            return QtCore.QSize(size.width(), int(doc.size().height()) + 4)
        return size
    
    def createEditor(self, parent, option, index):
        """Düzenleme widget'ı oluştur"""
        editor = QtWidgets.QPlainTextEdit(parent)
        editor.setMaximumHeight(150)
        editor.setWordWrapMode(QtGui.QTextOption.WordWrap)
        return editor
    
    def setEditorData(self, editor, index):
        """Editöre veriyi yaz"""
        text = index.data()
        editor.setPlainText(str(text) if text else "")
    
    def setModelData(self, editor, model, index):
        """Model'e veriyi geri yaz"""
        model.setData(index, editor.toPlainText())


class ExcelStyleTable(QtWidgets.QTableWidget):
    """Excel benzeri veri giriş tablosu"""
    
    # CREATE modu için sütunlar
    CREATE_COLUMNS = ["Issue Key", "Start Hour", "Time Spent", "Comment"]
    # DELETE modu için sütunlar
    DELETE_COLUMNS = ["Issue Key"]
    MAX_VISIBLE_ROWS = 10  # Maksimum görüntülenecek satır sayısı
    ROW_HEIGHT = 42  # Her satırın yüksekliği
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.mode = WorklogMode.CREATE.value
        # Multiline delegate'i ayarla
        self.multiline_delegate = MultilineTableDelegate(self)
        self._last_clicked_index = QtCore.QModelIndex()  # Son tıklanan index'i takip et
        self.setup_table()
    
    def setup_table(self):
        """Tabloyu başlat"""
        self.setColumnCount(4)  # Maksimum sütun sayısı
        self.setRowCount(1)     # Başlangıçta 1 satır
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.setAlternatingRowColors(True)
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setFixedHeight(26)  # Başlık yüksekliğini azalt
        self.verticalHeader().setDefaultSectionSize(self.ROW_HEIGHT)
        
        # Sabit yükseklik ayarla (max 6 satır + header)
        header_height = self.horizontalHeader().height()
        total_height = header_height + (self.MAX_VISIBLE_ROWS * self.ROW_HEIGHT) + 8
        self.setMaximumHeight(total_height)
        self.setMinimumHeight(header_height + self.ROW_HEIGHT)
        self.setMinimumWidth(520)
        
        self._update_columns_for_mode(WorklogMode.CREATE.value)
        self._setup_styling()

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        """Mouse press event'ini yakala ve seçimi kaldır"""
        # Tıklanan noktadaki item'ı kontrol et
        index = self.indexAt(event.pos())
        
        # Eğer geçersiz bir index ise (boş alan), seçimi kaldır
        if not index.isValid():
            self.clearSelection()
            self.clearFocus()
            self._last_clicked_index = None
            return
        
        # Eğer zaten seçili satırın aynı hücresine tıklandıysa seçimi kaldır
        if (self._last_clicked_index is not None and
            self._last_clicked_index.row() == index.row() and
            self._last_clicked_index.column() == index.column()):
            self.clearSelection()
            self.clearFocus()
            self._last_clicked_index = None
            return
        
        # Aksi takdirde normal davranış
        super().mousePressEvent(event)
        self._last_clicked_index = self.indexAt(event.pos())
    
    def _setup_styling(self):
        """Tablo stilini ayarla"""
        self.setStyleSheet("""
            QTableWidget {
                background-color: #FFFFFF;
                gridline-color: #D0D0D0;
                border: 1px solid #CCCCCC;
            }
            QTableWidget::item {
                padding: 5px;
                border: none;
            }
            QTableWidget::item:selected {
                background-color: #0078D4;
                color: white;
            }
            QHeaderView::section {
                background-color: #E8E8E8;
                padding: 5px;
                border: 1px solid #D0D0D0;
                font-weight: bold;
            }
        """)
    
    def _apply_cell_alignment(self):
        """Hücrelerin hizalamasını ayarla"""
        # Tüm hücreleri dolaş
        for row in range(self.rowCount()):
            for col in range(self.columnCount()):
                item = self.item(row, col)
                if item:
                    header = self.horizontalHeaderItem(col).text()
                    
                    # Issue Key, Start Hour, Time Spent sütunlarını ortala
                    if header in ["Issue Key", "Start Hour", "Time Spent"]:
                        item.setTextAlignment(QtCore.Qt.AlignCenter)
                    # Comment sütunu sol ve ortada hizala
                    elif header == "Comment":
                        item.setTextAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
    
    def set_mode(self, mode: str):
        """Tabloyu moda göre ayarla"""
        self.mode = mode
        self._update_columns_for_mode(mode)
    
    def _update_columns_for_mode(self, mode: str):
        """Moda göre sütunları güncelle"""
        if mode == WorklogMode.CREATE.value:
            columns = self.CREATE_COLUMNS
        else:
            columns = self.DELETE_COLUMNS
        
        self.setColumnCount(len(columns))
        self.setHorizontalHeaderLabels(columns)
        
        # Tooltip metinleri
        tooltips = {
            "Issue Key": "JIRA issue key'i (örn: KMIT-1234)",
            "Start Hour": "Worklog başlangıç saati (örn: 9, 9:00, 9.00, 14:45, 14.45)",
            "Time Spent": "Harcanan süre (örn: 2h, 30m, 1h 30m)",
            "Comment": "Worklog açıklaması (boş da bırakılabilir)"
        }
        
        # Sütun genişliklerini ayarla ve tooltip ekle
        for i, col in enumerate(columns):
            if col == "Issue Key":
                self.setColumnWidth(i, 90)
                # Hücreleri ortala
            elif col == "Start Hour":
                self.setColumnWidth(i, 80)
                # Hücreleri ortala
            elif col == "Time Spent":
                self.setColumnWidth(i, 90)
                # Hücreleri ortala
            elif col == "Comment":
                self.setColumnWidth(i, 200)
                # Multiline delegate'i Comment sütununa ayarla
                self.setItemDelegateForColumn(i, self.multiline_delegate)
            
            # Başlık widget'ına tooltip ekle
            header_item = self.horizontalHeaderItem(i)
            if header_item and col in tooltips:
                header_item.setToolTip(tooltips[col])
        
        # Hücreleri ortalaması için tüm hücrelere alignment ayarla
        self._apply_cell_alignment()
    
    def get_data_as_dataframe(self) -> pd.DataFrame:
        """Tablo verisini pandas DataFrame'e çevir"""
        data = []
        
        for row in range(self.rowCount()):
            row_data = {}
            for col in range(self.columnCount()):
                header = self.horizontalHeaderItem(col).text()
                item = self.item(row, col)
                value = item.text() if item else ""
                
                # Başlık adını DataFrame sütununa dönüştür
                column_name = {
                    "Issue Key": "issueKey",
                    "Start Hour": "startHour",
                    "Time Spent": "timeSpent",
                    "Comment": "comment"
                }.get(header, header)
                
                row_data[column_name] = value
            
            # Boş olmayan satırları ekle
            if any(row_data.values()):
                data.append(row_data)
        
        return pd.DataFrame(data)
    
    def add_empty_row(self):
        """Tabloya boş satır ekle"""
        self.insertRow(self.rowCount())
        # Yeni satırın hizalamasını ayarla
        self._apply_cell_alignment()
    
    def remove_selected_row(self):
        """Seçili satırı sil"""
        current_row = self.currentRow()
        if current_row >= 0:
            self.removeRow(current_row)
    
    def clear_data(self):
        """Tüm veriyi temizle ve 1 satıra dön"""
        self.setRowCount(1)
        for row in range(self.rowCount()):
            for col in range(self.columnCount()):
                self.setItem(row, col, QtWidgets.QTableWidgetItem(""))
    
    def load_from_dataframe(self, df: pd.DataFrame):
        """DataFrame'den verileri tabloya yükle"""
        if df.empty:
            return
        
        # Satır sayısını ayarla
        self.setRowCount(len(df))
        
        # Sütun header'larını al
        headers = [self.horizontalHeaderItem(i).text() for i in range(self.columnCount())]
        
        # DataFrame sütun adlarını tablo sütun adlarına map et
        column_reverse_mapping = {
            "Issue Key": "issueKey",
            "Start Hour": "startHour",
            "Time Spent": "timeSpent",
            "Comment": "comment"
        }
        
        # Tablo sütunlarına uygun DataFrame sütunlarını bulup doldur
        for row_idx, (_, row) in enumerate(df.iterrows()):
            for col_idx, header in enumerate(headers):
                # Header'a karşılık gelen DataFrame sütun adını bul
                df_col_name = column_reverse_mapping.get(header)
                
                if df_col_name and df_col_name in row:
                    value = row[df_col_name]
                    text = str(value) if pd.notna(value) else ""
                else:
                    text = ""
                
                item = QtWidgets.QTableWidgetItem(text)
                
                # Hücre hizalamasını ayarla
                if header in ["Issue Key", "Start Hour", "Time Spent"]:
                    item.setTextAlignment(QtCore.Qt.AlignCenter)
                elif header == "Comment":
                    item.setTextAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

                self.setItem(row_idx, col_idx, item)

    def import_from_excel(self) -> bool:
        """Excel dosyasından veri içe aktar"""
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            None,
            "Excel dosyasını seç",
            "",
            "Excel Dosyaları (*.xlsx *.xls)"
        )
        
        if not file_path:
            return False
        
        try:
            # Excel dosyasını oku
            df = pd.read_excel(file_path)
            
            if df.empty:
                QtWidgets.QMessageBox.warning(
                    None,
                    "Uyarı",
                    "Excel dosyası boş görünüyor."
                )
                return False
            
            # Gerekli sütunları kontrol et (en azından Issue Key olmalı)
            required_columns = {"issueKey"}
            available_columns = set(df.columns.str.lower())
            
            # Sütun adlarını normalize et (büyük/küçük harf fark etmez)
            df.columns = df.columns.str.lower()
            
            # issueKey sütunun mevcut olup olmadığını kontrol et
            issue_key_variants = ["issuekey", "issue key", "key", "issuenumber"]
            issue_key_col = None
            for variant in issue_key_variants:
                if variant in available_columns:
                    issue_key_col = variant
                    df = df.rename(columns={variant: "issuekey"})
                    break
            
            if issue_key_col is None:
                QtWidgets.QMessageBox.critical(
                    None,
                    "Hata",
                    "Excel dosyasında 'Issue Key' sütunu bulunamadı.\n"
                    "Dosyada şu sütunlardan biri olmalı:\n"
                    "issueKey, Issue Key, Key"
                )
                return False
            
            # Opsiyonel sütunları map et
            column_mapping = {
                "issuekey": "issueKey",
                "starthour": "startHour",
                "start hour": "startHour",
                "hour": "startHour",
                "timespent": "timeSpent",
                "time spent": "timeSpent",
                "duration": "timeSpent",
                "comment": "comment",
                "description": "comment",
                "description": "comment"
            }
            
            # Sütun adlarını standart hale getir
            renamed_cols = {}
            for old_col in df.columns:
                if old_col.lower() in column_mapping:
                    renamed_cols[old_col] = column_mapping[old_col.lower()]
            
            df = df.rename(columns=renamed_cols)
            
            # İhtiyaç olan sütunları seç
            needed_cols = ["issueKey", "startHour", "timeSpent", "comment"]
            cols_to_use = [col for col in needed_cols if col in df.columns]
            
            if "issueKey" not in cols_to_use:
                QtWidgets.QMessageBox.critical(
                    None,
                    "Hata",
                    "Issue Key sütunu işlenemedi."
                )
                return False
            
            df_filtered = df[cols_to_use].copy()
            
            # NaN değerleri boş string'e çevir
            df_filtered = df_filtered.fillna("")
            
            # Tabloya yükle
            self.load_from_dataframe(df_filtered)
            
            QtWidgets.QMessageBox.information(
                None,
                "Başarılı",
                f"Excel'den {len(df_filtered)} satır başarıyla içe aktarıldı."
            )
            
            logger.info(f"Excel dosyasından {len(df_filtered)} satır içe aktarıldı: {file_path}")
            return True
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                None,
                "Hata",
                f"Excel dosyası okunurken hata oluştu:\n{str(e)}"
            )
            logger.error(f"Excel import hatası: {e}", exc_info=True)
            return False


class MainWindow(QtWidgets.QWidget):
    """Uygulamanın ana penceresi"""
    
    def __init__(self):
        super().__init__()
        self._init_ui()
        self._connect_signals()
        self.load_settings_from_registry()

    def _init_ui(self):
        """UI bileşenlerini oluştur"""
        self.setWindowTitle("Worklogger")
        self.resize(800, 700)
        self.setWindowIcon(QtGui.QIcon(resource_path("jira.ico")))

        # Aktivasyon grup
        self._setup_activation_group()

        # Authentication grup (JSESSIONID veya username/password)
        self._setup_authentication_group()

        # Jira config bölümü
        self._setup_jira_config()

        self._setup_table_group()

        # İnfo label
        self.infoLabel = QtWidgets.QLabel("Kontrol et ile issue/worklog özeti alabilir veya başlat ile işlem yapabilirsiniz.")
        self.infoLabel.setStyleSheet("color:#555; font-size: 12px;")
        self.infoLabel.setMaximumHeight(20)

        # Kontrol butonları
        self._setup_buttons()

        # Progress ve log
        self.progress = QtWidgets.QProgressBar()
        self.progress.setValue(0)

        self.log = QtWidgets.QTextEdit()
        self.log.setMinimumWidth(200)
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("İşlem günlükleri burada görünecek...")

        # Sol taraf: Form ve tablo (dikey layout)
        left_layout = QtWidgets.QVBoxLayout()
        left_layout.setSpacing(12)
        left_layout.addWidget(self.activation_group, stretch=2)
        left_layout.addWidget(self.auth_group, stretch=2)
        
        # Ensure labels/fields initial visibility matches checkbox
        self._on_auth_mode_changed()
        
        left_layout.addWidget(self.jira_group, stretch=2)
        left_layout.addWidget(self.table_group, stretch=5)

        left_layout.addWidget(self.infoLabel, stretch=0, alignment=QtCore.Qt.AlignBottom)

        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addWidget(self.checkBtn)
        btn_layout.addWidget(self.startBtn)
        btn_layout.addWidget(self.cancelBtn)
        left_layout.addLayout(btn_layout)

        left_layout.addWidget(self.progress)

        # Sol taraf container (widget'e sarı sol tarafı holder'a koy)
        left_widget = QtWidgets.QWidget()
        left_widget.setLayout(left_layout)

        # Splitter ile ana layout: Yatay (sol taraf + sağ taraf log)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.addWidget(left_widget)
        splitter.addWidget(self.log)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)

        # Ana layout
        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.addWidget(splitter)

        # State
        self.worker: Optional[WorklogWorker] = None
        self.check_worker: Optional[AssigneeIssueCheckWorker] = None
        # Cache to preserve full table data when switching modes
        self._saved_table_data: Optional[pd.DataFrame] = None

    def _setup_activation_group(self):
        """Aktivasyon grubu oluştur"""
        self.activation_group = QtWidgets.QGroupBox("Aktivasyon")
        self.activation_group.setMaximumHeight(80)
        layout = QtWidgets.QGridLayout(self.activation_group)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(8)

        self.activation_label = QtWidgets.QLabel("")
        self.activation_edit = QtWidgets.QLineEdit()
        self.activation_btn = QtWidgets.QPushButton("Uygula")

        self.activation_edit.setPlaceholderText("Kodu buraya giriniz")
        self.activation_btn.setEnabled(False)

        layout.addWidget(self.activation_edit, 0, 0)
        layout.addWidget(self.activation_label, 0, 1)
        layout.addWidget(self.activation_btn, 0, 2)

    def _setup_authentication_group(self):
        # Authentication group (JSESSIONID or username/password) - stacked vertically
        self.auth_group = QtWidgets.QGroupBox("Authentication")
        self.auth_group.setMaximumHeight(120)

        auth_group_layout = QtWidgets.QVBoxLayout(self.auth_group)
        auth_group_layout.setSpacing(10)
        auth_group_layout.setContentsMargins(10, 10, 10, 10)

        # Authentication seçeneği
        self.use_jsession_checkbox = QtWidgets.QCheckBox("JSESSIONID ile Giriş")
        self.use_jsession_checkbox.setChecked(True)
        self.use_jsession_checkbox.stateChanged.connect(self._on_auth_mode_changed)

        # JSESSIONID alanları
        self.sessionId = QtWidgets.QLineEdit()
        self.sessionId.setPlaceholderText("JSESSIONID değeri")
        self.sessionId.setEchoMode(QtWidgets.QLineEdit.Password)

        self.session_label = QtWidgets.QLabel("Session:")
        self.session_label.setMinimumWidth(42)

        # Kullanıcı adı/şifre alanları
        self.username_label = QtWidgets.QLabel("Kullanıcı:")
        self.username_label.setMinimumWidth(40)
        self.username = QtWidgets.QLineEdit()
        self.username.setPlaceholderText("Kullanıcı adı")
        self.username.setVisible(False)

        self.password_label = QtWidgets.QLabel("Şifre:")
        self.password_label.setMinimumWidth(26)
        self.password = QtWidgets.QLineEdit()
        self.password.setPlaceholderText("Şifre")
        self.password.setEchoMode(QtWidgets.QLineEdit.Password)
        self.password.setVisible(False)
        
        # Session row (label + field) under checkbox
        session_row = QtWidgets.QHBoxLayout()
        session_row.setSpacing(8)
        session_row.addWidget(self.session_label, 0)
        session_row.addWidget(self.sessionId, 1)

        # Username ve Password yan yana
        username_password_row = QtWidgets.QHBoxLayout()
        username_password_row.setSpacing(8)
        username_password_row.addWidget(self.username_label, 0)
        username_password_row.addWidget(self.username, 1)
        username_password_row.addSpacing(30)  # Alanlar arasına boşluk ekle
        username_password_row.addWidget(self.password_label, 0)
        username_password_row.addWidget(self.password, 1)

        auth_group_layout.addWidget(self.use_jsession_checkbox)
        auth_group_layout.addLayout(session_row)
        auth_group_layout.addLayout(username_password_row)

    def _setup_jira_config(self):
        """Jira konfigürasyonu oluştur"""
        # JIRA settings group (URL, mode, dates)
        self.jira_group = QtWidgets.QGroupBox("JIRA Ayarları")
        self.jira_group.setMaximumHeight(150)

        jira_group_layout = QtWidgets.QVBoxLayout(self.jira_group)
        jira_group_layout.setSpacing(8)
        jira_group_layout.setContentsMargins(10, 10, 10, 10)

        top_layout = QtWidgets.QHBoxLayout()
        self.jira_label = QtWidgets.QLabel("JIRA:")
        self.jira_server = QtWidgets.QLineEdit()
        self.jira_server.setPlaceholderText("https://jira.example.com")

        date_layout = QtWidgets.QHBoxLayout()
        self.mode_label = QtWidgets.QLabel("Mod:")
        
        self.mode_options = QtWidgets.QComboBox()
        self.mode_options.addItem("Worklog Yükle", WorklogMode.CREATE.value)
        self.mode_options.addItem("Worklog Sil", WorklogMode.DELETE.value)

        self.start_label = QtWidgets.QLabel("Başlangıç:")
        self.startDate = QtWidgets.QLineEdit()
        self.startDate.setPlaceholderText("Başlangıç tarihi")
        self.startDate.setText(datetime.today().strftime("%d.%m.%Y"))

        self.end_label = QtWidgets.QLabel("Bitiş:")
        self.endDate = QtWidgets.QLineEdit()
        self.endDate.setPlaceholderText("Bitiş tarihi")
        self.endDate.setText(datetime.today().strftime("%d.%m.%Y"))

        self.include_weekends_checkbox = QtWidgets.QCheckBox("Hafta sonlarını dahil et")
        self.include_weekends_checkbox.setChecked(False)
        
        top_layout.addWidget(self.jira_label, 0)
        top_layout.addWidget(self.jira_server, 1)
        date_layout.addWidget(self.mode_label, 0)
        date_layout.addWidget(self.mode_options, 1)
        date_layout.addWidget(self.start_label, 0)
        date_layout.addWidget(self.startDate, 1)
        date_layout.addWidget(self.end_label, 0)
        date_layout.addWidget(self.endDate, 1)
        
        jira_group_layout.addLayout(top_layout)
        jira_group_layout.addLayout(date_layout)
        jira_group_layout.addWidget(self.include_weekends_checkbox)

    def _setup_table_group(self):
        # Excel-style tablo
        self.dataTable = ExcelStyleTable()
        # Tablo başlığı ve kontrolleri
        self.table_group = QtWidgets.QGroupBox("Worklog Verisi")
        table_group_layout = QtWidgets.QVBoxLayout(self.table_group)
        table_group_layout.setSpacing(0)
        table_group_layout.setContentsMargins(10, 0, 10, 10)

        # Tablo butonları (yatay layout)
        table_header_layout = QtWidgets.QHBoxLayout()
        table_header_layout.setContentsMargins(8, 8, 8, 8)
        table_header_layout.setSpacing(10)
        
        import_btn = QtWidgets.QPushButton("📥 İçeri Aktar")
        import_btn.setMaximumWidth(100)
        import_btn.clicked.connect(self.dataTable.import_from_excel)
        table_header_layout.addWidget(import_btn)
        
        add_row_btn = QtWidgets.QPushButton("➕ Satır Ekle")
        add_row_btn.setMaximumWidth(100)
        add_row_btn.clicked.connect(self.dataTable.add_empty_row)
        table_header_layout.addWidget(add_row_btn)
        
        remove_row_btn = QtWidgets.QPushButton("❌ Satır Sil")
        remove_row_btn.setMaximumWidth(100)
        remove_row_btn.clicked.connect(self.dataTable.remove_selected_row)
        table_header_layout.addWidget(remove_row_btn)
        
        table_header_layout.addStretch()

        clear_btn = QtWidgets.QPushButton("🗑 Temizle")
        clear_btn.setMaximumWidth(100)
        clear_btn.clicked.connect(self.dataTable.clear_data)
        table_header_layout.addWidget(clear_btn)

        # Group'a butonları ve tabloyu ekle
        table_group_layout.addLayout(table_header_layout, stretch=0)
        table_group_layout.addWidget(self.dataTable, stretch=1)
        table_group_layout.addStretch()  # Boşluğu aşağıya iter

    def _on_auth_mode_changed(self):
        """Authentication modu değiştiğinde"""
        use_jsession = self.use_jsession_checkbox.isChecked()
        
        # JSESSIONID alanları göster/gizle
        self.sessionId.setVisible(use_jsession)
        self.session_label.setVisible(use_jsession)
        
        # Kullanıcı adı/şifre alanları göster/gizle
        self.username.setVisible(not use_jsession)
        self.username_label.setVisible(not use_jsession)
        self.password.setVisible(not use_jsession)
        self.password_label.setVisible(not use_jsession)

    def _setup_buttons(self):
        """Butonları oluştur"""
        self.checkBtn = QtWidgets.QPushButton("🔎 Kontrol Et")
        self.checkBtn.setEnabled(True)
        self.checkBtn.setCursor(QtCore.Qt.PointingHandCursor)
        self.checkBtn.setStyleSheet("""
            QPushButton {
                background-color: #19A0FF;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #168CDE;
            }
            QPushButton:pressed {
                background-color: #1272B5;
            }
        """)

        self.startBtn = QtWidgets.QPushButton("▶️ Başlat")
        self.startBtn.setEnabled(True)
        self.startBtn.setCursor(QtCore.Qt.PointingHandCursor)
        self.startBtn.setStyleSheet("""
            QPushButton {
                background-color: #107C10;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0d6609;
            }
            QPushButton:pressed {
                background-color: #0a4d07;
            }
        """)

        self.cancelBtn = QtWidgets.QPushButton("⛔ İptal")
        self.cancelBtn.setEnabled(False)
        self.cancelBtn.setCursor(QtCore.Qt.PointingHandCursor)
        self.cancelBtn.setStyleSheet("""
            QPushButton {
                background-color: #E74C3C;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
            QPushButton:pressed {
                background-color: #a93226;
            }
            QPushButton:disabled {
                background-color: #C78D8E;
            }
        """)

    def _connect_signals(self):
        """Sinyal bağlantılarını kur"""
        self.checkBtn.clicked.connect(self.check_assignee_issues)
        self.startBtn.clicked.connect(self.start_processing)
        self.cancelBtn.clicked.connect(self.cancel_processing)
        self.activation_edit.textChanged.connect(self.on_activation_change)
        self.activation_btn.clicked.connect(self._check_activation)
        self.mode_options.currentIndexChanged.connect(self.on_mode_changed)
        self.use_jsession_checkbox.stateChanged.connect(self._on_auth_mode_changed)

    # ----- Aktivasyon Events -----

    def _check_activation(self, inform_on_success: bool = True) -> bool:
        """Aktivasyon kodunu uygula"""
        activation_result = check_activation(self.activation_edit.text())
        
        if activation_result["status"] == "valid":
            remaining_days = activation_result["value"]
            if inform_on_success:
                QtWidgets.QMessageBox.information(
                    self,
                    "Başarılı",
                    f"Aktivasyon başarılı.\n{remaining_days} gün kullanım hakkınız kaldı."
            )
            self.activation_label.setText(f"✓ {remaining_days} gün")
            self.activation_label.setStyleSheet("color: green; font-weight: bold;")
            logger.info(f"Aktivasyon başarılı: {remaining_days} gün kaldı")
            return True
        
        if activation_result["status"] == "invalid":
            QtWidgets.QMessageBox.critical(
                self,
                "Hata",
                "Geçersiz aktivasyon kodu."
            )
            logger.warning("Geçersiz aktivasyon kodu girildi")

        if activation_result["status"] == "expired":
            QtWidgets.QMessageBox.critical(
                self,
                "Hata",
                "Bu aktivasyon kodunun süresi dolmuş."
            )
            logger.warning("Süresi dolmuş aktivasyon kodu girildi")
        
        return False


    def on_activation_change(self):
        """Aktivasyon kodu değiştiğinde"""
        self.activation_btn.setEnabled(bool(self.activation_edit.text().strip()))

    # ----- Mode Events -----

    def on_mode_changed(self, index: int):
        """Mod değiştiğinde"""
        mode = self.mode_options.currentData()
        
        # Mevcut tablo verisini al
        current_data = self.dataTable.get_data_as_dataframe()
        
        # Eğer DELETE moduna geçiliyorsa, tam tabloyu iç cache'e kaydet
        if mode == WorklogMode.DELETE.value:
            if not current_data.empty:
                self._saved_table_data = current_data.copy()

        # Tabloyu moda göre ayarla
        self.dataTable.set_mode(mode)
        
        # Eğer CREATE moduna dönülüyorsa, cache'deki tam tabloyu geri yükle
        if mode == WorklogMode.CREATE.value:
            if self._saved_table_data is not None and not self._saved_table_data.empty:
                self.dataTable.load_from_dataframe(self._saved_table_data)
                # Cache'i temizleme isteğe bağlı; saklamaya devam edebiliriz
                # self._saved_table_data = None

        mode_name = self.mode_options.currentText()
        self.infoLabel.setText(f"Mod: {mode_name}")
        logger.info(f"İşlem modu değiştirildi: {mode_name}")


    def _validate_inputs(self) -> bool:
        """İnput doğrulaması"""
        errors = []

        jira_server = self.jira_server.text().strip()
        if not jira_server:
            errors.append("JIRA sunucusu boş.")
        elif not is_valid_server_url(jira_server):
            errors.append("JIRA URL geçersiz. Örnek: https://jira.example.com")

        # Authentication doğrulaması
        if self.use_jsession_checkbox.isChecked():
            if not self.sessionId.text().strip():
                errors.append("JSESSIONID boş.")
        else:
            if not self.username.text().strip():
                errors.append("Kullanıcı adı boş.")
            if not self.password.text().strip():
                errors.append("Şifre boş.")

      
        if errors:
            for error in errors:
                self.append_log(f"❌ {error}")
            return False

        return True

    def _validate_datatable(self) -> bool:
        """DataTable doğrulaması"""
        df = self.dataTable.get_data_as_dataframe()
        if df.empty:
            self.append_log("❌ Tablo boş. Lütfen veri girin.")
            return False
        return True

    def check_assignee_issues(self):
        """Assignee olduğum issue'ları kontrol et ve worklog özetini yaz."""
        if not self._check_activation(inform_on_success=False):
            return
        
        if not self._validate_inputs():
            return
        
        self.log.clear()
        self.progress.setValue(0)
        self._set_running_state(True)

        jsession_id = self.sessionId.text() if self.use_jsession_checkbox.isChecked() else ""
        username = "" if jsession_id else self.username.text()
        password = "" if jsession_id else self.password.text()
        self.check_worker = AssigneeIssueCheckWorker(
            jira_server=self.jira_server.text().strip(),
            jsession_id=jsession_id,
            username=username,
            password=password,
            start_date=self.startDate.text().strip(),
            end_date=self.endDate.text().strip(),
        )
        self.check_worker.statusSignal.connect(self.append_log)
        self.check_worker.errorSignal.connect(self.on_check_worker_error)
        self.check_worker.finishedSignal.connect(self.on_check_worker_finished)
        self.check_worker.finished.connect(self.on_check_worker_thread_finished)
        self.check_worker.start()

    def _suggest_issue_key(self, issue_keys: list) -> None:
        self.append_log(f"Eşleşen issue sayısı: {len(issue_keys)}")
        for issue_key in issue_keys:
            self.append_log(f"✓ {issue_key}")

    def _append_worklog_daily_summary(self, daily_totals: Dict[str, float]):
        """Issue workloglarını gün bazında log'a yaz."""
        if not daily_totals:
            self.append_log("ℹ Kriterlere uygun kendi worklog kaydı bulunamadı.")
            self.append_log("ℹ Kriterler:\n - assignee = currentUser()\n - issuetype = Sub-task\n - status = In Progress\n - duedate > startOfDay()")
            return
        for day_key, hour_total in daily_totals.items():
            status_icon = "🔴" if hour_total <= 0 else "🟡" if hour_total < 8 else "🟢" if hour_total == 8 else "🔵"
            self.append_log(f"{status_icon} {day_key}: {hour_total:.2f} saat")

    def _populate_table_if_empty(self, issue_keys: list):
        """Tablo boşsa issue key listesini tabloya doldur."""
        if not issue_keys:
            return
        if not self.dataTable.get_data_as_dataframe().empty:
            return
        issue_df = pd.DataFrame({"issueKey": issue_keys})
        self.dataTable.load_from_dataframe(issue_df)
        self.append_log("✓ Tablo boş olduğu için issue key'ler tabloya eklendi.")

    def on_check_worker_error(self, err: str):
        """Kontrol worker hata verdiğinde."""
        self.append_log(f"❌ {err}")

    def on_check_worker_finished(self, result: Dict[str, Any]):
        """Kontrol worker tamamlandığında sonuçları logla."""
        issue_keys = result.get("issue_keys", [])
        daily_totals = result.get("daily_totals", {})
        for warning_msg in result.get("warnings", []):
            self.append_log(warning_msg)
        self._suggest_issue_key(issue_keys)
        self._append_worklog_daily_summary(daily_totals)
        self._populate_table_if_empty(issue_keys)
        self.progress.setValue(100)

    def on_check_worker_thread_finished(self):
        """Kontrol worker thread'i bittiğinde UI durumunu sıfırla."""
        self._set_running_state(False)
        self.check_worker = None

    def start_processing(self):
        """İşlemi başlat"""
        if not self._check_activation(inform_on_success=False):
            return
        
        if not self._validate_inputs():
            return
        
        if not self._validate_datatable():
            return

        self.progress.setValue(0)
        self.log.clear()
        self.append_log("🔄 İş parçacığı başlatılıyor...")
        self._set_running_state(True)

        # Tablodan DataFrame oluştur
        df = self.dataTable.get_data_as_dataframe()

        # Authentication parametreleri
        jsession_id = ""
        username = ""
        password = ""
        
        if self.use_jsession_checkbox.isChecked():
            jsession_id = self.sessionId.text()
        else:
            username = self.username.text()
            password = self.password.text()

        self.worker = WorklogWorker(
            jira_server=self.jira_server.text(),
            table_data=df,
            jsession_id=jsession_id,
            username=username,
            password=password,
            start_date=self.startDate.text(),
            end_date=self.endDate.text(),
            worklog_mode=self.mode_options.currentData(),
            include_weekends=self.include_weekends_checkbox.isChecked(),
        )

        self.worker.startedSignal.connect(self.on_worker_started)
        self.worker.statusSignal.connect(self.append_log)
        self.worker.progressSignal.connect(self.progress.setValue)
        self.worker.errorSignal.connect(self.on_worker_error)
        self.worker.finishedSignal.connect(self.on_worker_finished)
        self.worker.start()

        self.save_settings_to_registry()
        logger.info("İşlem başlatıldı")

    def cancel_processing(self):
        """İşlemi iptal et"""
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.append_log("⏹ İptal isteği gönderildi...")
            logger.info("İşlem iptal edildi")

    # ----- Worker Handlers -----

    def on_worker_started(self, msg: str):
        """Worker başladığında"""
        self.infoLabel.setText(msg)
        self.append_log(msg)

    def on_worker_error(self, err: str):
        """Worker hata verdiğinde"""
        self.append_log(f"❌ HATA: {err}")
        self._set_running_state(False)
        logger.error(f"Worker hatası: {err}")

    def on_worker_finished(self, ok: int, fail: int):
        """Worker bittiğinde"""
        total = ok + fail
        self.append_log(f"\n{'='*10}")
        self.append_log(f"✓ Başarılı: {ok}/{total}")
        self.append_log(f"✗ Başarısız: {fail}/{total}")
        self.append_log(f"{'='*10}\n")
        self.infoLabel.setText(f"✓ Tamamlandı: {ok} başarılı, {fail} başarısız")
        self._set_running_state(False)
        logger.info(f"İşlem tamamlandı: {ok} başarılı, {fail} başarısız")

    # ----- Helpers -----

    def _set_running_state(self, running: bool):
        """Çalışma durumunu ayarla"""
        self.checkBtn.setEnabled(not running)
        self.startBtn.setEnabled(not running)
        self.cancelBtn.setEnabled(running)
        self.dataTable.setEnabled(not running)

    def append_log(self, text: str):
        """Log'a metin ekle"""
        self.log.append(text)
        self.log.ensureCursorVisible()

    # ----- Registry Management -----

    def save_settings_to_registry(self):
        """Ayarları Windows Registry'ye kaydet"""
        if winreg is None:
            logger.warning("winreg modülü mevcut değil, ayarlar kaydedilemedi")
            return

        try:
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_PATH)
            winreg.SetValueEx(key, "ActivationKey", 0, winreg.REG_SZ, self.activation_edit.text())
            winreg.SetValueEx(key, "JiraUrl", 0, winreg.REG_SZ, self.jira_server.text())
            winreg.SetValueEx(key, "UseJsession", 0, winreg.REG_SZ, str(self.use_jsession_checkbox.isChecked()))
            winreg.SetValueEx(
                key,
                "IncludeWeekends",
                0,
                winreg.REG_SZ,
                str(self.include_weekends_checkbox.isChecked()),
            )
            if self.use_jsession_checkbox.isChecked():
                winreg.SetValueEx(key, "SessionId", 0, winreg.REG_SZ, self.sessionId.text())
            else:
                winreg.SetValueEx(key, "Username", 0, winreg.REG_SZ, self.username.text())
            
            # Tablo verisini JSON formatında kaydet
            # Eğer cache varsa, cache'i tercih et (DELETE moduna geçerken orijinal tablo korunmuş olur)
            table_data = self._saved_table_data if self._saved_table_data is not None else self.dataTable.get_data_as_dataframe()
            table_json = table_data.to_json(orient='records', force_ascii=False)
            winreg.SetValueEx(key, "TableData", 0, winreg.REG_SZ, table_json)
            
            winreg.CloseKey(key)
            logger.info("Ayarlar ve tablo verisi kaydedildi")
        except Exception as e:
            logger.error(f"Ayarları kaydetme hatası: {e}")

    def load_settings_from_registry(self):
        """Ayarları Windows Registry'den yükle"""
        if winreg is None:
            logger.warning("winreg modülü mevcut değil, ayarlar yüklenemedi")
            return

        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH)
        except FileNotFoundError:
            logger.info("Registry ayarları bulunamadı, varsayılan değerler kullanılıyor")
            return

        # Aktivasyon kodu
        try:
            activation_key, _ = winreg.QueryValueEx(key, "ActivationKey")
            self.activation_edit.setText(activation_key)
            activation_result = check_activation(activation_key)
            if activation_result["status"] == "valid":
                remaining = activation_result["value"]
                self.activation_label.setText(f"✓ {remaining} gün")
                self.activation_label.setStyleSheet("color: green; font-weight: bold;")
        except FileNotFoundError:
            pass

        # JIRA URL
        try:
            url, _ = winreg.QueryValueEx(key, "JiraUrl")
            self.jira_server.setText(url)
        except FileNotFoundError:
            pass

        # Authentication mode
        try:
            use_jsession_str, _ = winreg.QueryValueEx(key, "UseJsession")
            use_jsession = use_jsession_str.lower() == "true"
            self.use_jsession_checkbox.setChecked(use_jsession)
        except FileNotFoundError:
            pass

        try:
            include_weekends_str, _ = winreg.QueryValueEx(key, "IncludeWeekends")
            self.include_weekends_checkbox.setChecked(include_weekends_str.lower() == "true")
        except FileNotFoundError:
            pass

        # JSESSIONID
        try:
            session_id, _ = winreg.QueryValueEx(key, "SessionId")
            self.sessionId.setText(session_id)
        except FileNotFoundError:
            pass

        # Username
        try:
            username, _ = winreg.QueryValueEx(key, "Username")
            self.username.setText(username)
        except FileNotFoundError:
            pass

        # Tablo verisi (JSON formatında)
        try:
            table_json, _ = winreg.QueryValueEx(key, "TableData")
            if table_json:
                table_data = json.loads(table_json)
                # JSON'u DataFrame'e çevir
                if isinstance(table_data, list) and len(table_data) > 0:
                    df = pd.DataFrame(table_data)
                    # DataFrame'i tabloya yükle
                    self.dataTable.load_from_dataframe(df)
                    logger.info(f"Tablo verisi yüklendi ({len(table_data)} satır)")
        except (FileNotFoundError, json.JSONDecodeError, Exception) as e:
            logger.warning(f"Tablo verisi yüklenemedi: {e}")
            pass

        winreg.CloseKey(key)
        logger.info("Ayarlar yüklendi")


def main():
    """Uygulamayı başlat"""
    logger.info("Worklogger uygulaması başlatılıyor...")
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
