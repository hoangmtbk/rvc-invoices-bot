---
title: Docker Host Migration Design
date: 2026-06-25
status: approved
---

# rvc-invoices-bot — Docker Host Migration Design

Move the entire `rvc-invoices-bot` stack from the current host to a new Docker host at `***REMOVED_IP***` using a maintenance window. All services and data must be preserved exactly.

## Context

- **Source host**: current machine (`/home/ai/rvc-invoices-bot/`)
- **Target host**: `***REMOVED_IP***`, user `rvc-user`, SSH key `~/.ssh/id_rsa`
- **Target project path**: `/home/rvc-user/rvc-invoices-bot/`
- **Docker**: v29.4.2 + Compose v5.1.3 already installed on target
- **Downtime**: maintenance window accepted; DNS + `docker compose down` already executed

## Stack

| Service | Image | Role |
|---------|-------|------|
| `rvc-traefik` | `traefik:v3.6.14` | Reverse proxy + TLS (Let's Encrypt HTTP challenge) |
| `rvc-invoices-bot` | built from `Dockerfile` | Email poller + invoice scraper (Playwright + Gemini) |
| `rvc-invoices-web` | built from `Dockerfile.web` | Flask web dashboard |
| `rvc-minio` | `minio/minio` | Object storage for PDFs + XMLs |

## Domains

| Domain | Service |
|--------|---------|
| `hddt.rvctel.vn` | web dashboard |
| `rvc-s3.rvctel.vn` | MinIO S3 API |
| `rvc-s3-console.rvctel.vn` | MinIO console UI |

DNS A records already updated to `***REMOVED_IP***`.

## Volumes to Migrate

| Volume | Contents | Priority |
|--------|----------|----------|
| `rvc-invoices-bot_invoices_data` | SQLite DB (`invoices.db`) | Critical |
| `rvc-invoices-bot_minio_data` | Invoice PDFs + XMLs | Critical |
| `rvc-invoices-bot_letsencrypt` | `acme.json` (TLS certs for all 3 domains) | Critical |
| `rvc-invoices-bot_invoices_logs` | Bot log files | Optional but included |

Migration method: **Docker tar pipe over SSH** — no root required, no intermediate files.

```bash
docker run --rm \
  -v <VOLUME_NAME>:/data \
  alpine tar czf - /data \
| ssh -i ~/.ssh/id_rsa rvc-user@***REMOVED_IP*** \
  "docker volume create <VOLUME_NAME> && \
   docker run --rm -i -v <VOLUME_NAME>:/data alpine tar xzf - -C /"
```

## Code Transfer

rsync project directory (excluding runtime dirs) before or during maintenance window:

```bash
rsync -avz \
  --exclude='.git' --exclude='__pycache__' \
  --exclude='data/' --exclude='logs/' --exclude='temp/' \
  -e "ssh -i ~/.ssh/id_rsa" \
  /home/ai/rvc-invoices-bot/ \
  rvc-user@***REMOVED_IP***:/home/rvc-user/rvc-invoices-bot/
```

The `.env` file (live credentials) is included in the rsync. No separate copy step needed.

## Build + Start on Target

```bash
ssh -i ~/.ssh/id_rsa rvc-user@***REMOVED_IP*** \
  "cd /home/rvc-user/rvc-invoices-bot && docker compose up --build -d"
```

Images are built on the target from the transferred Dockerfiles. No image export/import needed.

## Verification (Before DNS was cut — now verify post-cutover)

1. All 4 containers in `Up` state
2. Bot logs show clean startup (no DB/MinIO errors)
3. Web UI responds on internal port 8080
4. SQLite invoice count matches source
5. MinIO bucket `rvc-invoices` exists with objects
6. HTTPS endpoints respond correctly via domain

## Migration Phases

| # | Phase | Status |
|---|-------|--------|
| 0 | Pre-flight: verify SSH + disk space on target | pending |
| 1 | rsync code + .env to target | pending |
| 2 | Stop source containers (`docker compose down`) | **DONE** |
| 3 | Migrate 4 volumes via tar pipe over SSH | pending |
| 4 | Build images + start containers on target | pending |
| 5 | Verify all services on target | pending |
| 6 | DNS cutover (A records → ***REMOVED_IP***) | **DONE** |
| 7 | Monitor for 30 min; keep source volumes as backup | pending |

## Decommission

After target confirmed stable (≥30 min uptime, email polling verified):
- Source containers already stopped
- Source volumes retained as backup for ≥1 week
- Run `docker compose down -v` on source only after explicit confirmation
