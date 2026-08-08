# Deployment Guide

This guide deploys DocOps Agent 0.3 on one Linux host with Docker Compose. The API uses
SQLite and intentionally runs as a single worker. Use a PostgreSQL repository before running
multiple API replicas.

## Prerequisites

- Docker Engine 24 or newer
- Docker Compose 2.24 or newer
- A Linux host with persistent disk space
- Two DNS names when exposing both API and Streamlit, for example `api.example.com` and
  `docops.example.com`
- A TLS reverse proxy such as Nginx, Caddy, Traefik, or a managed load balancer

## 1. Create production configuration

Copy the production template:

```bash
cp .env.production.example .env
```

Generate an API key secret:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Put the generated value in both places below. The Streamlit key must match one entry in the API
credential list.

```dotenv
DOCOPS_API_KEYS=ui:admin:generated-secret
DOCOPS_UI_API_KEY=generated-secret
```

Generate a different secret for the shared Streamlit login:

```dotenv
DOCOPS_UI_PASSWORD=different-generated-secret
```

Update these values for the deployment:

```dotenv
DOCOPS_TRUSTED_HOSTS=api.example.com,localhost,127.0.0.1,api
DOCOPS_CORS_ORIGINS=https://docops.example.com
DOCOPS_DOCS_ENABLED=false
```

Never commit `.env`. API key entries use `name:role:secret` and are separated by commas. Secrets
must contain at least 24 characters.

## 2. Validate and start

```bash
docker compose config --quiet
docker compose build --pull
docker compose up -d
docker compose ps
```

The default bind address is `127.0.0.1`, so the services are not exposed directly to the public
network. Verify both probes locally:

```bash
curl --fail http://127.0.0.1:8000/health/live
curl --fail http://127.0.0.1:8000/health/ready
```

Verify authentication:

```bash
curl --fail \
  -H "X-API-Key: generated-secret" \
  http://127.0.0.1:8000/me
```

## 3. Configure TLS

Terminate TLS in a reverse proxy and keep the Compose ports bound to localhost. An Nginx example
is provided at [`deploy/nginx.conf.example`](../deploy/nginx.conf.example). Replace the hostnames
and certificate paths before enabling it.

Do not set `DOCOPS_BIND_HOST=0.0.0.0` on an internet-facing machine unless a firewall or private
network prevents direct access. API keys do not protect traffic confidentiality; HTTPS is required.

## 4. Data persistence

Compose stores `/state/docops.db` in the `docops-state` named volume. The database contains source
document text, approval records, tickets, and audit events. Retrieval chunks are rebuilt from source
sections during startup.

Create an online-consistent SQLite backup inside the volume:

```bash
mkdir -p backups
docker compose exec -T api python -c \
  "import sqlite3; src=sqlite3.connect('/state/docops.db'); dst=sqlite3.connect('/state/backup.db'); src.backup(dst); dst.close(); src.close()"
docker compose cp api:/state/backup.db ./backups/docops-$(date +%Y%m%d-%H%M%S).db
```

Store backups encrypted and outside the deployment host. Test restoration regularly.

To restore, stop the services, preserve the current database, copy the selected backup to
`/state/docops.db`, and then start the services. Do not restore while the API is running.

## 5. Upgrade and rollback

Before every upgrade:

1. Create and verify a database backup.
2. Record the currently deployed image or Git commit.
3. Run the test and configuration checks.
4. Rebuild and recreate the services.

```bash
docker compose build --pull
docker compose up -d --remove-orphans
docker compose ps
```

Database migrations run automatically at API startup. The application refuses to open a database
whose schema is newer than the code supports. Rolling back across a schema migration therefore
requires restoring the matching pre-upgrade database backup.

The container installs exact runtime versions from `requirements.lock`; CI uses
`requirements-dev.lock`. Regenerate and test these files intentionally when upgrading dependencies;
do not silently replace them during deployment.

## 6. Deployment constraints

- Run exactly one API worker and one API container while using SQLite.
- The Streamlit UI is optional; API-only deployment is supported with `docker compose up -d api`.
- Configure a reverse-proxy request rate limit for internet-facing deployments.
- Use PostgreSQL and an external object store before horizontal scaling or multi-host deployment.
- Use a managed secret store instead of plain environment files when the platform supports it.
- Prefer OIDC/SSO in the reverse proxy for public UI access; the built-in Streamlit password is a
  shared credential rather than an individual user identity.

See [Configuration](configuration.md), [Security](security.md), and the
[Operations Runbook](operations.md) before exposing the service to users.
