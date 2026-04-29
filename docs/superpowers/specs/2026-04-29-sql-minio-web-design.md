# rvc-invoices-bot — SQL + MinIO + Web UI Design Specification
**Date:** 2026-04-29
**Project:** Vietnamese E-Invoice Bot — Storage & Interface Upgrade
**Status:** Approved

---

## 1. Overview

Upgrade the existing rvc-invoices-bot from CSV file storage to SQLite, add MinIO object storage for raw PDF/XML files, extend the invoice schema with 4 new fields, and introduce a lightweight Flask web UI for browsing and exporting invoices. A Traefik reverse proxy with Let's Encrypt SSL is added to docker-compose.

---

## 2. Schema & Service Architecture

### Updated `INVOICE_COLUMNS` (22 columns)

```python
INVOICE_COLUMNS = [
    "invoice_type", "invoice_symbol", "invoice_number",
    "issue_date", "seller_name", "seller_tax_code",
    "buyer_name", "buyer_tax_code",
    "contract_number",        # hợp đồng số
    "customer_code",          # mã khách hàng / mã thuê bao (Viettel)
    "description", "total_before_tax",
    "vat_rate", "total_vat_amount", "total_after_tax",
    "lookup_code", "lookup_website",
    "pdf_file_link",          # MinIO HTTPS URL to PDF file
    "xml_file_link",          # MinIO HTTPS URL to XML file
    "source_branch", "source_email_subject", "processed_date",
]
```

### Docker services

| Service | Image | Purpose |
|---|---|---|
| `rvc-invoices-bot` | existing Python image | IMAP watcher + invoice processor |
| `rvc-invoices-web` | new Python image (`Dockerfile.web`) | Flask read-only web UI + CSV export |
| `rvc-minio` | `minio/minio` | Object storage for PDF/XML files |
| `traefik` | `traefik:v3.0` | Reverse proxy + Let's Encrypt SSL |

**Shared state:** `rvc-invoices-bot` and `rvc-invoices-web` both mount the `invoices_data` Docker named volume which holds `invoices.db` (SQLite). SQLite WAL mode enables concurrent reads (web) + writes (bot).

---

## 3. SQLite Storage Migration

### Clean start

`data/Tong_hop_hoa_don.csv` and `data/errors.csv` are deleted. No migration. `invoices.db` is created fresh on first run.

### Database: `data/invoices.db`

**`invoices` table** — 22 columns matching `INVOICE_COLUMNS`. Primary key: `(invoice_number, seller_tax_code)`. Duplicate check via `INSERT OR IGNORE`.

**`errors` table** — 6 columns matching `ERROR_COLUMNS`. No primary key.

Every connection opens with `PRAGMA journal_mode=WAL`.

### `storage.py` public API (unchanged)

- `append_invoice(data: dict) -> None`
- `append_error(data: dict) -> None`
- `update_file_link(invoice_number: str, seller_tax_code: str, pdf_link: str | None, xml_link: str | None) -> None` ← new

### `reporter.py`

Updated to query SQLite via `pandas.read_sql` instead of reading CSV. Report logic unchanged.

### `config.py` changes

Remove: `INVOICE_CSV`, `ERROR_CSV`
Add: `DB_PATH = os.path.join(DATA_DIR, "invoices.db")`

---

## 4. File Storage (`file_storage.py`)

New module wrapping the MinIO Python client.

### MinIO setup

- Bucket: `rvc-invoices` (auto-created on first bot startup)
- Bucket policy: public read — permanent URLs, no expiry
- URL format: `https://rvc-s3.rvctel.vn/rvc-invoices/<filename>`

### File naming convention

```
{seller_tax_code}_{invoice_number}_{YYYYMMDD}.pdf
{seller_tax_code}_{invoice_number}_{YYYYMMDD}.xml
```

Example: `0310674520_000123_20260429.pdf`

### Public API

```python
def upload_file(file_bytes: bytes, filename: str, content_type: str) -> str:
    """Upload bytes to MinIO, return public HTTPS URL."""

def build_filename(seller_tax_code: str, invoice_number: str, date_str: str, ext: str) -> str:
    """Construct canonical filename."""
```

### Attachment processing in `router.py`

One email may contain multiple PDF+XML pairs (including inside ZIP archives). Processing steps per email:

