from __future__ import annotations

from pathlib import Path

from .agent import DocOpsAgent
from .config import Settings
from .generation import ExtractiveGenerator, OpenAICompatibleGenerator
from .models import ParsedSection
from .rag import RAGService
from .store import KnowledgeBase, TicketStore


def build_agent(settings: Settings | None = None) -> tuple[DocOpsAgent, KnowledgeBase]:
    settings = settings or Settings.from_env()
    knowledge_base = KnowledgeBase()
    demo_path = Path(__file__).resolve().parent.parent / "data" / "demo_manual.md"
    if demo_path.exists():
        knowledge_base.add_document(
            document_id="demo-handbook",
            title="星云科技员工服务手册（演示）",
            sections=[ParsedSection(text=demo_path.read_text(encoding="utf-8"), page=1)],
        )

    if settings.llm_provider == "openai-compatible":
        generator = OpenAICompatibleGenerator(
            settings.llm_base_url,
            settings.llm_api_key,
            settings.llm_model,
        )
    else:
        generator = ExtractiveGenerator()

    rag = RAGService(
        knowledge_base,
        generator=generator,
        top_k=settings.top_k,
        min_evidence_score=settings.min_evidence_score,
    )
    return DocOpsAgent(rag, TicketStore()), knowledge_base

