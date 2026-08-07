from __future__ import annotations

import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from hashlib import sha256
from pathlib import Path
from typing import Annotated, NoReturn

from fastapi import Depends, FastAPI, File, HTTPException, Query, Security, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, StringConstraints
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import __version__
from .bootstrap import build_agent
from .config import Settings
from .models import ParsedSection
from .observability import RequestLoggingMiddleware, configure_logging
from .parsers import UnsupportedDocumentError, parse_document
from .security import ApiKeyAuthenticator, Principal
from .workflow import (
    ApprovalConflictError,
    ApprovalExpiredError,
    ApprovalNotFoundError,
)

settings = Settings.from_env()
logger = configure_logging(settings.log_level)
authenticator = ApiKeyAuthenticator(
    settings.api_keys,
    required=settings.environment == "production",
)
agent, knowledge_base = build_agent(settings)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    logger.info(
        "application.started",
        extra={
            "version": __version__,
            "environment": settings.environment,
            "authentication_enabled": authenticator.enabled,
        },
    )
    try:
        yield
    finally:
        repository = knowledge_base.repository
        if repository is not None:
            repository.close()
        logger.info("application.stopped")


app = FastAPI(
    title="DocOps Agent API",
    version=__version__,
    description="带引用、拒答、持久化审批和审计记录的企业知识智能体。",
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
    lifespan=lifespan,
)
app.state.settings = settings
app.state.agent = agent
app.state.knowledge_base = knowledge_base
app.add_middleware(RequestLoggingMiddleware, logger=logger)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.trusted_hosts))
if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "X-API-Key", "X-Request-ID"],
    )

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

DocumentId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=80,
        pattern=r"^[a-zA-Z0-9_-]+$",
    ),
]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
UserInput = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
ApprovalId = Annotated[
    str,
    StringConstraints(pattern=r"^APR-[A-F0-9]{12}$"),
]


class TextDocumentRequest(BaseModel):
    document_id: DocumentId
    title: Title
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class QueryRequest(BaseModel):
    question: UserInput


class AgentRequest(BaseModel):
    message: UserInput


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


