from __future__ import annotations

import re

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .bootstrap import build_agent
from .models import ParsedSection
from .parsers import UnsupportedDocumentError, parse_document

app = FastAPI(
    title="DocOps Agent API",
    version="0.1.0",
    description="带引用、拒答和人工审批的可信企业知识智能体。",
)
agent, knowledge_base = build_agent()


class TextDocumentRequest(BaseModel):
    document_id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1)


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


class AgentRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    approved: bool = False


@app.get("/health")
def health() -> dict[str, object]:
    document_count = len({chunk.document_id for chunk in knowledge_base.chunks})
    return {"status": "ok", "documents": document_count}


@app.post("/documents/text")
def add_text_document(payload: TextDocumentRequest) -> dict[str, object]:
    chunks = knowledge_base.add_document(
        payload.document_id,
        payload.title,
        [ParsedSection(text=payload.text, page=1)],
    )
    return {"document_id": payload.document_id, "chunks": len(chunks)}


@app.post("/documents/upload")
async def upload_document(file: UploadFile = File(...)) -> dict[str, object]:
    filename = file.filename or "document.txt"
    try:
        sections = parse_document(filename, await file.read())
    except (UnsupportedDocumentError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    document_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", filename).strip("-").lower() or "upload"
    chunks = knowledge_base.add_document(document_id, filename, sections)
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
