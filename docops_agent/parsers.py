from __future__ import annotations

import csv
from io import BytesIO, StringIO
from pathlib import Path

from .models import ParsedSection


class UnsupportedDocumentError(ValueError):
    pass


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("无法识别文本编码，请转换为 UTF-8 后重试。")


def parse_document(filename: str, data: bytes) -> list[ParsedSection]:
    suffix = Path(filename).suffix.lower()
    if suffix in {".txt", ".md"}:
        return [ParsedSection(text=_decode(data), page=1)]
    if suffix == ".csv":
        reader = csv.reader(StringIO(_decode(data)))
        text = "\n".join(" | ".join(cell.strip() for cell in row) for row in reader)
        return [ParsedSection(text=text, page=1)]
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError("解析 PDF 需要安装 pypdf。") from exc
        try:
            reader = PdfReader(BytesIO(data))
            sections: list[ParsedSection] = []
            for index, page in enumerate(reader.pages, start=1):
                text = page.extract_text() or ""
                if text.strip():
                    sections.append(ParsedSection(text=text, page=index))
            return sections
        except Exception as exc:
            raise ValueError("无法解析 PDF，请确认文件未损坏且包含可提取文本。") from exc
    raise UnsupportedDocumentError("当前支持 .txt、.md、.csv 和文本型 .pdf 文件。")
