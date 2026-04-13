# -*- coding: utf-8 -*-

from __future__ import annotations

CURRENT_LANG = "en"

STATUS_LABELS = {
    "pl": {
        "queued": "W kolejce",
        "running": "W toku",
        "done": "Gotowe",
        "error": "Błąd",
        "cancelled": "Anulowano",
    },
    "en": {
        "queued": "Queued",
        "running": "Running",
        "done": "Done",
        "error": "Error",
        "cancelled": "Cancelled",
    },
}

STATUS_COLORS = {
    "queued": "#486176",
    "running": "#0C6F98",
    "done": "#0F7B5F",
    "error": "#B5404E",
    "cancelled": "#8A5A10",
}

STATUS_BACKGROUNDS = {
    "queued": "#EEF3F7",
    "running": "#E3F6FC",
    "done": "#E6F7F1",
    "error": "#FCEBED",
    "cancelled": "#FBF2E2",
}


def set_language(lang: str) -> None:
    global CURRENT_LANG
    CURRENT_LANG = "pl" if lang == "pl" else "en"


def status_label(status: str) -> str:
    return STATUS_LABELS.get(CURRENT_LANG, STATUS_LABELS["en"]).get(status, status or "-")


def status_color(status: str) -> str:
    return STATUS_COLORS.get(status, "#314457")


def status_background(status: str) -> str:
    return STATUS_BACKGROUNDS.get(status, "#EEF3F7")


APP_STYLESHEET = """
QMainWindow, QWidget {
    background: #F4F7FA;
    color: #152434;
    font-size: 13px;
}

QMenuBar {
    background: #EEF3F7;
    border-bottom: 1px solid #D5DEE8;
}

QMenuBar::item {
    background: transparent;
    padding: 6px 10px;
    border-radius: 8px;
}

QMenuBar::item:selected,
QMenu::item:selected {
    background: #E2F4FB;
}

QMenu {
    background: #FFFFFF;
    border: 1px solid #D5DEE8;
    padding: 6px;
}

QMainWindow::separator,
QSplitter::handle {
    background: transparent;
}

QFrame#headerCard,
QGroupBox,
QFrame#card,
QFrame#infoCard,
QFrame#statCard {
    background: #FFFFFF;
    border: 1px solid #D7E0EA;
    border-radius: 16px;
}

QWidget#sidebarPanel,
QWidget#workAreaPanel {
    background: transparent;
}

QFrame#headerCard {
    border-radius: 18px;
}

QLabel[pageTitle="true"] {
    font-size: 26px;
    font-weight: 800;
    color: #0F1F2F;
}

QLabel[sectionTitle="true"] {
    font-size: 15px;
    font-weight: 700;
    color: #153046;
}

QLabel[muted="true"] {
    color: #688096;
}

QLabel[statValue="true"] {
    font-size: 28px;
    font-weight: 800;
    color: #0F1F2F;
}

QGroupBox {
    margin-top: 12px;
    padding: 14px 14px 14px 14px;
    font-weight: 700;
    color: #153046;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    top: -3px;
    padding: 0 6px;
    background: #FFFFFF;
}

QFrame#statCard {
    min-height: 76px;
}

QFrame#dropZone {
    background: #FBFDFF;
    border: 2px dashed #B7D4E8;
    border-radius: 16px;
}

QFrame#dropZone[dragActive="true"] {
    background: #ECFAFE;
    border: 2px dashed #14BFE8;
}

QLabel#connectionBadge,
QLabel[statusBadge="true"] {
    border-radius: 999px;
    padding: 7px 12px;
    font-weight: 700;
}

QLabel#connectionBadge[connected="true"] {
    color: #0F7B5F;
    background: #E7F7F0;
    border: 1px solid #B9E7D7;
}

QLabel#connectionBadge[connected="false"] {
    color: #9C3A46;
    background: #FDECEF;
    border: 1px solid #F4C8D0;
}

QPushButton {
    min-height: 38px;
    border-radius: 12px;
    border: 1px solid #C9D5E2;
    background: #FFFFFF;
    color: #163048;
    padding: 0 14px;
    font-weight: 600;
}

QPushButton:hover {
    background: #F6FBFE;
    border-color: #AFC7DB;
}

QPushButton:pressed {
    background: #EDF6FB;
}

QPushButton[role="primary"] {
    background: #14C6EC;
    color: #082230;
    border: 1px solid #10B7DB;
}

QPushButton[role="primary"]:hover {
    background: #27CEF0;
    border: 1px solid #12BBDF;
}

QPushButton[role="danger"] {
    background: #FFF7F8;
    color: #B5404E;
    border: 1px solid #E9C4CB;
}

QPushButton[role="danger"]:hover {
    background: #FDEDEF;
    border: 1px solid #E0B3BC;
}

QPushButton:disabled {
    background: #F4F7FA;
    color: #9AACBC;
    border-color: #DCE4EC;
}

QLineEdit,
QPlainTextEdit,
QTableWidget,
QComboBox,
QSpinBox {
    background: #FBFDFF;
    color: #152434;
    border: 1px solid #C9D5E2;
    border-radius: 12px;
    padding: 8px 10px;
    selection-background-color: #D9F4FC;
    selection-color: #0A2230;
}

QLineEdit:focus,
QPlainTextEdit:focus,
QTableWidget:focus,
QComboBox:focus,
QSpinBox:focus {
    border: 1px solid #14BFE8;
}

QLineEdit[readOnly="true"] {
    background: #F7FAFC;
}

QCheckBox {
    spacing: 8px;
    color: #254055;
}

QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 6px;
    border: 1px solid #B7C7D8;
    background: #FFFFFF;
}

QCheckBox::indicator:checked {
    background: #14C6EC;
    border: 1px solid #10B7DB;
}

QTableWidget {
    gridline-color: transparent;
    alternate-background-color: #F8FBFD;
}

QTableWidget::item {
    padding: 8px 6px;
    border: 0;
}

QHeaderView::section {
    background: #F7FAFD;
    color: #3D556B;
    padding: 11px 8px;
    border: 0;
    border-bottom: 1px solid #DDE5ED;
    font-weight: 700;
}

QTabWidget::pane {
    border: 1px solid #D7E0EA;
    background: #FFFFFF;
    border-radius: 16px;
    top: -1px;
}

QTabBar::tab {
    background: #EEF3F7;
    color: #526A7F;
    border-top-left-radius: 11px;
    border-top-right-radius: 11px;
    padding: 10px 14px;
    margin-right: 4px;
    font-weight: 700;
}

QTabBar::tab:selected {
    background: #FFFFFF;
    color: #142739;
}

QProgressBar {
    border: 1px solid #D5DEE8;
    border-radius: 10px;
    text-align: center;
    background: #EEF3F7;
    min-height: 18px;
}

QProgressBar::chunk {
    background: #14C6EC;
    border-radius: 10px;
}

QScrollBar:vertical {
    background: transparent;
    width: 12px;
    margin: 4px;
}

QScrollBar::handle:vertical {
    background: #C6D4E1;
    min-height: 28px;
    border-radius: 6px;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical,
QScrollBar:horizontal,
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {
    background: transparent;
    border: none;
    height: 0;
    width: 0;
}
"""
