from __future__ import annotations

from pathlib import Path
import logging

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal, QStandardPaths, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox,
    QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QProgressBar, QPushButton, QTextEdit,
    QVBoxLayout, QWidget)

from ebook_builder.core.discovery import discover
from ebook_builder.core.export import Cancelled, export_project
from ebook_builder.core.images import UnreadablePage, open_page
from ebook_builder.core.model import Metadata, Page, Project

LOG = logging.getLogger(__name__)


class Signals(QObject):
    progress = Signal(str, int, int)
    done = Signal(object)
    failed = Signal(str)
    thumbnail = Signal(str, object)


class Work(QRunnable):
    def __init__(self, function):
        super().__init__()
        self.function = function
        self.signals = Signals()
        self.cancelled = False

    def run(self):
        try:
            self.signals.done.emit(self.function(self.signals.progress.emit, lambda: self.cancelled))
        except Cancelled:
            self.signals.failed.emit("Operation cancelled.")
        except Exception as exc:
            LOG.exception("Background task failed")
            self.signals.failed.emit(str(exc))


class DropArea(QLabel):
    dropped = Signal(list)

    def __init__(self):
        super().__init__("Drop book pages or folders here\nJPG · PNG · WEBP")
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(110)
        self.setObjectName("dropArea")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        self.dropped.emit([u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()])
        event.acceptProposedAction()


class Gallery(QListWidget):
    def __init__(self):
        super().__init__()
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setIconSize(QPixmap(125, 165).size())
        self.setGridSize(QPixmap(156, 205).size())
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setMovement(QListWidget.Movement.Snap)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)


