"""
Tema escuro (QSS) para a aplicação — cores alinhadas a UIs de IDE modernas.
"""
from __future__ import annotations

# Paleta base: fundo, superfícies, texto, bordas, destaque
_BG = "#1a1a1c"
_BG_ELEV = "#222226"
_BG_INPUT = "#2a2a2e"
_TEXT = "#e4e4e7"
_TEXT_MUTED = "#a1a1aa"
_BORDER = "#3f3f46"
_ACCENT = "#3b82f6"
_ACCENT_HOVER = "#60a5fa"


def app_stylesheet() -> str:
    return f"""
QMainWindow, QDialog {{
    background-color: {_BG};
    color: {_TEXT};
}}
QFrame#contentHost {{
    background-color: {_BG};
    border: none;
}}
/* Pré-bets LoL: evita fundo branco no QScrollArea / conteúdo */
QWidget#LoLPrebetsRoot,
QScrollArea#prebetsScrollArea,
QWidget#prebetsHudRoot,
QWidget#prebetsHudHost {{
    background-color: #0e1117;
}}
QScrollArea#prebetsScrollArea > QWidget > QWidget {{
    background-color: #0e1117;
}}
QStackedWidget {{
    background-color: {_BG};
}}
QWidget {{
    color: {_TEXT};
    font-size: 13px;
}}
QFrame#sidebar {{
    background-color: {_BG_ELEV};
    border: none;
    border-right: 1px solid {_BORDER};
}}
QLabel#sidebarTitle {{
    color: {_TEXT};
    font-size: 16px;
    font-weight: 600;
    padding: 4px 8px 12px 8px;
}}
QLabel#sidebarSub {{
    color: {_TEXT_MUTED};
    font-size: 11px;
    padding: 0 8px 8px 8px;
}}
QListWidget#nav {{
    background-color: transparent;
    border: none;
    outline: none;
    padding: 4px;
}}
QListWidget#nav::item {{
    color: {_TEXT};
    padding: 10px 12px;
    border-radius: 6px;
    margin: 2px 0;
}}
QListWidget#nav::item:selected {{
    background-color: {_BG_INPUT};
    color: {_TEXT};
    border: 1px solid {_BORDER};
}}
QListWidget#nav::item:hover:!selected {{
    background-color: {_BG_INPUT};
}}
QGroupBox {{
    font-weight: 600;
    border: 1px solid {_BORDER};
    border-radius: 8px;
    margin-top: 12px;
    padding: 12px 8px 8px 8px;
    background-color: {_BG_ELEV};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    padding: 0 6px;
    color: {_TEXT_MUTED};
}}
QPushButton {{
    background-color: {_ACCENT};
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 500;
    min-height: 22px;
}}
QPushButton:hover {{
    background-color: {_ACCENT_HOVER};
}}
QPushButton:pressed {{
    background-color: #2563eb;
}}
QPushButton:disabled {{
    background-color: {_BORDER};
    color: {_TEXT_MUTED};
}}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit {{
    background-color: {_BG_INPUT};
    border: 1px solid {_BORDER};
    border-radius: 6px;
    padding: 6px 8px;
    min-height: 20px;
    color: {_TEXT};
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox QAbstractItemView {{
    background-color: {_BG_ELEV};
    color: {_TEXT};
    border: 1px solid {_BORDER};
    selection-background-color: {_BG_INPUT};
}}
QCheckBox {{
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {_BORDER};
    border-radius: 3px;
    background-color: {_BG_INPUT};
}}
QCheckBox::indicator:checked {{
    background-color: {_ACCENT};
    border-color: {_ACCENT};
}}
QTabWidget::pane {{
    border: 1px solid {_BORDER};
    border-radius: 6px;
    top: -1px;
    background-color: {_BG_ELEV};
}}
QTabBar::tab {{
    background-color: {_BG};
    color: {_TEXT_MUTED};
    border: 1px solid {_BORDER};
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 8px 14px;
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    background-color: {_BG_ELEV};
    color: {_TEXT};
    border-bottom: 1px solid {_BG_ELEV};
    font-weight: 500;
}}
QTableView, QTableWidget {{
    background-color: {_BG_INPUT};
    alternate-background-color: {_BG_ELEV};
    gridline-color: {_BORDER};
    border: 1px solid {_BORDER};
    border-radius: 6px;
    selection-background-color: #1e3a5f;
}}
QHeaderView::section {{
    background-color: {_BG_ELEV};
    color: {_TEXT_MUTED};
    border: none;
    border-bottom: 1px solid {_BORDER};
    padding: 6px;
}}
QScrollBar:vertical {{
    background: {_BG};
    width: 10px;
    margin: 0;
    border-radius: 5px;
}}
QScrollBar::handle:vertical {{
    background: {_BORDER};
    min-height: 32px;
    border-radius: 5px;
}}
QScrollBar::handle:vertical:hover {{
    background: #52525b;
}}
QStatusBar {{
    background-color: {_BG_ELEV};
    color: {_TEXT_MUTED};
    border-top: 1px solid {_BORDER};
    padding: 4px 8px;
}}
QMessageBox {{
    background-color: {_BG_ELEV};
}}
QMessageBox QLabel {{
    color: {_TEXT};
}}
QProgressBar {{
    border: 1px solid {_BORDER};
    border-radius: 4px;
    text-align: center;
    background-color: {_BG_INPUT};
    min-height: 20px;
}}
QProgressBar::chunk {{
    background-color: {_ACCENT};
    border-radius: 3px;
}}
"""


def apply_fusion(app) -> None:
    """Fusion + stylesheet para tema consistente em toda a app (inclui diálogos)."""
    from PySide6.QtWidgets import QApplication

    if isinstance(app, QApplication):
        app.setStyle("Fusion")
        app.setStyleSheet(app_stylesheet())
