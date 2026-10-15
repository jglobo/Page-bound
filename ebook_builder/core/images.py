from __future__ import annotations

from io import BytesIO
from pathlib import Path
from PIL import Image, ImageOps

from .model import Page


class UnreadablePage(Exception):
    pass


def open_page(page: Page) -> Image.Image:
    try:
        with Image.open(page.path) as source:
            image = ImageOps.exif_transpose(source)
            image.load()
        if page.rotation:
            image = image.rotate(-page.rotation, expand=True)
        return image
    except (OSError, ValueError) as exc:
        raise UnreadablePage(f"Could not read {Path(page.path).name}: {exc}") from exc


def jpeg_bytes(page: Page, quality: str) -> tuple[bytes, tuple[int, int]]:
    image = open_page(page)
    try:
        if quality == "Original" and image.format == "JPEG" and not page.rotation:
            # EXIF transpose may change pixels; only reuse when orientation is normal.
            with Image.open(page.path) as source:
                if source.getexif().get(274, 1) == 1:
                    return Path(page.path).read_bytes(), image.size
        max_edge = {"Balanced": 3000, "Smaller": 1800}.get(quality)
        if max_edge:
            image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
        if image.mode not in ("RGB", "L"):
            if "A" in image.getbands():
                background = Image.new("RGB", image.size, "white")
                background.paste(image, mask=image.getchannel("A"))
                image = background
            else:
                image = image.convert("RGB")
        output = BytesIO()
        image.save(output, format="JPEG", quality={"Original": 95, "Balanced": 88, "Smaller": 76}[quality], optimize=True)
        return output.getvalue(), image.size
    finally:
        image.close()