1. **Dump to temp** — save every attachment to `temp/<uid>/`, extract every `.zip` recursively, delete ZIP files after extraction.
2. **Discover files** — collect all `.xml`, `.pdf`, `.html` files in `temp/<uid>/`.
3. **Pair by stem** — group by filename stem (`HD001.xml` + `HD001.pdf` = one pair). Unpaired files are their own single-file pair.
4. **Process each pair** independently:
   - XML present → parse XML for invoice data, upload XML → `xml_file_link`
   - PDF in same pair → upload PDF → `pdf_file_link`
   - Only one file present → other link stored as `""` (updatable later via `storage.update_file_link`)
   - Each pair → one `storage.append_invoice()` call
5. **Cleanup** — delete `temp/<uid>/` in `finally` block.

HTML and WEB branches (no file attachments) — unchanged from current logic, produce single invoice record.

---

## 5. New Field Extraction

### XML / ZIP branch (`data_extractor.parse_xml`)

New tag mappings added to the XML parser:

| Schema field | XML tags to search |
|---|---|
| `contract_number` | `SoHopDong`, `SHD`, `Số hợp đồng`, `contractNumber` |
| `customer_code` | `MaKhachHang`, `MaKH`, `MaThueBao`, `subscriberNumber` |

Returns `""` if tag not found.

### PDF branch (Gemini prompt extension)

```
"contract_number": "Số hợp đồng / contract number, null if not found",
"customer_code": "Mã khách hàng / mã thuê bao (Viettel subscriber number), null if not found",
```

### WEB / HTML branches

Use the same XML parser or Gemini call as above — no extra logic needed.

### `pdf_file_link` / `xml_file_link`

Set by `router.py` after MinIO upload. `data_extractor` never touches these.

---

## 6. Web UI (`web_app.py`)

Minimal Flask app — read-only, no authentication (internal network).

### Routes

| Route | Description |
|---|---|
| `GET /` | Invoice table with filters and column toggles |
| `GET /export` | Download CSV |

### Invoice table (`/`)

**Filters:**
- Date range (`from_date` / `to_date`) — filters on `issue_date`
- Type dropdown — All / PURCHASE / SALE
- Free-text search — against `seller_name`, `buyer_name`, `invoice_number`

**Column visibility:** Checkbox panel above the table lists all 22 column names. Default: all checked. Toggle via minimal vanilla JS (show/hide columns by index — no framework).

**File links:** `pdf_file_link` and `xml_file_link` rendered as `<a href="..." target="_blank">PDF</a>` / `<a href="..." target="_blank">XML</a>`. Empty cell if link is blank.

**Pagination:** 50 rows per page.

### CSV export (`/export`)

- Accepts same filter query params as `/`
- Optional `?columns=col1,col2,...` — default: all 22 columns
- `pdf_file_link` / `xml_file_link` in CSV are raw HTTPS URLs (clickable in Excel / Google Sheets)
- Response header: `Content-Disposition: attachment; filename=hoa_don_YYYYMMDD.csv`

### Styling

Tailwind CSS via CDN (`<script src="https://cdn.tailwindcss.com">`). No build step. Striped rows, hover highlight, sticky header.

### New files

- `web_app.py` — Flask application
- `templates/index.html` — Tailwind CSS + vanilla JS column toggles
- `Dockerfile.web` — `python:3.11-slim`, installs `flask`, `pandas`, `python-dotenv`

---

## 7. Docker & Configuration

### `docker-compose.yml`

