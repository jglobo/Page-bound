"""Application-wide navy palette, including dialogs and native Qt controls."""

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


STYLE = """
QWidget { background: #101b2b; color: #e9f1fa; font-size: 10pt; }
QMainWindow, QDialog { background: #101b2b; }
QLabel { color: #e9f1fa; }
QLabel#heading { color: #f7fbff; font-size: 28pt; font-weight: 700; }
QLabel#dropArea {
    background: #172b43; color: #f1f8ff; font-size: 14pt;
    border: 2px dashed #67b8cb; border-radius: 14px;
}
QPushButton {
    background: #253b56; color: #f4f8ff; border: 1px solid #55718f;
    border-radius: 7px; padding: 8px 13px; font-weight: 600;
}
QPushButton:hover { background: #345574; border-color: #82c9db; }
QPushButton:pressed { background: #182f48; }
QPushButton:disabled { background: #19283a; color: #8ca1b7; border-color: #35485d; }
QPushButton#primary { background: #167a9a; border-color: #39a8c8; color: #ffffff; font-weight: 700; }
QPushButton#primary:hover { background: #1c93b6; }
QListWidget, QLineEdit, QTextEdit, QComboBox {
    background: #17283e; color: #f0f6fc; border: 1px solid #48627e;
    border-radius: 6px; padding: 6px; selection-background-color: #267aa2;
    selection-color: #ffffff;
}
QListWidget::item { color: #e9f1fa; padding: 3px; }
QListWidget::item:selected { background: #267aa2; color: #ffffff; border-radius: 5px; }
QLineEdit:focus, QTextEdit:focus, QComboBox:focus { border-color: #75c4d8; }
QLineEdit:disabled { color: #91a4b8; }
QComboBox::drop-down { border: 0; width: 24px; }
QComboBox QAbstractItemView { background: #17283e; color: #f0f6fc; selection-background-color: #267aa2; }
QCheckBox { color: #e9f1fa; spacing: 7px; }
QCheckBox::indicator { width: 16px; height: 16px; }
QProgressBar { background: #17283e; color: #f4f8ff; border: 1px solid #48627e; border-radius: 5px; text-align: center; min-height: 18px; }
QProgressBar::chunk { background: #168bad; border-radius: 4px; }
QMenuBar { background: #142237; color: #e9f1fa; }
QMenuBar::item:selected, QMenu::item:selected { background: #315575; }
QMenu { background: #17283e; color: #e9f1fa; border: 1px solid #48627e; }
QScrollBar { background: #17283e; }
QScrollBar::handle { background: #4b6d8b; border-radius: 5px; min-height: 20px; }
"""


def apply_theme(app: QApplication) -> None:
    palette = QPalette()
    colors = {
        QPalette.ColorRole.Window: "#101b2b",
        QPalette.ColorRole.WindowText: "#e9f1fa",
        QPalette.ColorRole.Base: "#17283e",
        QPalette.ColorRole.AlternateBase: "#20344d",
        QPalette.ColorRole.ToolTipBase: "#20344d",
        QPalette.ColorRole.ToolTipText: "#f0f6fc",
        QPalette.ColorRole.Text: "#f0f6fc",
        QPalette.ColorRole.Button: "#253b56",
        QPalette.ColorRole.ButtonText: "#f4f8ff",
        QPalette.ColorRole.BrightText: "#ffffff",
        QPalette.ColorRole.Highlight: "#267aa2",
        QPalette.ColorRole.HighlightedText: "#ffffff",
        QPalette.ColorRole.PlaceholderText: "#a4b9ce",
    }
    for role, value in colors.items():
        palette.setColor(role, QColor(value))
    app.setPalette(palette)
    app.setStyleSheet(STYLE)
