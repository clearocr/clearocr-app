# -*- coding: utf-8 -*-

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

DEFAULT_API_URL = "https://clearocr.teamquest.pl:60213/extract-document-parser"


class DropZone(QFrame):
    files_and_dirs_dropped = Signal(list, list)  # files, dirs

    def __init__(self, parent=None, t=None):
        super().__init__(parent)
        self.t = t or (lambda key, **kwargs: key)
        self.setObjectName('dropZone')
        self.setProperty('dragActive', False)
        self.setAcceptDrops(True)
        self.setMinimumHeight(180)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(10)

        self.title_label = QLabel(self.t('drop_title'))
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setProperty('sectionTitle', True)

        self.subtitle_label = QLabel(self.t('drop_subtitle'))
        self.subtitle_label.setAlignment(Qt.AlignCenter)
        self.subtitle_label.setProperty('muted', True)
        self.subtitle_label.setWordWrap(True)

        root.addStretch(1)
        root.addWidget(self.title_label)
        root.addWidget(self.subtitle_label)
        root.addStretch(1)

        self._refresh_style()

    def _set_drag_active(self, value: bool):
        self.setProperty('dragActive', value)
        self._refresh_style()

    def _refresh_style(self):
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    self._set_drag_active(True)
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dragLeaveEvent(self, event):
        self._set_drag_active(False)
        event.accept()

    def dropEvent(self, event):
        self._set_drag_active(False)
        files: list[str] = []
        dirs: list[str] = []
        for url in event.mimeData().urls():
            if not url.isLocalFile():
                continue
            local_path = url.toLocalFile()
            if not local_path:
                continue
            path = Path(local_path)
            if path.is_file():
                files.append(str(path))
            elif path.is_dir():
                dirs.append(str(path))

        if files or dirs:
            self.files_and_dirs_dropped.emit(files, dirs)
            event.acceptProposedAction()
            return
        event.ignore()


class StatCard(QFrame):
    def __init__(self, title: str, value: str = '0', parent=None):
        super().__init__(parent)
        self.setObjectName('statCard')
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(4)

        self.value_label = QLabel(value)
        self.value_label.setProperty('statValue', True)

        self.title_label = QLabel(title)
        self.title_label.setProperty('muted', True)

        root.addWidget(self.value_label)
        root.addWidget(self.title_label)

    def set_value(self, value: str | int):
        self.value_label.setText(str(value))

    def set_title(self, title: str):
        self.title_label.setText(title)


class SettingsDialog(QDialog):
    def __init__(self, parent=None, initial_data: dict | None = None, t=None):
        super().__init__(parent)
        self.t = t or (lambda key, **kwargs: key)
        self.setWindowTitle(self.t('settings_title'))
        self.resize(760, 400)

        initial_data = initial_data or {}

        self.api_url_edit = QLineEdit(initial_data.get('api_url', DEFAULT_API_URL))
        self.api_url_edit.setPlaceholderText('https://your-server/extract-document-parser')

        self.api_key_edit = QLineEdit(initial_data.get('api_key', ''))
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.api_version_edit = QLineEdit(initial_data.get('api_version', '0.1'))

        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(10, 3600)
        self.timeout_spin.setSuffix(' s')
        self.timeout_spin.setValue(int(initial_data.get('http_timeout', 300)))

        self.max_pages_spin = QSpinBox()
        self.max_pages_spin.setRange(1, 50)
        self.max_pages_spin.setValue(int(initial_data.get('max_pages_per_request', 2)))

        self.search_barcodes_checkbox = QCheckBox(self.t('search_barcodes'))
        self.search_barcodes_checkbox.setChecked(bool(initial_data.get('search_barcodes', False)))

        self.show_pages_checkbox = QCheckBox(self.t('split_pages'))
        self.show_pages_checkbox.setChecked(bool(initial_data.get('show_pages_separately', False)))

        self.show_key_checkbox = QCheckBox(self.t('show_api_key'))
        self.show_key_checkbox.toggled.connect(self._toggle_key_visibility)

        info_box = QFrame()
        info_box.setObjectName('infoCard')
        info_layout = QVBoxLayout(info_box)
        info_layout.setContentsMargins(16, 14, 16, 14)
        info_layout.setSpacing(8)
        info_title = QLabel(self.t('tips'))
        info_title.setProperty('sectionTitle', True)
        info_text = QLabel(self.t('tips_text'))
        info_text.setWordWrap(True)
        info_text.setProperty('muted', True)
        info_layout.addWidget(info_title)
        info_layout.addWidget(info_text)
        info_layout.addStretch(1)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setFormAlignment(Qt.AlignTop)
        form.setVerticalSpacing(12)
        form.addRow(self.t('api_url'), self.api_url_edit)

        key_row = QWidget()
        key_layout = QHBoxLayout(key_row)
        key_layout.setContentsMargins(0, 0, 0, 0)
        key_layout.setSpacing(8)
        key_layout.addWidget(self.api_key_edit, 1)
        key_layout.addWidget(self.show_key_checkbox)
        form.addRow(self.t('api_key'), key_row)

        form.addRow(self.t('api_version'), self.api_version_edit)
        form.addRow(self.t('timeout'), self.timeout_spin)
        form.addRow(self.t('max_pages'), self.max_pages_spin)
        form.addRow('', self.search_barcodes_checkbox)
        form.addRow('', self.show_pages_checkbox)

        self.button_box = QDialogButtonBox()
        self.save_button = self.button_box.addButton(self.t('save'), QDialogButtonBox.AcceptRole)
        self.cancel_button = self.button_box.addButton(self.t('cancel'), QDialogButtonBox.RejectRole)
        self.button_box.accepted.connect(self._validate_and_accept)
        self.button_box.rejected.connect(self.reject)

        root = QGridLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setHorizontalSpacing(18)
        root.setVerticalSpacing(14)
        root.addLayout(form, 0, 0)
        root.addWidget(info_box, 0, 1)
        root.addWidget(self.button_box, 1, 0, 1, 2)
        root.setColumnStretch(0, 3)
        root.setColumnStretch(1, 2)

    def _toggle_key_visibility(self, checked: bool):
        self.api_key_edit.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)

    def _validate_and_accept(self):
        data = self.get_data()
        if not data['api_url']:
            QMessageBox.warning(self, self.t('error_title'), self.t('api_url_empty'))
            return
        parsed = urlparse(data['api_url'])
        if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
            QMessageBox.warning(self, self.t('error_title'), self.t('api_url_invalid_dialog'))
            return
        if not data['api_key']:
            QMessageBox.warning(self, self.t('error_title'), self.t('api_key_empty'))
            return
        self.accept()

    def get_data(self) -> dict:
        return {
            'api_url': self.api_url_edit.text().strip(),
            'api_key': self.api_key_edit.text(),
            'api_version': self.api_version_edit.text().strip() or '0.1',
            'http_timeout': int(self.timeout_spin.value()),
            'max_pages_per_request': int(self.max_pages_spin.value()),
            'search_barcodes': self.search_barcodes_checkbox.isChecked(),
            'show_pages_separately': self.show_pages_checkbox.isChecked(),
        }
