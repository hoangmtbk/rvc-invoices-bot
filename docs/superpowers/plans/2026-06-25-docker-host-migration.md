# Docker Host Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the entire `rvc-invoices-bot` Docker Compose stack from the current host to `***REMOVED_IP***` with full data integrity during an active maintenance window.

**Architecture:** rsync source code to target, then stream each Docker volume via tar pipe over SSH using an Alpine container (no root required, no intermediate files), then build images and start the stack on the target.

**Tech Stack:** Docker Compose v5.1.3, rsync, SSH key `~/.ssh/id_rsa`, Alpine (busybox tar), Python 3.11-slim, Playwright, MinIO, Traefik v3.

**Current state:** Source containers stopped (`docker compose down` already run). DNS A records for all 3 domains already pointing to `***REMOVED_IP***`. Maintenance window is active — move fast.

---

### Task 1: Pre-flight checks

**Files:** None — verification only.

- [ ] **Step 1: Confirm SSH access to target**

```bash
ssh -i ~/.ssh/id_rsa rvc-user@***REMOVED_IP*** "echo 'SSH OK' && docker version --format '{{.Server.Version}}'"
```

Expected output:
```
SSH OK
29.4.2
```

If SSH fails: check that `~/.ssh/id_rsa` exists and has correct permissions (`chmod 600 ~/.ssh/id_rsa`).

- [ ] **Step 2: Confirm Docker Compose on target**

```bash
ssh -i ~/.ssh/id_rsa rvc-user@***REMOVED_IP*** "docker compose version"
```

Expected:
```
Docker Compose version v2.x.x
```

- [ ] **Step 3: Confirm disk space on target (need ~1 GB for all volumes + images)**

```bash
ssh -i ~/.ssh/id_rsa rvc-user@***REMOVED_IP*** "df -h /"
```

Expected: At least 2 GB available. Target currently has 112 GB free — confirmed OK.

- [ ] **Step 4: Confirm source containers are stopped**

```bash
docker ps --filter name=rvc --format "table {{.Names}}\t{{.Status}}"
```

Expected: Empty output (all rvc containers stopped). If any are still running: `cd /home/ai/rvc-invoices-bot && docker compose down`.

- [ ] **Step 5: Confirm volumes still exist on source**

```bash
docker volume ls | grep rvc-invoices-bot
```

Expected — all 4 volumes present:
```
local     rvc-invoices-bot_invoices_data
local     rvc-invoices-bot_invoices_logs
local     rvc-invoices-bot_letsencrypt
local     rvc-invoices-bot_minio_data
```

---

### Task 2: Transfer code and .env to target

**Files:**
- Source: `/home/ai/rvc-invoices-bot/` (entire project)
- Target: `/home/rvc-user/rvc-invoices-bot/`

- [ ] **Step 1: Create project directory on target**

```bash
ssh -i ~/.ssh/id_rsa rvc-user@***REMOVED_IP*** "mkdir -p /home/rvc-user/rvc-invoices-bot"
```

- [ ] **Step 2: rsync project files to target**

```bash
rsync -avz \
  --exclude='.git' \
  --exclude='__pycache__' \
  --exclude='data/' \
  --exclude='logs/' \
  --exclude='temp/' \
  -e "ssh -i ~/.ssh/id_rsa" \
  /home/ai/rvc-invoices-bot/ \
  rvc-user@***REMOVED_IP***:/home/rvc-user/rvc-invoices-bot/
```

Expected: rsync output listing transferred files, ending with transfer rate summary. The `.env` file is included — no separate copy needed.

- [ ] **Step 3: Verify key files arrived on target**

```bash
ssh -i ~/.ssh/id_rsa rvc-user@***REMOVED_IP*** \
  "ls /home/rvc-user/rvc-invoices-bot/ && echo '---' && head -3 /home/rvc-user/rvc-invoices-bot/.env"
```

Expected: directory listing including `docker-compose.yml`, `Dockerfile`, `Dockerfile.web`, `.env`, `main.py`, `requirements.txt`, `requirements.web.txt`.

---

### Task 3: Migrate invoices_data volume (SQLite database)

**Files:** Docker volume `rvc-invoices-bot_invoices_data` → target host same name.

- [ ] **Step 1: Create volume on target and stream data via tar pipe**

```bash
docker run --rm \
  -v rvc-invoices-bot_invoices_data:/data \
  alpine tar czf - /data \
| ssh -i ~/.ssh/id_rsa rvc-user@***REMOVED_IP*** \
  "docker volume create rvc-invoices-bot_invoices_data && \
   docker run --rm -i -v rvc-invoices-bot_invoices_data:/data alpine tar xzf - -C /"
```

Expected: No output on success. Takes ~2 seconds (volume is ~16 KB).

- [ ] **Step 2: Verify SQLite DB arrived on target**

```bash
ssh -i ~/.ssh/id_rsa rvc-user@***REMOVED_IP*** \
  "docker run --rm -v rvc-invoices-bot_invoices_data:/data alpine ls -lh /data/"
```

Expected: `invoices.db` listed, size ~16K.

- [ ] **Step 3: Verify invoice count on target matches source**

