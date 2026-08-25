# vision-service

A **carton & pallet counting vision microservice** built with **YOLO11 (Ultralytics) + OpenCV**. It consumes an **RTSP stream** or a **video file**, counts **unique** cartons and pallets using object *tracking*, reports the running counts to the [`inventory-service`](../inventory-service) via its REST API (`restock` / `consume`), and **persists every detection event to Postgres** for durability and audit.

### Data flow

```
 Camera (RTSP/file)
        │  frames
        ▼
 ┌──────────────┐   track ids   ┌───────────────┐  per-category delta
 │  OpenCV      │ ────────────▶ │  YOLO11       │ ───────────────┐
 │  capture     │               │  model.track  │                │
 └──────────────┘               └───────────────┘                ▼
                                                    ┌──────────────────────────┐
                                                    │ InventoryClient (httpx)  │
                                                    │  restock / consume       │
                                                    └─────────────┬────────────┘
                                                                  │ REST
                                 ┌────────────────────────────────┴───┐
                                 ▼                                    ▼
                  ┌──────────────────────────┐         ┌──────────────────────────┐
                  │ inventory-service        │         │ vision-service Postgres  │
                  │  -> its own Postgres     │         │  detection_jobs          │
                  │     (inventory_items)    │         │  detection_events (audit)│
                  └──────────────────────────┘         └──────────────────────────┘
```

The **final hop is Postgres** in two places: inventory-service stores the updated stock levels, and vision-service stores a durable audit trail of every report it pushed.

---

## Functions

| Function | Implementation |
|----------|----------------|
| **Read RTSP camera** | `core/source.py` — OpenCV `VideoCapture` with FFMPEG backend + `BUFFERSIZE=1` for low latency; also handles local video files |
| **Run YOLO11** | `core/detector.py` — `ObjectDetector` wraps `ultralytics.YOLO`, runs `model.track(persist=True, tracker=bytetrack.yaml)` |
| **Count carton / pallet** | `services/pipeline.py` — multi-category counting: maps YOLO class names to logical targets (`carton`, `pallet`) and counts **unique track IDs** per category (each physical object counted once) |
| **Call API to update inventory** | `clients/inventory_client.py` — sync `httpx` client calling `POST /inventory-items/{id}/restock` or `/consume` with per-category deltas |
| **Persist to Postgres** | `infrastructure/` — `detection_jobs` (durable job state) + `detection_events` (audit log of every report) |

---

## Why tracking instead of per-frame detection?

Counting in every frame would multiply-count the **same** box as it moves through the scene. The service uses `model.track(persist=True)` (ByteTrack) which assigns each object a stable **track ID**. The pipeline only increments a category's counter when a *new* track ID whose class matches that category appears — so each physical carton/pallet is counted exactly once.

---

## Multi-category counting (carton + pallet)

A job declares one or more **counting targets**. Each target maps a set of YOLO class names to an inventory item and a report mode:

```json
{
  "source": "rtsp://admin:pass@10.0.0.5:554/stream",
  "targets": [
    {
      "name": "carton",
      "class_names": ["carton", "box"],
      "target_sku": "CARTON-001",
      "report_mode": "restock"
    },
    {
      "name": "pallet",
      "class_names": ["pallet", "wooden pallet"],
      "target_item_id": "550e8400-e29b-41d4-a716-446655440000",
      "report_mode": "restock"
    }
  ],
  "frame_sample_interval": 5,
  "report_interval_seconds": 10
}
```

One camera feed can therefore restock cartons **and** pallets to (potentially different) inventory items simultaneously. Every `report_interval_seconds` the pipeline computes the per-category delta and pushes it upstream; each push is recorded as a `detection_events` row in Postgres.

---

## Architecture

```
vision-service/
├── app/
│   ├── main.py                       # FastAPI app factory + lifespan (init/dispose DB)
│   ├── config.py                     # pydantic-settings (env-driven; postgres + yolo + inventory)
│   ├── schemas/
│   │   └── job_schema.py             # CountingTarget, JobCreateRequest, JobResponse, DetectionEvent...
│   ├── core/
│   │   ├── detector.py               # ObjectDetector: YOLO11 wrapper (lazy import, category-agnostic)
│   │   ├── source.py                 # VideoSource: OpenCV RTSP/file (lazy import)
│   │   └── database.py               # Sync SQLAlchemy engine + session factory + init_db
│   ├── clients/
│   │   └── inventory_client.py       # Sync REST client -> inventory-service
│   ├── infrastructure/
│   │   ├── models.py                 # ORM: detection_jobs + detection_events (JSONB columns)
│   │   └── repository.py             # Sync JobRepository (insert/update/list)
│   ├── services/
│   │   ├── job.py                    # DetectionJob runtime state (multi-category counters)
│   │   ├── pipeline.py               # DetectionPipeline (worker loop + reporting + DB audit)
│   │   └── job_manager.py            # Registry + worker threads + DB wiring (singleton)
│   └── api/
│       ├── jobs.py                   # /jobs REST endpoints + /jobs/{id}/events
│       └── router.py                 # Aggregates routers
├── requirements.txt
├── Dockerfile
├── .env.example
└── README.md
```

**Dependency direction:** `api → services → {core, clients, infrastructure}`. The heavy ML libs (`ultralytics`, `cv2`) are imported lazily so the FastAPI app starts even before they are installed (only job *execution* requires them). The DB layer is **optional at startup** — if Postgres is unreachable, the service still runs in-memory and logs the failure.

### Database schema (vision-service Postgres)

```
detection_jobs
  id, source, source_type, model_path, targets (JSONB),
  status, counts (JSONB), last_reported_counts (JSONB),
  resolved_item_ids (JSONB), frames_processed,
  started_at, last_report_at, stopped_at, error, created_at

detection_events
  id, job_id (FK -> detection_jobs, CASCADE),
  target_name, delta, item_id, report_mode,
  status (success|failed), error, created_at
```

