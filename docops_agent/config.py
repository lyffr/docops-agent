from __future__ import annotations

import os
from dataclasses import dataclass, field

SUPPORTED_LLM_PROVIDERS = frozenset({"extractive", "openai-compatible"})
SUPPORTED_ENVIRONMENTS = frozenset({"development", "production", "test"})
SUPPORTED_LOG_LEVELS = frozenset({"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"})


def _split_csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _environment_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false")


@dataclass(frozen=True, slots=True)
class Settings:
    environment: str = "development"
    llm_provider: str = "extractive"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = field(default="", repr=False)
    llm_model: str = ""
    top_k: int = 4
    min_evidence_score: float = 0.08
    max_upload_bytes: int = 10 * 1024 * 1024
    database_path: str = "data/docops.db"
    approval_ttl_seconds: int = 900
    api_keys: str = field(default="", repr=False)
    cors_origins: tuple[str, ...] = ()
    trusted_hosts: tuple[str, ...] = ("localhost", "127.0.0.1", "testserver")
    log_level: str = "INFO"
    docs_enabled: bool = True

    def __post_init__(self) -> None:
        environment = self.environment.strip().lower()
        object.__setattr__(self, "environment", environment)
        if environment not in SUPPORTED_ENVIRONMENTS:
            supported = ", ".join(sorted(SUPPORTED_ENVIRONMENTS))
            raise ValueError(f"DOCOPS_ENVIRONMENT must be one of: {supported}")
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
        database_path = self.database_path.strip()
        if not database_path:
            raise ValueError("DOCOPS_DATABASE_PATH cannot be empty")
        object.__setattr__(self, "database_path", database_path)
        if self.approval_ttl_seconds <= 0:
            raise ValueError("DOCOPS_APPROVAL_TTL_SECONDS must be greater than zero")
        cors_origins = tuple(origin.strip() for origin in self.cors_origins if origin.strip())
        object.__setattr__(self, "cors_origins", cors_origins)
        trusted_hosts = tuple(host.strip() for host in self.trusted_hosts if host.strip())
        if not trusted_hosts:
            raise ValueError("DOCOPS_TRUSTED_HOSTS cannot be empty")
        if environment == "production" and "*" in trusted_hosts:
            raise ValueError("DOCOPS_TRUSTED_HOSTS cannot contain * in production")
        object.__setattr__(self, "trusted_hosts", trusted_hosts)
        log_level = self.log_level.strip().upper()
        if log_level not in SUPPORTED_LOG_LEVELS:
            raise ValueError("DOCOPS_LOG_LEVEL is invalid")
        object.__setattr__(self, "log_level", log_level)

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            environment=os.getenv("DOCOPS_ENVIRONMENT", "development"),
            llm_provider=os.getenv("DOCOPS_LLM_PROVIDER", "extractive"),
            llm_base_url=os.getenv("DOCOPS_LLM_BASE_URL", "https://api.openai.com/v1"),
            llm_api_key=os.getenv("DOCOPS_LLM_API_KEY", ""),
            llm_model=os.getenv("DOCOPS_LLM_MODEL", ""),
            top_k=int(os.getenv("DOCOPS_TOP_K", "4")),
            min_evidence_score=float(os.getenv("DOCOPS_MIN_EVIDENCE_SCORE", "0.08")),
            max_upload_bytes=int(os.getenv("DOCOPS_MAX_UPLOAD_BYTES", str(10 * 1024 * 1024))),
            database_path=os.getenv("DOCOPS_DATABASE_PATH", "data/docops.db"),
            approval_ttl_seconds=int(os.getenv("DOCOPS_APPROVAL_TTL_SECONDS", "900")),
            api_keys=os.getenv("DOCOPS_API_KEYS", ""),
            cors_origins=_split_csv(os.getenv("DOCOPS_CORS_ORIGINS", "")),
            trusted_hosts=_split_csv(
                os.getenv("DOCOPS_TRUSTED_HOSTS", "localhost,127.0.0.1,testserver")
            ),
            log_level=os.getenv("DOCOPS_LOG_LEVEL", "INFO"),
            docs_enabled=_environment_bool("DOCOPS_DOCS_ENABLED", True),
        )
