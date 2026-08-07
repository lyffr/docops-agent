# API Guide

The default base URL is `http://localhost:8000`. Production requests must use HTTPS through a
reverse proxy.

## Authentication

Pass the configured secret in every protected request:

```http
X-API-Key: your-secret
```

`/health`, `/health/live`, and `/health/ready` are intentionally unauthenticated for orchestrator
probes. All other endpoints require an API key when authentication is configured. Development mode
without configured keys grants an in-process development admin identity.

Every response includes `X-Request-ID`. Clients may submit their own `X-Request-ID` value for log
correlation.

## Endpoints

| Method | Path | Minimum role | Purpose |
| --- | --- | --- | --- |
| `GET` | `/health/live` | Public | Process liveness. |
| `GET` | `/health/ready` | Public | Database readiness and document count. |
| `GET` | `/me` | Reader | Current API identity and role. |
| `GET` | `/documents` | Reader | List indexed document metadata. |
| `POST` | `/documents/text` | Admin | Add or replace a text document. |
| `POST` | `/documents/upload` | Admin | Upload TXT, Markdown, CSV, or text PDF. |
| `DELETE` | `/documents/{id}` | Admin | Delete source sections and retrieval chunks. |
| `POST` | `/documents/{id}/reindex` | Admin | Rebuild chunks from persisted source sections. |
| `POST` | `/query` | Reader | Run knowledge retrieval and grounded generation. |
| `POST` | `/agent/run` | Operator | Run routing; ticket actions create pending approvals. |
| `GET` | `/approvals` | Operator | List approvals, optionally filtered by status. |
| `POST` | `/approvals/{id}/approve` | Operator | Atomically approve and create the ticket. |
| `POST` | `/approvals/{id}/reject` | Operator | Reject a pending action. |
| `GET` | `/tickets` | Reader | List created tickets. |
| `GET` | `/audit-events` | Admin | Read persisted audit events, newest first. |

## Knowledge query

```bash
curl --fail https://api.example.com/query \
  -H "X-API-Key: $DOCOPS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"question":"正式员工一年有几天年假？"}'
```

The response includes `content`, `citations`, `confidence`, and `abstained`. A low-evidence query
returns an explicit abstention with no citations.

## Server-side approval flow

Request an action:

```bash
curl --fail https://api.example.com/agent/run \
  -H "X-API-Key: $DOCOPS_OPERATOR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"message":"创建工单：电脑无法启动"}'
```

The response contains a persisted `approval.id` and `expires_at`. Resolve it with a separate call:

```bash
curl --fail -X POST \
  -H "X-API-Key: $DOCOPS_OPERATOR_KEY" \
  https://api.example.com/approvals/APR-XXXXXXXXXXXX/approve
```

Approval is single-use. Replaying the request returns `409 Conflict`; an expired approval returns
`410 Gone`. Approval and ticket creation commit in one database transaction.

## Common errors

| Status | Meaning |
| --- | --- |
| `400` | Invalid document or unsupported content. |
| `401` | Missing or invalid API key. |
| `403` | Authenticated identity lacks the required role. |
| `404` | Document or approval does not exist. |
| `409` | Approval has already been resolved. |
| `410` | Approval expired before resolution. |
| `413` | Document exceeds the configured size limit. |
| `422` | Request validation failed. |
| `503` | Persistent storage is unavailable. |
