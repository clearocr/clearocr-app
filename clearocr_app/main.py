# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QDesktopServices, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QProgressBar,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .engine import OCRSettings, list_supported_files, process_file
from .logo_asset import clearocr_logo_pixmap
from .ui_theme import APP_STYLESHEET, set_language, status_background, status_color, status_label
from .widgets import DropZone, SettingsDialog, StatCard
from .i18n import I18N


APP_DIR = Path.home() / ".clearocr_client_app_qt"
SETTINGS_FILE = APP_DIR / "settings.json"
SUPPORTED_FILTER = "Documents (*.pdf *.png *.jpg *.jpeg)"


@dataclass(slots=True)
class OCRJob:
    job_id: str
    source_path: Path
    output_path: Path | None = None
    status: str = "queued"
    error_message: str = ""
    result_text: str = ""
    attempts: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @property
    def source_name(self) -> str:
        return self.source_path.name

    @property
    def source_dir(self) -> str:
        return str(self.source_path.parent)


class OCRWorker(QThread):
    log_signal = Signal(str)
    job_update_signal = Signal(str, str, str, str, int)
    result_signal = Signal(str, str, str)
    progress_signal = Signal(int, int)
    finished_summary_signal = Signal(str)

    def __init__(
        self,
        jobs: list[OCRJob],
        settings: OCRSettings,
        output_root: Path | None,
        max_retries: int = 2,
        retry_delays: tuple[int, ...] = (2, 5),
        language: str | None = None,
    ):
        super().__init__()
        self.jobs = jobs
        self.settings = settings
        self.output_root = output_root.resolve() if output_root else None
        self.max_retries = max_retries
        self.retry_delays = retry_delays
        self.cancel_requested = False
        self.common_source_root = self._compute_common_source_root()
        self.i18n = I18N(language)

    def _compute_common_source_root(self) -> Path | None:
        if len(self.jobs) <= 1:
            return None
        try:
            common = os.path.commonpath([str(job.source_path.parent) for job in self.jobs])
            return Path(common)
        except Exception:
            return None

    def _t(self, key: str, **kwargs) -> str:
        return self.i18n.t(key, **kwargs)

    def request_cancel(self):
        self.cancel_requested = True

    def _logger(self, message: str):
        self.log_signal.emit(message)

    def _is_retryable(self, exc: Exception) -> bool:
        message = str(exc)
        non_retry_markers = [
            "HTTP 400",
            "HTTP 401",
            "HTTP 403",
            "HTTP 404",
            "Unauthorized",
            "Unsupported extension",
            self._t("api_missing"),
            "Empty OCR result",
            "Empty OCR result for PDF",
        ]
        return not any(marker in message for marker in non_retry_markers)

    def _output_dir_for(self, source_path: Path) -> Path | None:
        if self.output_root is None:
            return None
        if self.common_source_root is None:
            return self.output_root
        try:
            relative_parent = source_path.parent.relative_to(self.common_source_root)
            return self.output_root / relative_parent
        except Exception:
            return self.output_root

    def run(self):
        total = len(self.jobs)
        finished = 0
        ok_count = 0
        err_count = 0
        cancelled_count = 0
        self.progress_signal.emit(0, total)

        for job in self.jobs:
            if self.cancel_requested:
                self.job_update_signal.emit(job.job_id, "cancelled", "", "", job.attempts)
                finished += 1
                cancelled_count += 1
                self.progress_signal.emit(finished, total)
                continue

            self.job_update_signal.emit(job.job_id, "running", "", "", job.attempts)
            self.log_signal.emit(self._t("worker_start_ocr", path=job.source_path))

            last_error = ""
            attempts_total = self.max_retries + 1
            success = False

            for attempt_number in range(1, attempts_total + 1):
                if self.cancel_requested:
                    last_error = self._t("cancel")
                    break

                try:
                    output_dir = self._output_dir_for(job.source_path)
                    out_path = process_file(
                        job.source_path,
                        self.settings,
                        output_dir=output_dir,
                        logger=self._logger,
                    )
                    text = out_path.read_text(encoding="utf-8", errors="replace")
                    self.job_update_signal.emit(job.job_id, "done", str(out_path), "", attempt_number)
                    self.result_signal.emit(job.job_id, str(out_path), text)
                    ok_count += 1
                    success = True
                    break
                except Exception as exc:
                    last_error = str(exc)
                    retryable = self._is_retryable(exc)
                    self.job_update_signal.emit(job.job_id, "running", "", last_error, attempt_number)
                    if attempt_number < attempts_total and retryable and not self.cancel_requested:
                        delay = self.retry_delays[min(attempt_number - 1, len(self.retry_delays) - 1)]
                        self.log_signal.emit(self._t("worker_retry_error", job_name=job.source_name, last_error=last_error, delay=delay, attempt_number=attempt_number, attempts_total=attempts_total))
                        time.sleep(delay)
                        continue
                    break

            if not success:
                if self.cancel_requested and last_error == self._t("cancel"):
                    self.job_update_signal.emit(job.job_id, "cancelled", "", "", attempt_number)
                    cancelled_count += 1
                else:
                    self.job_update_signal.emit(job.job_id, "error", "", last_error, attempt_number)
                    err_count += 1

            finished += 1
            self.progress_signal.emit(finished, total)

        self.finished_summary_signal.emit(self._t("queue_finished_summary", ok_count=ok_count, err_count=err_count, cancelled_count=cancelled_count, total=total))


