from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import json


@dataclass
class Metadata:
    title: str = ""
    author: str = ""
    language: str = "en"
    publisher: str = ""
    description: str = ""
    publication_date: str = ""
    isbn: str = ""
    cover_path: str = ""
    use_first_page_cover: bool = True


@dataclass
class Page:
    path: str
    rotation: int = 0


@dataclass
class Project:
    pages: list[Page] = field(default_factory=list)
    metadata: Metadata = field(default_factory=Metadata)
    quality: str = "Original"
    output_folder: str = ""
    output_name: str = ""
    pdf: bool = True
    epub: bool = True

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> tuple[Project, list[str]]:
        data = json.loads(path.read_text(encoding="utf-8"))
        project = cls(
            pages=[Page(**p) for p in data.get("pages", [])],
            metadata=Metadata(**data.get("metadata", {})),
            quality=data.get("quality", "Original"),
            output_folder=data.get("output_folder", ""),
            output_name=data.get("output_name", ""),
            pdf=data.get("pdf", True), epub=data.get("epub", True),
        )
        missing = [p.path for p in project.pages if not Path(p.path).is_file()]
        project.pages = [p for p in project.pages if p.path not in missing]
        return project, missing