`detection_events` is the audit trail: one row per upstream report attempt (success or failure), realising the "→ Postgres" hop of the data flow.

---

## API reference

Base URL: `/api/v1`

| Method   | Path                  | Description                                  |
|----------|-----------------------|----------------------------------------------|
| `POST`   | `/jobs`               | Create (and auto-start) a detection job      |
| `GET`    | `/jobs`               | List jobs (optional `?status=running` filter)|
| `GET`    | `/jobs/{id}`          | Get job status & per-category counters       |
| `GET`    | `/jobs/{id}/events`   | List detection events (audit trail)          |
| `POST`   | `/jobs/{id}/stop`     | Stop a running job (flushes final deltas)    |
| `DELETE` | `/jobs/{id}`          | Stop and remove a job                        |
| `GET`    | `/health`             | Liveness probe                               |

---

## Getting started (local)

```bash
cd vision-service
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # installs ultralytics + torch + opencv + sqlalchemy + psycopg2

cp .env.example .env                     # edit POSTGRES_* and INVENTORY_SERVICE_URL
uvicorn app.main:app --reload --port 8001
```

> Prerequisites before creating jobs:
> - `inventory-service` reachable at `INVENTORY_SERVICE_URL` (default `http://localhost:8000`)
> - Postgres reachable at the `POSTGRES_*` settings (the service degrades to in-memory if not)

### About the model

`yolo11n.pt` (COCO, auto-downloaded) has no "carton"/"pallet" class — it is a placeholder so the service boots. For real counting, fine-tune YOLO11 on carton + pallet data and set `DEFAULT_MODEL_PATH=runs/detect/train/weights/best.pt`. Each job's `targets[].class_names` must match the classes your model emits.

---

## Running with Docker

```bash
docker build -t vision-service:latest .

docker run --rm -p 8001:8001 \
  -e INVENTORY_SERVICE_URL=http://host.docker.internal:8000 \
  -e POSTGRES_HOST=host.docker.internal \
  -e POSTGRES_USER=vision -e POSTGRES_PASSWORD=vision -e POSTGRES_DB=vision_db \
  -e DEFAULT_MODEL_PATH=weights/carton_pallet.pt \
  -v "$PWD/weights:/app/weights:ro" \
  vision-service:latest
```

### docker-compose (vision + inventory + 2× postgres)

```yaml
version: "3.9"
services:
  inv-postgres:
    image: postgres:16-alpine
    environment: { POSTGRES_USER: inventory, POSTGRES_PASSWORD: inventory, POSTGRES_DB: inventory_db }
    volumes: ["inv_pgdata:/var/lib/postgresql/data"]

  inventory-service:
    build: ../inventory-service
    depends_on: [inv-postgres]
    environment:
      POSTGRES_HOST: inv-postgres
      POSTGRES_USER: inventory
      POSTGRES_PASSWORD: inventory
      POSTGRES_DB: inventory_db
      ENVIRONMENT: production
    ports: ["8000:8000"]

  vision-postgres:
    image: postgres:16-alpine
    environment: { POSTGRES_USER: vision, POSTGRES_PASSWORD: vision, POSTGRES_DB: vision_db }
    volumes: ["vision_pgdata:/var/lib/postgresql/data"]

  vision-service:
    build: .
    depends_on: [inventory-service, vision-postgres]
    environment:
      INVENTORY_SERVICE_URL: http://inventory-service:8000
      POSTGRES_HOST: vision-postgres
      POSTGRES_USER: vision
      POSTGRES_PASSWORD: vision
      POSTGRES_DB: vision_db
      DEFAULT_MODEL_PATH: weights/carton_pallet.pt
    volumes: ["./weights:/app/weights:ro"]
    ports: ["8001:8001"]

volumes:
  inv_pgdata:
  vision_pgdata:
```

---

## Configuration

All settings come from environment variables (see `.env.example`). Key ones:

| Variable                          | Default            | Description                                |
|-----------------------------------|--------------------|--------------------------------------------|
| `POSTGRES_HOST` / `_PORT` / ...   | `localhost` / 5432 | vision-service DB connection               |
| `DEFAULT_MODEL_PATH`              | `yolo11n.pt`       | YOLO11 model path/id                       |
| `CONFIDENCE_THRESHOLD`            | `0.35`             | Min detection confidence                   |
| `DEFAULT_FRAME_SAMPLE_INTERVAL`   | `5`                | Process 1 frame every N                    |
| `DEFAULT_REPORT_INTERVAL_SECONDS` | `10`               | Seconds between upstream reports           |
| `INVENTORY_SERVICE_URL`           | `http://localhost:8000` | inventory-service base URL            |
| `INVENTORY_REQUEST_TIMEOUT_SECONDS` | `10`             | Per-request HTTP timeout                   |
| `API_KEY`                         | _(unset)_          | Secret required in `X-API-Key` on every `/api/v1` request; unset in production makes the API return `503` |
| `INVENTORY_API_KEY`               | _(falls back to `API_KEY`)_ | Key sent to inventory-service     |
| `CORS_ORIGINS`                    | `http://localhost:3000` | Allowed browser origins (`*` ignored in production) |
| `ENABLE_DOCS`                     | _(unset)_          | Force `/docs`, `/redoc`, `/openapi.json` on/off (off in production by default) |
| `ALLOWED_MEDIA_DIRS`              | `media`            | Directories a job's file `source` may resolve to |
| `ALLOWED_MODEL_DIR`               | `weights`          | Directory a job's `model_path` override may resolve to |
| `ALLOW_DEMO_SOURCES`              | `true`             | Accept simulated `demo://` sources         |
