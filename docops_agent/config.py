from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    llm_provider: str = "extractive"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = ""
    top_k: int = 4
    min_evidence_score: float = 0.08

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            llm_provider=os.getenv("DOCOPS_LLM_PROVIDER", "extractive").lower(),
            llm_base_url=os.getenv("DOCOPS_LLM_BASE_URL", "https://api.openai.com/v1"),
            llm_api_key=os.getenv("DOCOPS_LLM_API_KEY", ""),
            llm_model=os.getenv("DOCOPS_LLM_MODEL", ""),
            top_k=int(os.getenv("DOCOPS_TOP_K", "4")),
            min_evidence_score=float(os.getenv("DOCOPS_MIN_EVIDENCE_SCORE", "0.08")),
        )
