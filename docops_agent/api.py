from __future__ import annotations

import re
from hashlib import sha256
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel, StringConstraints

from .bootstrap import build_agent
from .config import Settings
from .models import ParsedSection
from .parsers import UnsupportedDocumentError, parse_document

app = FastAPI(
    title="DocOps Agent API",
    version="0.1.0",
    description="带引用、拒答和人工审批的可信企业知识智能体。",
)
settings = Settings.from_env()
agent, knowledge_base = build_agent(settings)

DocumentId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
UserInput = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class TextDocumentRequest(BaseModel):
    document_id: DocumentId
    title: Title
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class QueryRequest(BaseModel):
    question: UserInput


class AgentRequest(BaseModel):
    message: UserInput
    approved: bool = False


def _safe_filename(filename: str) -> str:
    return filename.replace("\\", "/").rsplit("/", maxsplit=1)[-1].strip() or "document.txt"


def _document_id(filename: str) -> str:
    stem = Path(filename).stem
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", stem).strip("-").lower()[:60]
    digest = sha256(filename.encode("utf-8")).hexdigest()[:10]
    return f"{slug or 'upload'}-{digest}"


def _validate_document_size(data: bytes) -> None:
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"文档大小不能超过 {settings.max_upload_bytes} 字节。",
        )


@app.get("/health")
def health() -> dict[str, object]:
    document_count = len({chunk.document_id for chunk in knowledge_base.chunks})
    return {"status": "ok", "documents": document_count}


@app.post("/documents/text")
def add_text_document(payload: TextDocumentRequest) -> dict[str, object]:
    _validate_document_size(payload.text.encode("utf-8"))
    chunks = knowledge_base.add_document(
        payload.document_id,
        payload.title,
        [ParsedSection(text=payload.text, page=1)],
    )
    return {"document_id": payload.document_id, "chunks": len(chunks)}


@app.post("/documents/upload")
async def upload_document(file: UploadFile = File(...)) -> dict[str, object]:
    filename = _safe_filename(file.filename or "document.txt")
    try:
        data = await file.read(settings.max_upload_bytes + 1)
    finally:
        await file.close()
    _validate_document_size(data)
    if not data:
        raise HTTPException(status_code=400, detail="上传文件不能为空。")
    try:
        sections = parse_document(filename, data)
        document_id = _document_id(filename)
        chunks = knowledge_base.add_document(document_id, filename, sections)
    except (UnsupportedDocumentError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"document_id": document_id, "chunks": len(chunks)}


@app.post("/query")
def query(payload: QueryRequest) -> dict[str, object]:
    return agent.rag.answer(payload.question).to_dict()


@app.post("/agent/run")
def run_agent(payload: AgentRequest) -> dict[str, object]:
    return agent.run(payload.message, approved=payload.approved).to_dict()


@app.get("/tickets")
def list_tickets() -> list[dict[str, object]]:
    return [ticket.to_dict() for ticket in agent.tickets.list()]
