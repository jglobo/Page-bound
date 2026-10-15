# Pagebound

A local Python desktop app that turns scanned book-page images into image-based PDF and fixed-layout EPUB 3 ebooks. Built with PySide6, Pillow, and img2pdf.

## Features

- Import JPG, JPEG, PNG, and WEBP files or recursively scan folders.
- Sort pages naturally, preview them, and reorder, rotate, or remove pages.
- Add book metadata and a cover image.
- Export PDF, EPUB, or both with Original, Balanced, or Smaller quality.
- Save and reopen projects containing image paths and page edits.

## Setup and run

Requires Python 3.10 or later. Run these commands in PowerShell from the **project root** (the folder above `src`):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\run.ps1
```

After setup, you can also double-click **Open Pagebound.bat** in the project root.

## Source layout

```text
src/
└── ebook_builder/
    ├── app.py              # Application entry point and logging
    ├── core/
    │   ├── discovery.py    # Image discovery and natural sorting
    │   ├── images.py       # Image preparation, rotation, and quality
    │   ├── model.py        # Page, metadata, and project persistence
    │   └── export.py       # PDF and EPUB generation
    └── gui/
        ├── main_window.py # Desktop interface and background tasks
        └── theme.py       # Application colors and styling
```

## Tests

From the project root after setup:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
.\.venv\Scripts\python.exe -m pytest -q
```

## Notes

Processing happens locally. Exports contain images, not searchable text; no OCR is included. Project files reference the original images, so keep those files in place. EPUB display depends on the reader's support for fixed-layout books.