Record source count first:
```bash
docker run --rm \
  -v rvc-invoices-bot_invoices_data:/data \
  python:3.11-slim \
  python -c "import sqlite3; c=sqlite3.connect('/data/invoices.db'); print('Source count:', c.execute('SELECT COUNT(*) FROM invoices').fetchone()[0])"
```

Then check target:
```bash
ssh -i ~/.ssh/id_rsa rvc-user@***REMOVED_IP*** \
  "docker run --rm -v rvc-invoices-bot_invoices_data:/data python:3.11-slim \
   python -c \"import sqlite3; c=sqlite3.connect('/data/invoices.db'); print('Target count:', c.execute('SELECT COUNT(*) FROM invoices').fetchone()[0])\""
```

Expected: Both counts identical.

---

### Task 4: Migrate invoices_logs volume

**Files:** Docker volume `rvc-invoices-bot_invoices_logs` → target host same name.

- [ ] **Step 1: Stream logs volume to target**

```bash
docker run --rm \
  -v rvc-invoices-bot_invoices_logs:/data \
  alpine tar czf - /data \
| ssh -i ~/.ssh/id_rsa rvc-user@***REMOVED_IP*** \
  "docker volume create rvc-invoices-bot_invoices_logs && \
   docker run --rm -i -v rvc-invoices-bot_invoices_logs:/data alpine tar xzf - -C /"
```

Expected: No output on success. Takes ~2 seconds (small volume).

- [ ] **Step 2: Verify logs arrived on target**

```bash
ssh -i ~/.ssh/id_rsa rvc-user@***REMOVED_IP*** \
  "docker run --rm -v rvc-invoices-bot_invoices_logs:/data alpine ls -lh /data/"
```

Expected: `bot.log` listed (may be empty or contain prior log lines).

---

### Task 5: Migrate minio_data volume (invoice PDFs + XMLs)

**Files:** Docker volume `rvc-invoices-bot_minio_data` → target host same name. Size: ~224 MB.

- [ ] **Step 1: Stream MinIO data volume to target (takes ~1–3 min)**

```bash
docker run --rm \
  -v rvc-invoices-bot_minio_data:/data \
  alpine tar czf - /data \
| ssh -i ~/.ssh/id_rsa rvc-user@***REMOVED_IP*** \
  "docker volume create rvc-invoices-bot_minio_data && \
   docker run --rm -i -v rvc-invoices-bot_minio_data:/data alpine tar xzf - -C /"
```

Expected: No output on success. Wait patiently — 224 MB compressed over LAN takes 1–3 minutes.

- [ ] **Step 2: Verify MinIO data size on target**

```bash
ssh -i ~/.ssh/id_rsa rvc-user@***REMOVED_IP*** \
  "docker run --rm -v rvc-invoices-bot_minio_data:/data alpine du -sh /data/"
```

Expected: Size close to `223.8M` (within a few KB difference due to compression).

---

### Task 6: Migrate letsencrypt volume (TLS certificates)

**Files:** Docker volume `rvc-invoices-bot_letsencrypt` → target host same name. Contains `acme.json` with valid TLS certs for all 3 domains.

- [ ] **Step 1: Stream letsencrypt volume to target**

```bash
docker run --rm \
  -v rvc-invoices-bot_letsencrypt:/data \
  alpine tar czf - /data \
| ssh -i ~/.ssh/id_rsa rvc-user@***REMOVED_IP*** \
  "docker volume create rvc-invoices-bot_letsencrypt && \
   docker run --rm -i -v rvc-invoices-bot_letsencrypt:/data alpine tar xzf - -C /"
```

Expected: No output on success. Takes ~1 second (tiny file).

- [ ] **Step 2: Verify acme.json exists on target and has correct permissions**

```bash
ssh -i ~/.ssh/id_rsa rvc-user@***REMOVED_IP*** \
  "docker run --rm -v rvc-invoices-bot_letsencrypt:/data alpine ls -lh /data/"
```

Expected: `acme.json` listed with size > 0 bytes.

> **Note:** Traefik requires `acme.json` to have permissions `600`. The file permissions are preserved inside the Docker volume — no manual chmod needed.

---

### Task 7: Build images and start the stack on target

**Files:** `/home/rvc-user/rvc-invoices-bot/docker-compose.yml` on target.

- [ ] **Step 1: Pull base images on target (speeds up build)**

```bash
ssh -i ~/.ssh/id_rsa rvc-user@***REMOVED_IP*** \
  "docker pull python:3.11-slim && docker pull traefik:v3.6.14 && docker pull minio/minio"
```

Expected: Pull progress bars, ending with "Status: Image is up to date" or "Downloaded newer image".

- [ ] **Step 2: Build and start the stack**

```bash
ssh -i ~/.ssh/id_rsa rvc-user@***REMOVED_IP*** \
  "cd /home/rvc-user/rvc-invoices-bot && docker compose up --build -d"
```

Expected output (order may vary):
```
[+] Building ...
...
[+] Running 4/4
 ✔ Container rvc-traefik         Started
 ✔ Container rvc-minio           Started
 ✔ Container rvc-invoices-bot    Started
 ✔ Container rvc-invoices-web    Started
```

