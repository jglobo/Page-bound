import logging
from pathlib import Path
import sys
from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QApplication
from .gui.main_window import MainWindow
from .gui.theme import apply_theme


def main():
    log_dir = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=log_dir / "pagebound.log", level=logging.INFO)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    apply_theme(app)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