class MetadataDialog(QDialog):
    def __init__(self, data: Metadata, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Book details")
        layout = QFormLayout(self)
        self.inputs = {}
        for key, label in (("title", "Title *"), ("author", "Author *"), ("language", "Language"),
                           ("publisher", "Publisher"), ("publication_date", "Date (YYYY-MM-DD)"), ("isbn", "ISBN")):
            edit = QLineEdit(getattr(data, key))
            layout.addRow(label, edit)
            self.inputs[key] = edit
        self.description = QTextEdit(data.description)
        self.description.setMaximumHeight(80)
        layout.addRow("Description", self.description)
        cover_row = QHBoxLayout()
        self.cover = QLineEdit(data.cover_path)
        cover_row.addWidget(self.cover)
        browse = QPushButton("Browse")
        browse.clicked.connect(self.browse_cover)
        cover_row.addWidget(browse)
        layout.addRow("Cover image", cover_row)
        self.first_cover = QCheckBox("Use first page when no cover is selected")
        self.first_cover.setChecked(data.use_first_page_cover)
        layout.addRow(self.first_cover)
        save = QPushButton("Save details")
        save.clicked.connect(self.accept)
        layout.addRow(save)

    def browse_cover(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose cover", "", "Images (*.jpg *.jpeg *.png *.webp)")
        if path:
            self.cover.setText(path)

    def value(self):
        return Metadata(**{key: edit.text().strip() for key, edit in self.inputs.items()},
                        description=self.description.toPlainText().strip(), cover_path=self.cover.text().strip(),
                        use_first_page_cover=self.first_cover.isChecked())


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pagebound · Image to Ebook")
        self.resize(1050, 800)
        self.project = Project()
        self.pool = QThreadPool.globalInstance()
        self.task = None
        self.output_paths = []
        self.thumbnail_cache = {}
        self.thumb_task = None
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        heading = QLabel("Pagebound")
        heading.setObjectName("heading")
        outer.addWidget(heading)
        outer.addWidget(QLabel("Turn your scanned pages into a book. Everything stays on this computer."))
        self.drop = DropArea()
        self.drop.dropped.connect(self.import_paths)
        outer.addWidget(self.drop)
        add = QPushButton("Add images or folders")
        add.clicked.connect(self.pick_images)
        add_folder = QPushButton("Add folder")
        add_folder.clicked.connect(self.pick_folder)
        add_row = QHBoxLayout()
        add_row.addWidget(add); add_row.addWidget(add_folder); add_row.addStretch()
        outer.addLayout(add_row)
        self.gallery = Gallery()
        self.gallery.model().rowsMoved.connect(self.sync_order)
        self.gallery.itemDoubleClicked.connect(self.preview)
        outer.addWidget(self.gallery, 1)
        actions = QHBoxLayout()
        for label, method in (("Earlier", lambda: self.move(-1)), ("Later", lambda: self.move(1)),
                              ("Rotate left", lambda: self.rotate(-90)), ("Rotate right", lambda: self.rotate(90)),
                              ("Remove", self.remove), ("Clear", self.clear), ("Book details", self.edit_metadata)):
            button = QPushButton(label)
            button.clicked.connect(method)
            actions.addWidget(button)
        outer.addLayout(actions)
        row = QHBoxLayout()
        self.pdf = QCheckBox("PDF")
        self.pdf.setChecked(True)
        self.epub = QCheckBox("EPUB")
        self.epub.setChecked(True)
        row.addWidget(QLabel("Output")); row.addWidget(self.pdf); row.addWidget(self.epub)
        row.addSpacing(20); row.addWidget(QLabel("Quality"))
        self.quality = QComboBox()
        self.quality.addItems(["Original", "Balanced", "Smaller"])
        row.addWidget(self.quality); row.addStretch()
        outer.addLayout(row)
        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("Output folder"))
        documents = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
        self.folder = QLineEdit(documents or str(Path.home()))
        path_row.addWidget(self.folder)
        browse = QPushButton("Browse")
        browse.clicked.connect(self.pick_output)
        path_row.addWidget(browse)
        outer.addLayout(path_row)
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("File name"))
        self.filename = QLineEdit()
        self.filename.setPlaceholderText("Uses book title if blank")
        name_row.addWidget(self.filename)
        outer.addLayout(name_row)
        bottom = QHBoxLayout()
        self.create = QPushButton("Create Ebook")
        self.create.setObjectName("primary")
        self.create.clicked.connect(self.export)
        bottom.addWidget(self.create)
        self.cancel = QPushButton("Cancel")
        self.cancel.setEnabled(False)
        self.cancel.clicked.connect(self.cancel_task)
        bottom.addWidget(self.cancel)
        self.open_folder = QPushButton("Open Output Folder")
        self.open_folder.setEnabled(False)
        self.open_folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.folder.text())))
        bottom.addWidget(self.open_folder)
        outer.addLayout(bottom)
        self.progress = QProgressBar()
        self.progress.setValue(0)
        outer.addWidget(self.progress)
        self.status = QLabel("Ready")
        outer.addWidget(self.status)
        menu = self.menuBar().addMenu("Project")
        for name, method in (("Open project", self.open_project), ("Save project", self.save_project)):
            action = QAction(name, self)
            action.triggered.connect(method)
            menu.addAction(action)

    def pick_images(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Choose pages", "", "Images (*.jpg *.jpeg *.png *.webp)")
        if files:
            self.import_paths(files)

    def pick_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose image folder")
        if folder:
            self.import_paths([folder])

    def import_paths(self, paths):
        self.set_busy(True)
        task = Work(lambda progress, cancelled: discover(paths, lambda n: progress("Finding images", n, 0), cancelled))
        task.signals.done.connect(self.import_done)
        task.signals.failed.connect(self.failed)
        task.signals.progress.connect(self.update_progress)
        self.task = task
        self.pool.start(task)

    def import_done(self, pages):
        existing = {p.path.casefold() for p in self.project.pages}
        new = [p for p in pages if p.path.casefold() not in existing]
        self.project.pages.extend(new)
        self.set_busy(False)
        self.status.setText(f"Added {len(new)} pages. {len(self.project.pages)} total.")
        self.refresh()

    def refresh(self):
        if self.thumb_task:
            self.thumb_task.cancelled = True
        self.gallery.clear()
        for i, page in enumerate(self.project.pages, 1):
            item = QListWidgetItem(f"{i}. {Path(page.path).name}")
            item.setData(Qt.ItemDataRole.UserRole, page)
            self.gallery.addItem(item)
            cached = self.thumbnail_cache.get((page.path, page.rotation))
            if cached:
                item.setIcon(QIcon(QPixmap.fromImage(cached)))
        self.load_thumbnails()

    def load_thumbnails(self):
        from PIL.ImageQt import ImageQt
        pages = [Page(p.path, p.rotation) for p in self.project.pages if (p.path, p.rotation) not in self.thumbnail_cache]
        if not pages:
            return
        task = Work(lambda progress, cancelled: self._make_thumbnails(pages, progress, cancelled, task.signals.thumbnail.emit))
        task.signals.thumbnail.connect(self.show_thumbnail)
        task.signals.progress.connect(self.update_progress)
        task.signals.failed.connect(self.failed)
        self.thumb_task = task
        self.pool.start(task)

    @staticmethod
    def _make_thumbnails(pages, progress, cancelled, emit):
        from PIL.ImageQt import ImageQt
        for i, page in enumerate(pages, 1):
            if cancelled():
                return
            try:
                image = open_page(page)
                image.thumbnail((125, 165))
                emit(page.path + "|" + str(page.rotation), QImage(ImageQt(image)).copy())
                image.close()
            except UnreadablePage:
                LOG.exception("Thumbnail failed: %s", page.path)
            progress("Making thumbnails", i, len(pages))

    def show_thumbnail(self, key, image):
        path, rotation = key.rsplit("|", 1)
        self.thumbnail_cache[(path, int(rotation))] = image
        for i in range(self.gallery.count()):
            item = self.gallery.item(i)
            page = item.data(Qt.ItemDataRole.UserRole)
            if page.path == path and page.rotation == int(rotation):
                item.setIcon(QIcon(QPixmap.fromImage(image)))

    def sync_order(self, *args):
        self.project.pages = [self.gallery.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.gallery.count())]
        self.renumber()

    def renumber(self):
        for i in range(self.gallery.count()):
            item = self.gallery.item(i)
            item.setText(f"{i+1}. {Path(item.data(Qt.ItemDataRole.UserRole).path).name}")

    def selected_rows(self):
        return sorted((self.gallery.row(item) for item in self.gallery.selectedItems()))

    def move(self, direction):
        rows = self.selected_rows()
        if not rows:
            return
        for row in (rows if direction < 0 else reversed(rows)):
            other = row + direction
            if 0 <= other < len(self.project.pages):
                self.project.pages[row], self.project.pages[other] = self.project.pages[other], self.project.pages[row]
        self.refresh()
        for row in rows:
            target = row + direction
            if 0 <= target < self.gallery.count():
                self.gallery.item(target).setSelected(True)

    def rotate(self, angle):
        for row in self.selected_rows():
            page = self.project.pages[row]
            page.rotation = (page.rotation + angle) % 360
        self.refresh()

    def remove(self):
        for row in reversed(self.selected_rows()):
            self.project.pages.pop(row)
        self.refresh()

    def clear(self):
        self.project.pages.clear()
        self.refresh()

    def preview(self, item):
        page = item.data(Qt.ItemDataRole.UserRole)
        try:
            from PIL.ImageQt import ImageQt
            image = open_page(page)
            image.thumbnail((900, 900))
            dialog = QDialog(self)
            dialog.setWindowTitle(Path(page.path).name)
            layout = QVBoxLayout(dialog)
            label = QLabel()
            label.setPixmap(QPixmap.fromImage(ImageQt(image)))
            layout.addWidget(label)
            image.close()
            dialog.exec()
        except UnreadablePage as exc:
            QMessageBox.warning(self, "Unreadable page", str(exc))

    def edit_metadata(self):
        dialog = MetadataDialog(self.project.metadata, self)
        if dialog.exec():
            self.project.metadata = dialog.value()

    def pick_output(self):
        path = QFileDialog.getExistingDirectory(self, "Output folder", self.folder.text())
        if path:
            self.folder.setText(path)

    def export(self):
        if not self.project.pages:
            QMessageBox.warning(self, "No pages", "Add book pages first.")
            return
        if not self.project.metadata.title or not self.project.metadata.author:
            self.edit_metadata()
            if not self.project.metadata.title or not self.project.metadata.author:
                return
        if not (self.pdf.isChecked() or self.epub.isChecked()):
            QMessageBox.warning(self, "Choose output", "Select PDF, EPUB, or both.")
            return
        output = Path(self.folder.text())
        if not output.is_dir():
            QMessageBox.warning(self, "Output folder", "Choose an existing output folder.")
            return
        self.project.quality = self.quality.currentText()
        self.project.pdf = self.pdf.isChecked()
        self.project.epub = self.epub.isChecked()
        self.project.output_folder = str(output)
        self.project.output_name = self.filename.text().strip()
        self.set_busy(True)
        task = Work(lambda progress, cancelled: export_project(self.project, output, progress, cancelled))
        task.signals.done.connect(self.export_done)
        task.signals.failed.connect(self.failed)
        task.signals.progress.connect(self.update_progress)
        self.task = task
        self.pool.start(task)

    def export_done(self, value):
        paths, warnings = value
        self.set_busy(False)
        self.open_folder.setEnabled(True)
        self.status.setText("Created: " + ", ".join(p.name for p in paths))
        QMessageBox.information(self, "Ebook created", "\n".join(str(p) for p in paths) + ("\n\n" + "\n".join(warnings) if warnings else ""))

    def failed(self, message):
        self.set_busy(False)
        QMessageBox.warning(self, "Could not finish", message)
        self.status.setText(message)

    def update_progress(self, stage, current, total):
        self.status.setText(f"{stage}: {current}" + (f" / {total}" if total else ""))
        self.progress.setValue(round(100 * current / total) if total else 0)

    def set_busy(self, busy):
        self.create.setEnabled(not busy)
        self.cancel.setEnabled(busy)

    def cancel_task(self):
        if self.task:
            self.task.cancelled = True

    def save_project(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save project", "", "Ebook project (*.ebookproject)")
        if path:
            self.project.output_folder = self.folder.text()
            self.project.output_name = self.filename.text().strip()
            self.project.quality = self.quality.currentText()
            self.project.pdf = self.pdf.isChecked()
            self.project.epub = self.epub.isChecked()
            self.project.save(Path(path))

    def open_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open project", "", "Ebook project (*.ebookproject)")
        if path:
            try:
                self.project, missing = Project.load(Path(path))
                self.folder.setText(self.project.output_folder)
                self.filename.setText(self.project.output_name)
                self.quality.setCurrentText(self.project.quality)
                self.pdf.setChecked(self.project.pdf)
                self.epub.setChecked(self.project.epub)
                self.refresh()
                if missing:
                    QMessageBox.warning(self, "Missing pages", f"{len(missing)} source files are missing and were skipped.\n" + "\n".join(missing[:10]))
            except (OSError, ValueError, TypeError) as exc:
                LOG.exception("Could not open project")
                QMessageBox.warning(self, "Could not open project", str(exc))
