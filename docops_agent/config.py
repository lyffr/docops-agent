from __future__ import annotations

import os
from dataclasses import dataclass

SUPPORTED_LLM_PROVIDERS = frozenset({"extractive", "openai-compatible"})


@dataclass(frozen=True, slots=True)
class Settings:
    llm_provider: str = "extractive"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = ""
    top_k: int = 4
    min_evidence_score: float = 0.08
    max_upload_bytes: int = 10 * 1024 * 1024

    def __post_init__(self) -> None:
        provider = self.llm_provider.strip().lower()
        object.__setattr__(self, "llm_provider", provider)
        if provider not in SUPPORTED_LLM_PROVIDERS:
            supported = ", ".join(sorted(SUPPORTED_LLM_PROVIDERS))
            raise ValueError(f"DOCOPS_LLM_PROVIDER must be one of: {supported}")
        if self.top_k <= 0:
            raise ValueError("DOCOPS_TOP_K must be greater than zero")
        if not 0 <= self.min_evidence_score <= 1:
            raise ValueError("DOCOPS_MIN_EVIDENCE_SCORE must be between 0 and 1")
        if self.max_upload_bytes <= 0:
            raise ValueError("DOCOPS_MAX_UPLOAD_BYTES must be greater than zero")

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            llm_provider=os.getenv("DOCOPS_LLM_PROVIDER", "extractive"),
            llm_base_url=os.getenv("DOCOPS_LLM_BASE_URL", "https://api.openai.com/v1"),
            llm_api_key=os.getenv("DOCOPS_LLM_API_KEY", ""),
            llm_model=os.getenv("DOCOPS_LLM_MODEL", ""),
            top_k=int(os.getenv("DOCOPS_TOP_K", "4")),
            min_evidence_score=float(os.getenv("DOCOPS_MIN_EVIDENCE_SCORE", "0.08")),
            max_upload_bytes=int(os.getenv("DOCOPS_MAX_UPLOAD_BYTES", str(10 * 1024 * 1024))),
        )