class MainWindow(QMainWindow):
    COL_NAME = 0
    COL_STATUS = 1
    COL_SOURCE = 2
    COL_OUTPUT = 3
    COL_ERROR = 4

    def __init__(self):
        super().__init__()
        APP_DIR.mkdir(parents=True, exist_ok=True)
        self.settings_data = self.load_settings()
        self.i18n = I18N(self.settings_data.get("language"))
        self.t = self.i18n.t
        set_language(self.i18n.lang)
        self.jobs_by_id: dict[str, OCRJob] = {}
        self.path_to_job_id: dict[str, str] = {}
        self.worker: OCRWorker | None = None

        self.setWindowTitle(self.t("app_title"))
        self.setWindowIcon(QIcon(clearocr_logo_pixmap(64)))
        self.resize(1540, 940)
        self.setStyleSheet(APP_STYLESHEET)

        self._build_ui()
        self._build_menu()
        self._build_shortcuts()
        self._restore_window_state()
        self._load_initial_state()
        self.refresh_ui_state()

    @staticmethod
    def load_settings() -> dict:
        if not SETTINGS_FILE.exists():
            return {}
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def save_settings(self):
        APP_DIR.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(
            json.dumps(self.settings_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _build_menu(self):
        menubar = self.menuBar()
        app_menu = menubar.addMenu(self.t("app_menu"))

        add_file_action = QAction(self.t("add_file"), self)
        add_file_action.setShortcut(QKeySequence.Open)
        add_file_action.triggered.connect(self.choose_files)
        app_menu.addAction(add_file_action)

        add_dir_action = QAction(self.t("add_directory"), self)
        add_dir_action.setShortcut(QKeySequence("Ctrl+Shift+O"))
        add_dir_action.triggered.connect(self.choose_directory)
        app_menu.addAction(add_dir_action)

        app_menu.addSeparator()

        settings_action = QAction(self.t("api_settings"), self)
        settings_action.setShortcut(QKeySequence.Preferences)
        settings_action.triggered.connect(self.open_settings_dialog)
        app_menu.addAction(settings_action)

        app_menu.addSeparator()

        exit_action = QAction(self.t("close"), self)
        exit_action.triggered.connect(self.close)
        app_menu.addAction(exit_action)

    def _build_shortcuts(self):
        QShortcut(QKeySequence("Delete"), self, activated=self.remove_selected_jobs)
        QShortcut(QKeySequence("F5"), self, activated=self.retry_selected_jobs)
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self.start_queue)

    def _build_ui(self):
        central = QWidget(self)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(18, 16, 18, 18)
        root.setSpacing(14)

        header = self._build_header()
        root.addWidget(header)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(8)
        root.addWidget(splitter, 1)

        sidebar = self._build_sidebar()
        work_area = self._build_work_area()

        splitter.addWidget(sidebar)
        splitter.addWidget(work_area)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([360, 1180])
        self.main_splitter = splitter

    def _build_header(self) -> QWidget:
        card = QFrame()
        card.setObjectName("headerCard")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(16)

        self.logo_label = QLabel()
        self.logo_label.setPixmap(clearocr_logo_pixmap(168))
        self.logo_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.logo_label.setMinimumWidth(180)

        title_col = QVBoxLayout()
        title_col.setSpacing(4)

        self.page_title_label = QLabel(self.t("app_title"))
        self.page_title_label.setProperty("pageTitle", True)

        self.page_subtitle_label = QLabel(self.t("page_subtitle"))
        self.page_subtitle_label.setProperty("muted", True)

        title_col.addWidget(self.page_title_label)
        title_col.addWidget(self.page_subtitle_label)
        title_col.addStretch(1)

        right_col = QVBoxLayout()
        right_col.setSpacing(8)
        right_col.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        badge_row = QHBoxLayout()
        badge_row.setSpacing(10)
        badge_row.addStretch(1)

        self.connection_badge = QLabel(self.t("api_missing"))
        self.connection_badge.setObjectName("connectionBadge")
        self.connection_badge.setProperty("connected", False)

        self.quick_settings_btn = QPushButton(self.t("api_settings"))
        self.quick_settings_btn.setProperty("role", "primary")
        self.quick_settings_btn.clicked.connect(self.open_settings_dialog)

        badge_row.addWidget(self.connection_badge, 0)
        badge_row.addWidget(self.quick_settings_btn, 0)

        self.api_host_label = QLabel(self.t("api_host_missing"))
        self.api_host_label.setProperty("muted", True)
        self.api_host_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        right_col.addLayout(badge_row)
        right_col.addWidget(self.api_host_label)

        layout.addWidget(self.logo_label, 0)
        layout.addLayout(title_col, 1)
        layout.addLayout(right_col, 1)
        return card

    def _build_sidebar(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("sidebarPanel")
        panel.setFixedWidth(360)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        source_group = QGroupBox(self.t("sources"))
        source_layout = QVBoxLayout(source_group)
        source_layout.setSpacing(10)

        self.drop_zone = DropZone(t=self.t)
        self.drop_zone.files_and_dirs_dropped.connect(self.handle_dropped_items)

        self.add_file_btn = QPushButton(self.t("add_files"))
        self.add_dir_btn = QPushButton(self.t("add_directory"))
        self.add_file_btn.clicked.connect(self.choose_files)
        self.add_dir_btn.clicked.connect(self.choose_directory)

        source_buttons = QHBoxLayout()
        source_buttons.setSpacing(8)
        source_buttons.addWidget(self.add_file_btn)
        source_buttons.addWidget(self.add_dir_btn)

        source_layout.addWidget(self.drop_zone)
        source_layout.addLayout(source_buttons)

        options_group = QGroupBox(self.t("queue_settings"))
        options_layout = QFormLayout(options_group)
        options_layout.setVerticalSpacing(10)

        self.output_dir_edit = QLineEdit(self.settings_data.get("output_dir", ""))
        self.output_dir_edit.setPlaceholderText(self.t("output_placeholder"))

        self.choose_output_btn = QPushButton(self.t("choose"))
        self.choose_output_btn.clicked.connect(self.choose_output_directory)

        output_row = QWidget()
        output_row_layout = QHBoxLayout(output_row)
        output_row_layout.setContentsMargins(0, 0, 0, 0)
        output_row_layout.setSpacing(8)
        output_row_layout.addWidget(self.output_dir_edit, 1)
        output_row_layout.addWidget(self.choose_output_btn)

        self.recursive_checkbox = QCheckBox(self.t("recursive_scan"))
        self.recursive_checkbox.setChecked(bool(self.settings_data.get("recursive", True)))
        self.recursive_checkbox.toggled.connect(self._on_recursive_toggled)

        options_layout.addRow(self.t("output_directory"), output_row)
        options_layout.addRow("", self.recursive_checkbox)

        actions_group = QGroupBox(self.t("queue_actions"))
        actions_layout = QGridLayout(actions_group)
        actions_layout.setHorizontalSpacing(8)
        actions_layout.setVerticalSpacing(8)

        self.start_queue_btn = QPushButton(self.t("start_queue"))
        self.start_queue_btn.setProperty("role", "primary")
        self.start_queue_btn.clicked.connect(self.start_queue)

        self.cancel_btn = QPushButton(self.t("cancel"))
        self.cancel_btn.setProperty("role", "danger")
        self.cancel_btn.clicked.connect(self.cancel_queue)

        self.retry_selected_btn = QPushButton(self.t("retry_selected"))
        self.retry_selected_btn.clicked.connect(self.retry_selected_jobs)

        self.remove_selected_btn = QPushButton(self.t("remove_selected"))
        self.remove_selected_btn.clicked.connect(self.remove_selected_jobs)

        self.clear_finished_btn = QPushButton(self.t("clear_finished"))
        self.clear_finished_btn.clicked.connect(self.clear_finished_jobs)

        actions_layout.addWidget(self.start_queue_btn, 0, 0)
        actions_layout.addWidget(self.cancel_btn, 0, 1)
        actions_layout.addWidget(self.retry_selected_btn, 1, 0)
        actions_layout.addWidget(self.remove_selected_btn, 1, 1)
        actions_layout.addWidget(self.clear_finished_btn, 2, 0, 1, 2)

        layout.addWidget(source_group)
        layout.addWidget(options_group)
        layout.addWidget(actions_group)
        layout.addStretch(1)
        return panel

    def _build_work_area(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("workAreaPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        stats_row = QHBoxLayout()
        stats_row.setSpacing(10)
        self.total_card = StatCard(self.t("all"), "0")
        self.queued_card = StatCard(self.t("queued"), "0")
        self.running_card = StatCard(self.t("running"), "0")
        self.done_card = StatCard(self.t("done"), "0")
        self.error_card = StatCard(self.t("errors"), "0")
        for card in [self.total_card, self.queued_card, self.running_card, self.done_card, self.error_card]:
            stats_row.addWidget(card)

        progress_card = QFrame()
        progress_card.setObjectName("card")
        progress_layout = QVBoxLayout(progress_card)
        progress_layout.setContentsMargins(16, 14, 16, 14)
        progress_layout.setSpacing(10)

        progress_header = QHBoxLayout()
        progress_title = QLabel(self.t("queue_progress"))
        progress_title.setProperty("sectionTitle", True)
        self.progress_summary_label = QLabel("0 / 0")
        self.progress_summary_label.setProperty("muted", True)
        progress_header.addWidget(progress_title)
        progress_header.addStretch(1)
        progress_header.addWidget(self.progress_summary_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")

        progress_layout.addLayout(progress_header)
        progress_layout.addWidget(self.progress_bar)

        queue_group = QGroupBox(self.t("queue"))
        queue_layout = QVBoxLayout(queue_group)
        queue_layout.setSpacing(10)

        queue_toolbar = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(self.t("filter_placeholder"))
        self.search_edit.textChanged.connect(self.apply_filters)

        self.status_filter_combo = QComboBox()
        self.status_filter_combo.addItem(self.t("all_statuses"), "all")
        self.status_filter_combo.addItem(self.t("queued"), "queued")
        self.status_filter_combo.addItem(self.t("running"), "running")
        self.status_filter_combo.addItem(self.t("done"), "done")
        self.status_filter_combo.addItem(self.t("errors"), "error")
        self.status_filter_combo.addItem(self.t("cancelled_plural"), "cancelled")
        self.status_filter_combo.currentIndexChanged.connect(self.apply_filters)

        queue_toolbar.addWidget(self.search_edit, 1)
        queue_toolbar.addWidget(self.status_filter_combo)

        self.jobs_table = QTableWidget(0, 5)
        self.jobs_table.setHorizontalHeaderLabels([self.t("file").rstrip(":"), self.t("status").rstrip(":"), self.t("source_folder"), self.t("output_file").rstrip(":"), self.t("error_title")])
        self.jobs_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.jobs_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.jobs_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.jobs_table.setAlternatingRowColors(True)
        self.jobs_table.setShowGrid(False)
        self.jobs_table.verticalHeader().setVisible(False)
        self.jobs_table.itemSelectionChanged.connect(self.on_job_selection_changed)
        self.jobs_table.cellDoubleClicked.connect(self.on_table_double_clicked)
        self.jobs_table.setSortingEnabled(False)
        header = self.jobs_table.horizontalHeader()
        header.setSectionResizeMode(self.COL_NAME, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.COL_STATUS, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.COL_SOURCE, QHeaderView.Stretch)
        header.setSectionResizeMode(self.COL_OUTPUT, QHeaderView.Stretch)
        header.setSectionResizeMode(self.COL_ERROR, QHeaderView.Stretch)

        queue_layout.addLayout(queue_toolbar)
        queue_layout.addWidget(self.jobs_table, 1)

        tabs = QTabWidget()
        self.preview_tab = self._build_preview_tab()
        self.details_tab = self._build_details_tab()
        self.log_tab = self._build_log_tab()
        tabs.addTab(self.preview_tab, self.t("ocr_result"))
        tabs.addTab(self.details_tab, self.t("details"))
        tabs.addTab(self.log_tab, self.t("log"))
        self.bottom_tabs = tabs

        details_splitter = QSplitter(Qt.Vertical)
        details_splitter.setHandleWidth(8)
        details_splitter.addWidget(queue_group)
        details_splitter.addWidget(tabs)
        details_splitter.setStretchFactor(0, 3)
        details_splitter.setStretchFactor(1, 2)
        details_splitter.setSizes([520, 320])
        self.details_splitter = details_splitter

        layout.addLayout(stats_row)
        layout.addWidget(progress_card)
        layout.addWidget(details_splitter, 1)
        return panel

    def _build_preview_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        button_row = QHBoxLayout()
        self.copy_result_btn = QPushButton(self.t("copy_result"))
        self.open_txt_btn = QPushButton(self.t("open_txt"))
        self.open_folder_btn = QPushButton(self.t("open_folder"))
        self.open_source_btn = QPushButton(self.t("open_source"))

        self.copy_result_btn.clicked.connect(self.copy_result)
        self.open_txt_btn.clicked.connect(self.open_selected_txt)
        self.open_folder_btn.clicked.connect(self.open_selected_folder)
        self.open_source_btn.clicked.connect(self.open_selected_source)

        button_row.addWidget(self.copy_result_btn)
        button_row.addWidget(self.open_txt_btn)
        button_row.addWidget(self.open_folder_btn)
        button_row.addWidget(self.open_source_btn)
        button_row.addStretch(1)

        self.result_box = QPlainTextEdit()
        self.result_box.setReadOnly(True)
        self.result_box.setPlaceholderText(self.t("result_placeholder"))

        layout.addLayout(button_row)
        layout.addWidget(self.result_box, 1)
        return widget

    def _build_details_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        card = QFrame()
        card.setObjectName("card")
        card_layout = QFormLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setVerticalSpacing(12)

        self.selected_name_label = QLabel("-")
        self.selected_name_label.setWordWrap(True)
        self.selected_source_label = QLabel("-")
        self.selected_source_label.setWordWrap(True)
        self.selected_output_label = QLabel("-")
        self.selected_output_label.setWordWrap(True)
        self.selected_status_badge = QLabel("-")
        self.selected_status_badge.setProperty("statusBadge", True)
        self.selected_attempts_label = QLabel("-")
        self.selected_updated_label = QLabel("-")
        self.selected_error_label = QLabel("-")
        self.selected_error_label.setWordWrap(True)

        card_layout.addRow(self.t("file"), self.selected_name_label)
        card_layout.addRow(self.t("full_path"), self.selected_source_label)
        card_layout.addRow(self.t("status"), self.selected_status_badge)
        card_layout.addRow(self.t("output_file"), self.selected_output_label)
        card_layout.addRow(self.t("attempts"), self.selected_attempts_label)
        card_layout.addRow(self.t("last_change"), self.selected_updated_label)
        card_layout.addRow(self.t("error"), self.selected_error_label)

        layout.addWidget(card)
        layout.addStretch(1)
        return widget

    def _build_log_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMaximumBlockCount(5000)
        self.log_box.setPlaceholderText(self.t("technical_log"))
        layout.addWidget(self.log_box)
        return widget

    def _load_initial_state(self):
        self.log(self.t("app_started"))
        self.update_api_summary()
        if self.settings_data.get("api_url"):
            self.log(self.t("api_loaded"))
        else:
            self.log(self.t("api_missing_config"))

    def _restore_window_state(self):
        geometry_hex = self.settings_data.get("window_geometry")
        splitter_hex = self.settings_data.get("main_splitter_state")
        details_hex = self.settings_data.get("details_splitter_state")
        if geometry_hex:
            try:
                self.restoreGeometry(bytes.fromhex(geometry_hex))
            except Exception:
                pass
        if splitter_hex:
            try:
                self.main_splitter.restoreState(bytes.fromhex(splitter_hex))
            except Exception:
                pass
        if details_hex:
            try:
                self.details_splitter.restoreState(bytes.fromhex(details_hex))
            except Exception:
                pass

    def _persist_window_state(self):
        self.settings_data["window_geometry"] = bytes(self.saveGeometry()).hex()
        self.settings_data["main_splitter_state"] = bytes(self.main_splitter.saveState()).hex()
        self.settings_data["details_splitter_state"] = bytes(self.details_splitter.saveState()).hex()

    def _on_recursive_toggled(self, checked: bool):
        self.persist_basic_settings()


    def update_api_summary(self):
        api_url = self.settings_data.get("api_url", "").strip()
        api_version = self.settings_data.get("api_version", "0.1")

        if not api_url:
            self.connection_badge.setText(self.t("api_missing"))
            self.connection_badge.setToolTip(self.t("api_tooltip_missing"))
            self.connection_badge.setProperty("connected", False)
            self.api_host_label.setText(self.t("api_host_missing"))
        else:
            parsed = urlparse(api_url)
            host = parsed.netloc or api_url
            self.connection_badge.setText(self.t("api_configured"))
            self.connection_badge.setToolTip(self.t("api_tooltip", host=host, api_url=api_url, api_version=api_version))
            self.connection_badge.setProperty("connected", True)
            self.api_host_label.setText(self.t("api_header_short", host=host, api_version=api_version))

        self.connection_badge.style().unpolish(self.connection_badge)
        self.connection_badge.style().polish(self.connection_badge)
        self.connection_badge.update()

    def log(self, message: str):
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_box.appendPlainText(f"[{stamp}] {message}")

    def persist_basic_settings(self):
        self.settings_data["output_dir"] = self.output_dir_edit.text().strip()
        self.settings_data["recursive"] = self.recursive_checkbox.isChecked()
        self.settings_data["language"] = self.i18n.lang
        self.save_settings()

    def choose_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, self.t("choose_files_title"), "", SUPPORTED_FILTER)
        if files:
            self.add_many_paths([Path(file_path) for file_path in files])

    def choose_directory(self):
        directory = QFileDialog.getExistingDirectory(self, self.t("choose_dir_title"))
        if directory:
            self.enqueue_directory(Path(directory))

    def choose_output_directory(self):
        directory = QFileDialog.getExistingDirectory(self, self.t("choose_output_title"))
        if not directory:
            return
        self.output_dir_edit.setText(directory)
        self.persist_basic_settings()
        self.log(self.t("selected_output_dir", directory=directory))

    def handle_dropped_items(self, files: list[str], dirs: list[str]):
        if files:
            self.add_many_paths([Path(item) for item in files])
        for directory in dirs:
            self.enqueue_directory(Path(directory))

    def enqueue_directory(self, directory: Path):
        try:
            files = list_supported_files(directory, recursive=self.recursive_checkbox.isChecked())
        except Exception as exc:
            QMessageBox.warning(self, self.t("error_title"), str(exc))
            self.log(f"ERR: {exc}")
            return

        if not files:
            QMessageBox.information(self, self.t("info"), self.t("no_supported_files"))
            return

        added, skipped = self.add_many_paths(files)
        self.log(self.t("added_from_dir", directory=directory, added=added, skipped=skipped))

    def add_many_paths(self, paths: list[Path]) -> tuple[int, int]:
        added = 0
        skipped = 0
        for path in paths:
            if self.add_job(path):
                added += 1
            else:
                skipped += 1
        if added:
            self.apply_filters()
            self.refresh_summary_cards()
            self.refresh_ui_state()
        return added, skipped

    def add_job(self, source_path: Path) -> bool:
        source_path = source_path.resolve()
        path_key = str(source_path)
        if path_key in self.path_to_job_id:
            existing_job_id = self.path_to_job_id[path_key]
            row = self.find_row_by_job_id(existing_job_id)
            if row is not None:
                self.jobs_table.selectRow(row)
            self.log(self.t("duplicate_skipped", source_path=source_path))
            return False

        job = OCRJob(job_id=str(uuid.uuid4()), source_path=source_path)
        self.jobs_by_id[job.job_id] = job
        self.path_to_job_id[path_key] = job.job_id

        row = self.jobs_table.rowCount()
        self.jobs_table.insertRow(row)

        name_item = QTableWidgetItem(job.source_name)
        name_item.setData(Qt.UserRole, job.job_id)
        name_item.setToolTip(str(job.source_path))

        status_item = QTableWidgetItem()
        source_item = QTableWidgetItem(job.source_dir)
        source_item.setToolTip(str(job.source_path.parent))
        output_item = QTableWidgetItem("")
        error_item = QTableWidgetItem("")

        self.jobs_table.setItem(row, self.COL_NAME, name_item)
        self.jobs_table.setItem(row, self.COL_STATUS, status_item)
        self.jobs_table.setItem(row, self.COL_SOURCE, source_item)
        self.jobs_table.setItem(row, self.COL_OUTPUT, output_item)
        self.jobs_table.setItem(row, self.COL_ERROR, error_item)

        self.update_job_row(job.job_id)
        self.log(self.t("added_to_queue", source_path=source_path))
        return True

    def find_row_by_job_id(self, job_id: str) -> int | None:
        for row in range(self.jobs_table.rowCount()):
            item = self.jobs_table.item(row, self.COL_NAME)
            if item and item.data(Qt.UserRole) == job_id:
                return row
        return None

    def selected_job_ids(self) -> list[str]:
        rows = self.jobs_table.selectionModel().selectedRows()
        job_ids: list[str] = []
        for model_index in rows:
            item = self.jobs_table.item(model_index.row(), self.COL_NAME)
            if item:
                job_id = item.data(Qt.UserRole)
                if job_id:
                    job_ids.append(job_id)
        return job_ids

    def selected_jobs(self) -> list[OCRJob]:
        return [self.jobs_by_id[job_id] for job_id in self.selected_job_ids() if job_id in self.jobs_by_id]

    def current_job(self) -> OCRJob | None:
        jobs = self.selected_jobs()
        return jobs[0] if jobs else None

    def update_job_row(self, job_id: str):
        job = self.jobs_by_id.get(job_id)
        row = self.find_row_by_job_id(job_id)
        if not job or row is None:
            return

        status_item = self.jobs_table.item(row, self.COL_STATUS)
        source_item = self.jobs_table.item(row, self.COL_SOURCE)
        output_item = self.jobs_table.item(row, self.COL_OUTPUT)
        error_item = self.jobs_table.item(row, self.COL_ERROR)

        status_item.setText(status_label(job.status))
        status_item.setTextAlignment(Qt.AlignCenter)
        output_item.setText(str(job.output_path) if job.output_path else "")
        output_item.setToolTip(str(job.output_path) if job.output_path else "")
        error_item.setText(job.error_message)
        error_item.setToolTip(job.error_message)
        source_item.setText(job.source_dir)

        bg = QColor(status_background(job.status))
        fg = QColor(status_color(job.status))
        status_item.setBackground(bg)
        status_item.setForeground(fg)

    def build_settings(self) -> OCRSettings:
        api_url = self.settings_data.get("api_url", "").strip()
        api_key = self.settings_data.get("api_key", "")
        api_version = self.settings_data.get("api_version", "0.1").strip() or "0.1"

        if not api_url:
            raise RuntimeError(self.t("missing_api_url"))
        if not api_url.startswith(("http://", "https://")):
            raise RuntimeError(self.t("invalid_api_url"))
        if not api_key:
            raise RuntimeError(self.t("missing_api_key"))

        return OCRSettings(
            api_url=api_url,
            api_key=api_key,
            api_version=api_version,
            search_barcodes=bool(self.settings_data.get("search_barcodes", False)),
            show_pages_separately=bool(self.settings_data.get("show_pages_separately", False)),
            max_pages_per_request=int(self.settings_data.get("max_pages_per_request", 2)),
            http_timeout=int(self.settings_data.get("http_timeout", 300)),
        )

    def current_output_root(self) -> Path | None:
        value = self.output_dir_edit.text().strip()
        return Path(value).resolve() if value else None

    def pending_jobs(self) -> list[OCRJob]:
        return [job for job in self.jobs_by_id.values() if job.status == "queued"]

    def start_queue(self):
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, self.t("info"), self.t("queue_already_running"))
            return

        jobs = self.pending_jobs()
        if not jobs:
            QMessageBox.information(self, self.t("info"), self.t("no_queued_jobs"))
            return

        self.persist_basic_settings()
        try:
            settings = self.build_settings()
        except Exception as exc:
            QMessageBox.warning(self, self.t("settings_error"), str(exc))
            self.log(f"ERR: {exc}")
            return

        if self.worker is not None:
            for signal_name in (
                "log_signal",
                "job_update_signal",
                "result_signal",
                "progress_signal",
                "finished_summary_signal",
            ):
                try:
                    getattr(self.worker, signal_name).disconnect()
                except Exception:
                    pass

        self.worker = OCRWorker(jobs=jobs, settings=settings, output_root=self.current_output_root(), language=self.i18n.lang)
        self.worker.log_signal.connect(self.log)
        self.worker.job_update_signal.connect(self.on_job_update)
        self.worker.result_signal.connect(self.on_job_result)
        self.worker.progress_signal.connect(self.on_progress_update)
        self.worker.finished_summary_signal.connect(self.on_queue_finished)
        self.worker.start()

        self.log(self.t("queue_started", count=len(jobs)))
        self.refresh_ui_state()

    def cancel_queue(self):
        if self.worker and self.worker.isRunning():
            self.worker.request_cancel()
            self.log(self.t("cancel_requested"))
        else:
            self.log(self.t("no_active_queue"))

    def retry_selected_jobs(self):
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, self.t("info"), self.t("cannot_reset_during_run"))
            return

        jobs = self.selected_jobs()
        if not jobs:
            QMessageBox.information(self, self.t("info"), self.t("select_at_least_one"))
            return

        for job in jobs:
            job.status = "queued"
            job.error_message = ""
            job.result_text = ""
            job.output_path = None
            job.updated_at = time.time()
            self.update_job_row(job.job_id)

        self.on_job_selection_changed()
        self.refresh_summary_cards()
        self.refresh_ui_state()
        self.apply_filters()
        self.log(self.t("restored_to_queue", count=len(jobs)))

    def remove_selected_jobs(self):
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, self.t("info"), self.t("cannot_remove_during_run"))
            return

        job_ids = self.selected_job_ids()
        if not job_ids:
            QMessageBox.information(self, self.t("info"), self.t("select_at_least_one"))
            return

        rows = sorted((r for job_id in job_ids if (r := self.find_row_by_job_id(job_id)) is not None), reverse=True)
        for row in rows:
            item = self.jobs_table.item(row, self.COL_NAME)
            if not item:
                continue
            job_id = item.data(Qt.UserRole)
            job = self.jobs_by_id.pop(job_id, None)
            if job:
                self.path_to_job_id.pop(str(job.source_path), None)
            self.jobs_table.removeRow(row)

        self.clear_details()
        self.result_box.clear()
        self.refresh_summary_cards()
        self.refresh_ui_state()
        self.apply_filters()
        self.log(self.t("removed_jobs", count=len(job_ids)))

    def clear_finished_jobs(self):
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, self.t("info"), self.t("cannot_clear_during_run"))
            return

        removable_statuses = {"done", "error", "cancelled"}
        job_ids = [job.job_id for job in self.jobs_by_id.values() if job.status in removable_statuses]
        if not job_ids:
            self.log(self.t("no_finished_to_remove"))
            return

        rows = sorted((r for job_id in job_ids if (r := self.find_row_by_job_id(job_id)) is not None), reverse=True)
        for row in rows:
            item = self.jobs_table.item(row, self.COL_NAME)
            if not item:
                continue
            job_id = item.data(Qt.UserRole)
            job = self.jobs_by_id.pop(job_id, None)
            if job:
                self.path_to_job_id.pop(str(job.source_path), None)
            self.jobs_table.removeRow(row)

        self.clear_details()
        self.result_box.clear()
        self.refresh_summary_cards()
        self.refresh_ui_state()
        self.apply_filters()
        self.log(self.t("cleared_finished", count=len(job_ids)))

    def on_job_update(self, job_id: str, status: str, output_path: str, error_message: str, attempts: int):
        job = self.jobs_by_id.get(job_id)
        if not job:
            return

        job.status = status
        job.error_message = error_message or ""
        job.attempts = max(job.attempts, attempts)
        job.updated_at = time.time()
        if output_path:
            job.output_path = Path(output_path)
        self.update_job_row(job_id)
        self.refresh_summary_cards()
        self.apply_filters()

        current = self.current_job()
        if current and current.job_id == job_id:
            self.update_details_for_job(job)

        self.refresh_ui_state()

    def on_job_result(self, job_id: str, output_path: str, text: str):
        job = self.jobs_by_id.get(job_id)
        if not job:
            return

        job.output_path = Path(output_path) if output_path else None
        job.result_text = text
        job.updated_at = time.time()
        self.update_job_row(job_id)

        current = self.current_job()
        if current is None:
            row = self.find_row_by_job_id(job_id)
            if row is not None:
                self.jobs_table.selectRow(row)
            self.show_result(text)
            self.update_details_for_job(job)
        elif current.job_id == job_id:
            self.show_result(text)
            self.update_details_for_job(job)

        self.log(self.t("ocr_saved", name=job.source_name))
        self.refresh_ui_state()

    def on_progress_update(self, done: int, total: int):
        self.progress_bar.setMaximum(max(total, 1))
        self.progress_bar.setValue(done)
        self.progress_summary_label.setText(f"{done} / {total}")

    def on_queue_finished(self, summary: str):
        self.log(summary)
        self.refresh_summary_cards()
        self.refresh_ui_state()

    def refresh_summary_cards(self):
        jobs = list(self.jobs_by_id.values())
        total = len(jobs)
        queued = sum(job.status == "queued" for job in jobs)
        running = sum(job.status == "running" for job in jobs)
        done = sum(job.status == "done" for job in jobs)
        errors = sum(job.status == "error" for job in jobs)
        completed = sum(job.status in {"done", "error", "cancelled"} for job in jobs)

        self.total_card.set_value(total)
        self.queued_card.set_value(queued)
        self.running_card.set_value(running)
        self.done_card.set_value(done)
        self.error_card.set_value(errors)

        self.progress_bar.setMaximum(max(total, 1))
        self.progress_bar.setValue(completed)
        self.progress_summary_label.setText(f"{completed} / {total}")

    def refresh_ui_state(self):
        has_selection = bool(self.selected_job_ids())
        running = bool(self.worker and self.worker.isRunning())
        has_jobs = bool(self.jobs_by_id)
        has_pending = any(job.status == "queued" for job in self.jobs_by_id.values())
        current = self.current_job()
        has_output = bool(current and current.output_path)
        has_result = bool(current and (current.result_text or (current.output_path and current.output_path.exists())))

        self.start_queue_btn.setEnabled(has_pending and not running)
        self.cancel_btn.setEnabled(running)
        self.retry_selected_btn.setEnabled(has_selection and not running)
        self.remove_selected_btn.setEnabled(has_selection and not running)
        self.clear_finished_btn.setEnabled(has_jobs and not running)
        self.copy_result_btn.setEnabled(has_result)
        self.open_txt_btn.setEnabled(has_output)
        self.open_folder_btn.setEnabled(has_selection)
        self.open_source_btn.setEnabled(has_selection)

    def apply_filters(self):
        search_value = self.search_edit.text().strip().lower()
        selected_status = self.status_filter_combo.currentData()

        for row in range(self.jobs_table.rowCount()):
            item = self.jobs_table.item(row, self.COL_NAME)
            if not item:
                continue
            job_id = item.data(Qt.UserRole)
            job = self.jobs_by_id.get(job_id)
            if not job:
                continue

            matches_status = selected_status in {None, "all"} or job.status == selected_status
            haystack = " ".join(
                [
                    job.source_name,
                    str(job.source_path),
                    str(job.output_path or ""),
                    job.error_message,
                    status_label(job.status),
                ]
            ).lower()
            matches_search = not search_value or search_value in haystack
            self.jobs_table.setRowHidden(row, not (matches_status and matches_search))

    def on_job_selection_changed(self):
        job = self.current_job()
        if job is None:
            self.clear_details()
            self.result_box.clear()
            self.refresh_ui_state()
            return

        self.update_details_for_job(job)
        text = self.ensure_job_text_loaded(job)
        self.show_result(text)
        self.refresh_ui_state()

    def ensure_job_text_loaded(self, job: OCRJob) -> str:
        if job.result_text:
            return job.result_text
        if job.output_path and job.output_path.exists():
            try:
                job.result_text = job.output_path.read_text(encoding="utf-8", errors="replace")
                return job.result_text
            except Exception as exc:
                self.log(self.t("read_output_failed", exc=exc))
        return ""

    def show_result(self, text: str):
        self.result_box.setPlainText(text or "")

    def update_details_for_job(self, job: OCRJob):
        self.selected_name_label.setText(job.source_name)
        self.selected_source_label.setText(str(job.source_path))
        self.selected_output_label.setText(str(job.output_path) if job.output_path else "-")
        self.selected_attempts_label.setText(str(job.attempts or 0))
        self.selected_updated_label.setText(datetime.fromtimestamp(job.updated_at).strftime("%Y-%m-%d %H:%M:%S"))
        self.selected_error_label.setText(job.error_message or "-")
        self._set_status_badge(job.status)

    def _set_status_badge(self, status: str):
        self.selected_status_badge.setText(status_label(status))
        self.selected_status_badge.setStyleSheet(
            f"background: {status_background(status)}; color: {status_color(status)}; padding: 4px 10px; font-weight: 700; border-radius: 8px;"
        )

    def clear_details(self):
        self.selected_name_label.setText("-")
        self.selected_source_label.setText("-")
        self.selected_output_label.setText("-")
        self.selected_attempts_label.setText("-")
        self.selected_updated_label.setText("-")
        self.selected_error_label.setText("-")
        self.selected_status_badge.setText("-")
        self.selected_status_badge.setStyleSheet("padding: 4px 10px;")

    def on_table_double_clicked(self, row: int, column: int):
        job_id = self.jobs_table.item(row, self.COL_NAME).data(Qt.UserRole)
        job = self.jobs_by_id.get(job_id)
        if not job:
            return
        if column == self.COL_OUTPUT and job.output_path:
            self.open_selected_txt()
        elif column == self.COL_SOURCE or column == self.COL_NAME:
            self.open_selected_source()

    def copy_result(self):
        text = self.result_box.toPlainText()
        if not text:
            QMessageBox.information(self, self.t("info"), self.t("no_result_to_copy"))
            return
        QApplication.clipboard().setText(text)
        self.log(self.t("copied_result"))

    def open_selected_txt(self):
        job = self.current_job()
        if not job or not job.output_path:
            QMessageBox.information(self, self.t("info"), self.t("no_output_file"))
            return
        if not job.output_path.exists():
            QMessageBox.warning(self, self.t("error_title"), self.t("file_not_exists", path=job.output_path))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(job.output_path)))
        self.log(self.t("opened_txt", path=job.output_path))

    def open_selected_folder(self):
        job = self.current_job()
        if not job:
            QMessageBox.information(self, self.t("info"), self.t("selected_task"))
            return
        folder = job.output_path.parent if job.output_path and job.output_path.exists() else job.source_path.parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        self.log(self.t("opened_folder", folder=folder))

    def open_selected_source(self):
        job = self.current_job()
        if not job:
            QMessageBox.information(self, self.t("info"), self.t("selected_task"))
            return
        if not job.source_path.exists():
            QMessageBox.warning(self, self.t("error_title"), self.t("source_file_not_exists", path=job.source_path))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(job.source_path)))
        self.log(self.t("opened_source", path=job.source_path))

    def open_settings_dialog(self):
        dialog = SettingsDialog(self, self.settings_data, t=self.t)
        if dialog.exec() != SettingsDialog.Accepted:
            return
        self.settings_data.update(dialog.get_data())
        self.persist_basic_settings()
        self.update_api_summary()
        self.log(self.t("settings_saved", path=SETTINGS_FILE))

    def closeEvent(self, event):
        self.persist_basic_settings()
        self._persist_window_state()
        self.save_settings()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("clearOCR Client")
    app.setOrganizationName("clearOCR")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