```yaml
services:
  traefik:
    image: traefik:v3.0
    container_name: rvc-traefik
    restart: always
    command:
      - --providers.docker=true
      - --providers.docker.exposedbydefault=false
      - --entrypoints.web.address=:80
      - --entrypoints.websecure.address=:443
      - --certificatesresolvers.letsencrypt.acme.httpchallenge=true
      - --certificatesresolvers.letsencrypt.acme.httpchallenge.entrypoint=web
      - --certificatesresolvers.letsencrypt.acme.email=${ACME_EMAIL}
      - --certificatesresolvers.letsencrypt.acme.storage=/letsencrypt/acme.json
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - letsencrypt:/letsencrypt
    networks:
      - proxy

  rvc-invoices-bot:
    build: .
    container_name: rvc-invoices-bot
    restart: always
    env_file: .env
    volumes:
      - invoices_data:/app/data
      - invoices_logs:/app/logs
    depends_on:
      - rvc-minio
    networks:
      - proxy

  rvc-invoices-web:
    build:
      context: .
      dockerfile: Dockerfile.web
    container_name: rvc-invoices-web
    restart: always
    env_file: .env
    volumes:
      - invoices_data:/app/data
    depends_on:
      - rvc-invoices-bot
    networks:
      - proxy
    labels:
      - traefik.enable=true
      - traefik.http.routers.web.rule=Host(`${DOMAIN_WEB}`)
      - traefik.http.routers.web.entrypoints=websecure
      - traefik.http.routers.web.tls.certresolver=letsencrypt
      - traefik.http.routers.web-redirect.rule=Host(`${DOMAIN_WEB}`)
      - traefik.http.routers.web-redirect.entrypoints=web
      - traefik.http.routers.web-redirect.middlewares=redirect-to-https
      - traefik.http.middlewares.redirect-to-https.redirectscheme.scheme=https
      - traefik.http.services.web.loadbalancer.server.port=8080

  rvc-minio:
    image: minio/minio
    container_name: rvc-minio
    restart: always
    command: server /data --console-address ":9001"
    env_file: .env
    volumes:
      - minio_data:/data
    networks:
      - proxy
    labels:
      - traefik.enable=true
      - traefik.http.routers.minio.rule=Host(`${DOMAIN_MINIO}`)
      - traefik.http.routers.minio.entrypoints=websecure
      - traefik.http.routers.minio.tls.certresolver=letsencrypt
      - traefik.http.services.minio.loadbalancer.server.port=9000
      - traefik.http.routers.minio-console.rule=Host(`${DOMAIN_MINIO_CONSOLE}`)
      - traefik.http.routers.minio-console.entrypoints=websecure
      - traefik.http.routers.minio-console.tls.certresolver=letsencrypt
      - traefik.http.services.minio-console.loadbalancer.server.port=9001

volumes:
  invoices_data:
  invoices_logs:
  minio_data:
  letsencrypt:

networks:
  proxy:
    external: false
```

### `.env` additions

```env
# MinIO
MINIO_ENDPOINT=rvc-minio:9000
MINIO_ACCESS_KEY=your_access_key
MINIO_SECRET_KEY=your_secret_key
MINIO_ROOT_USER=your_access_key          # same value as MINIO_ACCESS_KEY
MINIO_ROOT_PASSWORD=your_secret_key      # same value as MINIO_SECRET_KEY
MINIO_BUCKET=rvc-invoices
MINIO_PUBLIC_URL=https://rvc-s3.rvctel.vn

# Web UI
WEB_PORT=8080

# Traefik
ACME_EMAIL=admin@rvctel.vn
DOMAIN_WEB=hddt.rvctel.vn
DOMAIN_MINIO=rvc-s3.rvctel.vn
DOMAIN_MINIO_CONSOLE=rvc-s3-console.rvctel.vn
```

MinIO container reads `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` — set these to the same values as `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` in `.env`.

**Note:** Ports 80 and 443 must be open on the Docker host. All three domains must resolve to the host's public IP for Let's Encrypt HTTP challenge to work.

### `requirements.txt` additions

- `minio>=7.2.0`
- `flask>=3.0.0` (installed in `Dockerfile.web` only)

---

## 8. File Changes Summary

| File | Action |
|---|---|
| `storage.py` | Rewrite — SQLite replaces CSV, same public API + new `update_file_link` |
| `config.py` | Remove CSV paths, add DB_PATH + MinIO + web constants |
| `router.py` | Rewrite attachment loop — multi-pair processing, MinIO uploads |
| `data_extractor.py` | Add `contract_number` / `customer_code` extraction (XML tags + Gemini prompt) |
| `reporter.py` | Update to read from SQLite via `pandas.read_sql` |
| `requirements.txt` | Add `minio>=7.2.0`, `flask>=3.0.0` |
| `docker-compose.yml` | Add `rvc-invoices-web`, `rvc-minio`, `traefik` services |
| `file_storage.py` | New — MinIO upload wrapper |
| `web_app.py` | New — Flask web UI |
| `templates/index.html` | New — Tailwind CSS invoice table |
| `Dockerfile.web` | New — web container image |
| `.env.example` | Update with new variables |
| `data/Tong_hop_hoa_don.csv` | Delete |
| `data/errors.csv` | Delete |

---

## 9. Testing Notes

- `test_storage.py` — rewrite for SQLite: test `append_invoice`, `append_error`, `update_file_link`, duplicate suppression via `INSERT OR IGNORE`
- `test_router.py` — add tests for multi-pair attachment processing; mock `file_storage.upload_file`
- `test_data_extractor.py` — add tests for `contract_number` / `customer_code` extraction from XML and Gemini response
- `test_file_storage.py` — new: mock MinIO client, test `upload_file` and `build_filename`
- `test_web_app.py` — new: Flask test client, test table route, CSV export, column filter params