def current_principal(
    supplied_key: Annotated[str | None, Security(api_key_header)],
) -> Principal:
    principal = authenticator.authenticate(supplied_key)
    if principal is None:
        logger.warning("authentication.failed")
        raise HTTPException(
            status_code=401,
            detail="缺少或无效的 API Key。",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return principal


def _require_permission(principal: Principal, permission: str) -> Principal:
    if not authenticator.authorize(principal, permission):
        raise HTTPException(status_code=403, detail="当前 API Key 没有执行该操作的权限。")
    return principal


def require_reader(
    principal: Annotated[Principal, Depends(current_principal)],
) -> Principal:
    return _require_permission(principal, "read")


def require_operator(
    principal: Annotated[Principal, Depends(current_principal)],
) -> Principal:
    return _require_permission(principal, "operate")


def require_admin(
    principal: Annotated[Principal, Depends(current_principal)],
) -> Principal:
    return _require_permission(principal, "admin")


def _raise_approval_http_error(exc: Exception) -> NoReturn:
    if isinstance(exc, ApprovalNotFoundError):
        raise HTTPException(status_code=404, detail="审批不存在。") from exc
    if isinstance(exc, ApprovalExpiredError):
        raise HTTPException(status_code=410, detail="审批已过期。") from exc
    if isinstance(exc, ApprovalConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise exc


@app.get("/health/live")
def liveness() -> dict[str, object]:
    return {"status": "ok", "version": __version__}


@app.get("/health/ready")
def readiness() -> dict[str, object]:
    repository = knowledge_base.repository
    try:
        ready = repository is None or repository.ping()
    except Exception as exc:
        logger.exception("readiness.failed")
        raise HTTPException(status_code=503, detail="持久化存储不可用。") from exc
    if not ready:
        raise HTTPException(status_code=503, detail="持久化存储不可用。")
    return {
        "status": "ready",
        "version": __version__,
        "documents": len(knowledge_base.documents),
    }


@app.get("/health")
def health() -> dict[str, object]:
    return readiness()


@app.get("/me")
def me(principal: Annotated[Principal, Depends(require_reader)]) -> dict[str, str]:
    return {"name": principal.name, "role": principal.role}


@app.get("/documents")
def list_documents(
    _principal: Annotated[Principal, Depends(require_reader)],
) -> list[dict[str, object]]:
    return [document.to_dict() for document in knowledge_base.documents]


@app.post("/documents/text")
def add_text_document(
    payload: TextDocumentRequest,
    principal: Annotated[Principal, Depends(require_admin)],
) -> dict[str, object]:
    _validate_document_size(payload.text.encode("utf-8"))
    existed = knowledge_base.has_document(payload.document_id)
    chunks = knowledge_base.add_document(
        payload.document_id,
        payload.title,
        [ParsedSection(text=payload.text, page=1)],
    )
    agent.audit.record(
        "document.updated" if existed else "document.created",
        principal.name,
        "document",
        payload.document_id,
        {"chunks": len(chunks)},
    )
    return {"document_id": payload.document_id, "chunks": len(chunks)}


@app.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    principal: Principal = Depends(require_admin),
) -> dict[str, object]:
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
        existed = knowledge_base.has_document(document_id)
        chunks = knowledge_base.add_document(document_id, filename, sections)
    except (UnsupportedDocumentError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    agent.audit.record(
        "document.updated" if existed else "document.created",
        principal.name,
        "document",
        document_id,
        {"chunks": len(chunks), "filename": filename},
    )
    return {"document_id": document_id, "chunks": len(chunks)}


@app.delete("/documents/{document_id}")
def delete_document(
    document_id: DocumentId,
    principal: Annotated[Principal, Depends(require_admin)],
) -> dict[str, object]:
    if not knowledge_base.delete_document(document_id):
        raise HTTPException(status_code=404, detail="文档不存在。")
    agent.audit.record("document.deleted", principal.name, "document", document_id)
    return {"document_id": document_id, "deleted": True}


@app.post("/documents/{document_id}/reindex")
def reindex_document(
    document_id: DocumentId,
    principal: Annotated[Principal, Depends(require_admin)],
) -> dict[str, object]:
    chunks = knowledge_base.reindex_document(document_id)
    if chunks is None:
        raise HTTPException(status_code=404, detail="文档不存在。")
    agent.audit.record(
        "document.reindexed",
        principal.name,
        "document",
        document_id,
        {"chunks": len(chunks)},
    )
    return {"document_id": document_id, "chunks": len(chunks)}


@app.post("/query")
def query(
    payload: QueryRequest,
    principal: Annotated[Principal, Depends(require_reader)],
) -> dict[str, object]:
    answer = agent.rag.answer(payload.question)
    agent.audit.record(
        "query.completed",
        principal.name,
        "query",
        "-",
        {"abstained": answer.abstained, "citations": len(answer.citations)},
    )
    return answer.to_dict()


@app.post("/agent/run")
def run_agent(
    payload: AgentRequest,
    principal: Annotated[Principal, Depends(require_operator)],
) -> dict[str, object]:
    return agent.run(payload.message, actor=principal.name).to_dict()


@app.get("/approvals")
def list_approvals(
    principal: Annotated[Principal, Depends(require_operator)],
    approval_status: Annotated[
        str | None,
        Query(alias="status", pattern=r"^(pending|approved|rejected|expired)$"),
    ] = None,
) -> list[dict[str, object]]:
    del principal
    return [approval.to_dict() for approval in agent.approvals.list(approval_status)]


@app.post("/approvals/{approval_id}/approve")
def approve_action(
    approval_id: ApprovalId,
    principal: Annotated[Principal, Depends(require_operator)],
) -> dict[str, object]:
    try:
        return agent.approve(approval_id, principal.name).to_dict()
    except (ApprovalNotFoundError, ApprovalExpiredError, ApprovalConflictError) as exc:
        _raise_approval_http_error(exc)


@app.post("/approvals/{approval_id}/reject")
def reject_action(
    approval_id: ApprovalId,
    principal: Annotated[Principal, Depends(require_operator)],
) -> dict[str, object]:
    try:
        return agent.reject(approval_id, principal.name).to_dict()
    except (ApprovalNotFoundError, ApprovalExpiredError, ApprovalConflictError) as exc:
        _raise_approval_http_error(exc)


@app.get("/tickets")
def list_tickets(
    _principal: Annotated[Principal, Depends(require_reader)],
) -> list[dict[str, object]]:
    return [ticket.to_dict() for ticket in agent.tickets.list()]


@app.get("/audit-events")
def list_audit_events(
    _principal: Annotated[Principal, Depends(require_admin)],
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> list[dict[str, object]]:
    return [event.to_dict() for event in agent.audit.list(limit)]