Build takes ~3–5 minutes (Playwright + Chromium install is the slow step in `Dockerfile`).

- [ ] **Step 3: Confirm all 4 containers are running**

```bash
ssh -i ~/.ssh/id_rsa rvc-user@***REMOVED_IP*** \
  "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"
```

Expected — all 4 containers in `Up` state:
```
NAMES                STATUS          PORTS
rvc-traefik          Up X seconds    0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp
rvc-minio            Up X seconds    9000/tcp
rvc-invoices-bot     Up X seconds
rvc-invoices-web     Up X seconds
```

If any container is in `Restarting` or `Exited` state: `docker logs <container-name>` to diagnose.

---

### Task 8: Verify all services

**Files:** None — verification only.

- [ ] **Step 1: Check bot startup logs (no errors)**

```bash
ssh -i ~/.ssh/id_rsa rvc-user@***REMOVED_IP*** \
  "docker logs rvc-invoices-bot --tail 40"
```

Expected: Lines like `[INFO] Starting email poller`, `[INFO] Connected to MinIO`, `[INFO] DB ready`. No tracebacks or `ERROR` lines.

- [ ] **Step 2: Check web UI responds internally**

```bash
ssh -i ~/.ssh/id_rsa rvc-user@***REMOVED_IP*** \
  "docker exec rvc-invoices-web curl -s -o /dev/null -w '%{http_code}' http://localhost:8080"
```

Expected: `200` or `302` (redirect to login).

- [ ] **Step 3: Verify SQLite invoice count on running container**

```bash
ssh -i ~/.ssh/id_rsa rvc-user@***REMOVED_IP*** \
  "docker exec rvc-invoices-bot python -c \
   \"import sqlite3; c=sqlite3.connect('/app/data/invoices.db'); \
   print('Invoices in DB:', c.execute('SELECT COUNT(*) FROM invoices').fetchone()[0])\""
```

Expected: Same count as source (recorded in Task 3 Step 3).

- [ ] **Step 4: Verify MinIO bucket exists and has objects**

```bash
ssh -i ~/.ssh/id_rsa rvc-user@***REMOVED_IP*** \
  "docker exec rvc-minio mc alias set local http://localhost:9000 myminio '***REMOVED***' 2>/dev/null && \
   docker exec rvc-minio mc ls local/rvc-invoices --summarize 2>/dev/null | tail -5"
```

Expected: Object listing with file count and total size close to 224 MB.

- [ ] **Step 5: Verify HTTPS via domain (DNS already pointing to new host)**

```bash
curl -I https://hddt.rvctel.vn
```

Expected:
```
HTTP/2 200
...
```

No certificate errors. If you get a cert error: wait 30–60 seconds for Traefik to load the `acme.json` (it reads on startup).

- [ ] **Step 6: Verify MinIO HTTPS endpoint**

```bash
curl -I https://rvc-s3.rvctel.vn
```

Expected: `HTTP/2 200` or `403` (MinIO health check — both mean TLS is working).

- [ ] **Step 7: Verify MinIO console**

```bash
curl -I https://rvc-s3-console.rvctel.vn
```

Expected: `HTTP/2 200`.

---

### Task 9: Monitor and finalize

**Files:** None — monitoring and cleanup.

- [ ] **Step 1: Watch bot logs for one full email poll cycle (15 min)**

```bash
ssh -i ~/.ssh/id_rsa rvc-user@***REMOVED_IP*** \
  "docker logs rvc-invoices-bot -f --since 5m"
```

Wait for a log line like `[INFO] Polling mailbox...` or `[INFO] No new emails`. This confirms IMAP connection is live. Press Ctrl+C when satisfied.

- [ ] **Step 2: Send a test Telegram message to confirm notifications work**

Check the Telegram bot received any message (startup notification or first poll report). If you don't see a message within 15 minutes, check:

```bash
ssh -i ~/.ssh/id_rsa rvc-user@***REMOVED_IP*** \
  "docker logs rvc-invoices-bot 2>&1 | grep -i telegram"
```

Expected: `[INFO] Telegram notification sent` or similar.

- [ ] **Step 3: Keep source volumes intact as backup (do NOT run this yet)**

Source containers are already stopped. Source volumes remain on the current host as a safety net. Leave them for at least 1 week. Only clean up volumes after explicit confirmation that the target is fully stable:

```bash
# Run ONLY after 1 week of confirmed stable operation on target
# cd /home/ai/rvc-invoices-bot && docker compose down -v
```

- [ ] **Step 4: Confirm migration complete**

Final checklist:
- [ ] All 4 containers running on `***REMOVED_IP***`
- [ ] Invoice count in DB matches source
- [ ] MinIO objects intact (~224 MB)
- [ ] `https://hddt.rvctel.vn` loads correctly with valid TLS
- [ ] `https://rvc-s3.rvctel.vn` responds with valid TLS
- [ ] `https://rvc-s3-console.rvctel.vn` responds with valid TLS
- [ ] Bot successfully polled email at least once
- [ ] Telegram notification received
