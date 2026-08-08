# Security Model

DocOps Agent 0.3 is suitable for a small, single-host deployment when placed behind HTTPS and a
rate-limiting reverse proxy. This document distinguishes implemented controls from deployment
responsibilities and known limitations.

## Implemented controls

- Static API key authentication with constant-time secret comparison
- Reader, operator, and admin authorization roles
- Production startup failure when API keys are missing
- Minimum 24-character API key secrets
- Exact trusted-host validation; wildcard hosts are rejected in production
- Optional exact-origin CORS configuration
- Server-side, expiring, single-use approval records
- Atomic approval and ticket creation transaction
- Persistent audit events that never include API or model secrets
- Upload and direct-text size limits
- Filename path removal and constrained document IDs
- Prompt instructions that treat retrieved document content as untrusted data
- Non-root container user, read-only container filesystem, and `no-new-privileges`
- Optional shared Streamlit login password, separate from its server-side API key
- `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and no-store response headers
- Request IDs and structured JSON access logs

## Deployment responsibilities

- Terminate HTTPS before traffic reaches the API or Streamlit service.
- Store `.env`, SQLite backups, and model credentials with restricted filesystem permissions.
- Rotate API keys and model credentials on a regular schedule and immediately after suspected
  exposure.
- Add reverse-proxy or platform rate limiting. The application does not implement distributed rate
  limiting.
- Restrict outbound network access when using an external model endpoint.
- Back up and test restoration of the SQLite database.
- Monitor audit events and authentication failures.

## Known limitations

- API keys are static bearer secrets. There is no OIDC, SSO, user directory, or automatic rotation.
- SQLite data is not encrypted by the application. Use encrypted disks or migrate to an encrypted
  managed database.
- Uploaded files are parsed but not scanned for malware. Add an antivirus or content-disarm stage
  for untrusted public uploads.
- Text PDF parsing does not sandbox `pypdf` in a separate process.
- Prompt-injection instructions reduce risk but do not prove that model output is safe. The optional
  LLM generator still requires output validation for high-impact decisions.
- The Streamlit UI uses one server-side API key and one optional shared login password. It does not
  identify individual end users; use reverse-proxy OIDC/SSO when per-user identity is required.
- SQLite mode supports one API process. It is not a multi-replica consistency model.

## Secret rotation

`DOCOPS_API_KEYS` may contain old and new keys simultaneously. A safe rotation is:

1. Add the new credential and restart the API.
2. Update every client, including `DOCOPS_UI_API_KEY`, and restart the UI.
3. Verify `/me` with the new key.
4. Remove the old credential and restart the API.
5. Review audit and request logs for unexpected use of the old identity.

Never include secrets in URLs, document content, chat questions, Git commits, or support logs.
