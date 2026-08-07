# Operations Runbook

## Health and readiness

- `GET /health/live` confirms that the process can serve HTTP.
- `GET /health/ready` checks SQLite connectivity and reports the loaded document count.
- A live but unready service should be removed from traffic and investigated before restart loops are
  introduced.

Docker checks readiness every 30 seconds. Inspect state with:

```bash
docker compose ps
docker compose logs --tail=200 api
docker compose logs --tail=200 ui
```

## Structured logs

API request logs are JSON objects written to stdout. Important fields are:

- `timestamp`
- `level`
- `message`
- `request_id`
- `method`
- `path`
- `status_code`
- `duration_ms`

Responses return the same request ID in `X-Request-ID`. Search logs by that value when tracing a
failed client request. Compose rotates container logs at 10 MB and retains three files.

## Routine checks

Perform these checks regularly:

1. Confirm both containers are healthy.
2. Confirm `/health/ready` returns `ready`.
3. Review `401`, `403`, `409`, `410`, and `5xx` request counts.
4. Review `/audit-events` with an admin credential.
5. Monitor the named volume and backup storage capacity.
6. Create a SQLite backup and periodically restore it in a separate test environment.
7. Confirm pending approvals are not accumulating unexpectedly.

## Common incidents

### API returns 401

- Confirm the client sends `X-API-Key`, not an Authorization bearer token.
- Verify the raw key matches the secret portion of a configured `name:role:secret` entry.
- Restart the API after changing `.env`.

### API returns 403

The key is valid but its role is insufficient. Use reader for queries, operator for approvals, and
admin for document mutations and audit reads.

### Readiness returns 503

- Inspect API logs for SQLite errors.
- Verify the `/state` volume is mounted and writable by the non-root container user.
- Check disk capacity and filesystem health.
- Do not delete `docops.db-wal` or `docops.db-shm` while the API is running.

### Approval returns 409 or 410

- `409` means another request already approved or rejected the action.
- `410` means the approval exceeded `DOCOPS_APPROVAL_TTL_SECONDS`; create a new request.
- Never retry approval blindly after a network timeout. Check the approval and ticket lists first.

### Retrieval quality changes after deployment

- Run `python scripts/evaluate.py` against the committed dataset.
- Compare `DOCOPS_TOP_K` and `DOCOPS_MIN_EVIDENCE_SCORE` with the previous deployment.
- Reindex documents after changing chunking or tokenization code.
- Roll back code and restore the matching database backup if a schema migration is involved.

## Graceful restart

```bash
docker compose up -d --no-deps --force-recreate api
docker compose ps
curl --fail http://127.0.0.1:8000/health/ready
```

The API closes its SQLite connection during graceful shutdown. Keep the single-worker setting while
using SQLite.
