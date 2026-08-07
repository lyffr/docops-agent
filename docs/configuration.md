# Configuration Reference

DocOps Agent reads configuration from environment variables. Invalid values fail fast during API
startup. In production, `DOCOPS_API_KEYS` is mandatory and wildcard trusted hosts are rejected.

| Variable | Default | Description |
| --- | --- | --- |
| `DOCOPS_ENVIRONMENT` | `development` | `development`, `test`, or `production`. |
| `DOCOPS_DATABASE_PATH` | `data/docops.db` | SQLite database path. Compose overrides this with `/state/docops.db`. |
| `DOCOPS_API_KEYS` | empty | Comma-separated `name:role:secret` API credentials. Required in production. |
| `DOCOPS_APPROVAL_TTL_SECONDS` | `900` | Lifetime of a pending state-changing action. |
| `DOCOPS_TRUSTED_HOSTS` | local hosts | Accepted HTTP `Host` values. Wildcards are forbidden in production. |
| `DOCOPS_CORS_ORIGINS` | empty | Comma-separated exact browser origins. Empty disables CORS middleware. |
| `DOCOPS_DOCS_ENABLED` | `true` | Enables `/docs` and `/openapi.json`. Usually disabled in production. |
| `DOCOPS_LOG_LEVEL` | `INFO` | `CRITICAL`, `ERROR`, `WARNING`, `INFO`, or `DEBUG`. |
| `DOCOPS_MAX_UPLOAD_BYTES` | `10485760` | Maximum text or uploaded document size in bytes. |
| `DOCOPS_TOP_K` | `4` | Number of retrieval results passed to generation. |
| `DOCOPS_MIN_EVIDENCE_SCORE` | `0.08` | Abstention threshold from 0 through 1. |
| `DOCOPS_LLM_PROVIDER` | `extractive` | `extractive` or `openai-compatible`. |
| `DOCOPS_LLM_BASE_URL` | OpenAI API URL | Base URL for an OpenAI-compatible endpoint. |
| `DOCOPS_LLM_API_KEY` | empty | Model provider credential. Never logged by the application. |
| `DOCOPS_LLM_MODEL` | empty | Model name for the compatible endpoint. |
| `DOCOPS_API_URL` | `http://localhost:8000` | API URL used by Streamlit outside Compose. |
| `DOCOPS_API_KEY` | empty | API key used by Streamlit outside Compose. |
| `DOCOPS_UI_API_KEY` | empty | Compose value injected into Streamlit as `DOCOPS_API_KEY`. |
| `DOCOPS_UI_PASSWORD` | empty | Shared Streamlit login password; minimum 16 characters when set. |
| `DOCOPS_BIND_HOST` | `127.0.0.1` | Host interface used for published Compose ports. |
| `DOCOPS_API_PORT` | `8000` | Published API port. |
| `DOCOPS_UI_PORT` | `8501` | Published Streamlit port. |

## API key roles

Credentials use this syntax:

```dotenv
DOCOPS_API_KEYS=reports:reader:first-secret,helpdesk:operator:second-secret,admin:admin:third-secret
```

| Role | Permissions |
| --- | --- |
| `reader` | Health, identity, document metadata, queries, and ticket reads. |
| `operator` | Reader permissions plus agent execution and approval resolution. |
| `admin` | Operator permissions plus document mutation and audit-event reads. |

API key names may contain letters, digits, `_`, and `-`. Secrets must be at least 24 characters.
The secret itself may contain `:` but not `,` because commas separate credentials.

The Streamlit password is separate from the API key. Configure both in deployments that expose the
UI. For deployments with OIDC or SSO at the reverse proxy, the shared Streamlit password can be an
additional defense or the UI can remain private.

## OpenAI-compatible generation

Set all four model variables together:

```dotenv
DOCOPS_LLM_PROVIDER=openai-compatible
DOCOPS_LLM_BASE_URL=https://model.example.com/v1
DOCOPS_LLM_API_KEY=secret
DOCOPS_LLM_MODEL=model-name
```

The endpoint must implement `POST /chat/completions`. Model failures currently return a server
error; configure upstream timeouts and availability monitoring when enabling this provider.
