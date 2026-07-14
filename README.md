# Vision Inventory System

An end-to-end **carton & pallet counting pipeline** for warehouse/line-side
cameras. It reads an **RTSP stream** or video file, counts objects with
**YOLO11**, pushes count deltas to the **inventory-service** REST API, and
persists an audit trail to **Postgres**.

## Data flow

```
 Camera (RTSP / video file)
        │  frames
        ▼
 ┌──────────────────────┐  track ids   ┌──────────────────┐
 │  vision-service      │ ───────────▶ │  YOLO11 (Ultralytics) │
 │  • OpenCV capture    │              │  model.track (ByteTrack) │
 │  • sample 1/N frames │              └─────────┬────────┘
 └──────────────────────┘                        │ unique carton / pallet track ids
                                                 ▼
                                   ┌───────────────────────────┐
                                   │ per-category delta every  │
                                   │ report_interval_seconds   │
                                   └─────────────┬─────────────┘
                                                 │ REST (httpx)
                          ┌──────────────────────┴───────────────────────┐
                          ▼                                                ▼
            ┌─────────────────────────────┐              ┌───────────────────────────────┐
            │ inventory-service (FastAPI) │              │ vision-service Postgres       │
            │  POST /inventory-items/     │              │  detection_jobs (durable)     │
            │    {id}/restock|consume     │              │  detection_events (audit log) │
            │  → updates inventory_items   │              └───────────────────────────────┘
            │  (inventory-service Postgres)│
            └─────────────────────────────┘
```

The **final hop is Postgres in two places**: inventory-service stores the
updated stock levels; vision-service stores a durable audit trail of every
report it pushed.

## Repository layout

```
.
├── docker-compose.yml          # one command runs the whole stack
├── README.md                   # this file
├── inventory-service/          # FastAPI + SQLAlchemy + PostgreSQL (Clean Architecture)
│   ├── app/                    # domain / use_cases / infrastructure / presentation
│   ├── scripts/seed_items.py   # seed CARTON-001 + PALLET-001
│   ├── Dockerfile
│   └── requirements.txt
└── vision-service/             # FastAPI + YOLO11 + OpenCV + httpx + PostgreSQL
    ├── app/                    # core / clients / services / infrastructure / api
    ├── scripts/demo_count.py   # CLI: create a counting job + poll status
    ├── Dockerfile
    └── requirements.txt
```

## Functions

| Function | Where | Notes |
|----------|-------|-------|
| Read RTSP camera | `vision-service/app/core/source.py` | OpenCV `VideoCapture` (FFMPEG backend, `BUFFERSIZE=1`); also reads local video files |
| Run YOLO11 | `vision-service/app/core/detector.py` | `ObjectDetector` wraps `ultralytics.YOLO`, uses `model.track(persist=True, bytetrack.yaml)` |
| Count carton / pallet | `vision-service/app/services/pipeline.py` | Multi-category: each job declares `targets` (carton, pallet) with class-name → category mapping; counts **unique track IDs** so each physical object is counted once |
| Call API to update inventory | `vision-service/app/clients/inventory_client.py` | Sync `httpx`: per-category delta → `POST /inventory-items/{id}/restock` or `/consume` |
| Persist to Postgres | `vision-service/app/infrastructure/` (audit) + `inventory-service/app/infrastructure/` (stock) | `detection_jobs` + `detection_events` (vision) and `inventory_items` (inventory) |

## Quick start (Docker)

```bash
# 1) Run the whole stack (2× Postgres + inventory-service + vision-service)
docker compose up --build

# 2) In another terminal, seed sample inventory items
pip install httpx
python inventory-service/scripts/seed_items.py
#   -> creates CARTON-001 and PALLET-001 with quantity 0

# 3) Create a counting job against a video file (or RTSP URL)
#    Put your fine-tuned YOLO11 weights in vision-service/weights/best.pt
python vision-service/scripts/demo_count.py \
    --source /path/to/warehouse.mp4 \
    --model-path weights/best.pt
#   -> prints live carton/pallet counters + the audit trail of reports sent
```

Service docs:
- inventory-service: http://localhost:8000/docs
- vision-service: http://localhost:8001/docs

## Quick start (local, no Docker)

```bash
# Terminal 1 — Postgres for both services (or use the compose containers)
docker compose up inventory-postgres vision-postgres

# Terminal 2 — inventory-service
cd inventory-service
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
POSTGRES_HOST=localhost POSTGRES_PORT=5433 uvicorn app.main:app --reload --port 8000

# Terminal 3 — seed + vision-service
cd inventory-service && python scripts/seed_items.py
cd ../vision-service
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt   # includes ultralytics + torch + opencv
POSTGRES_HOST=localhost POSTGRES_PORT=5434 \
INVENTORY_SERVICE_URL=http://localhost:8000 \
uvicorn app.main:app --reload --port 8001

# Terminal 4 — run a counting job
python vision-service/scripts/demo_count.py --source /path/to/video.mp4 --model-path runs/weights/best.pt
```

### Quick start (no Postgres at all — in-memory inventory)

For a fast local demo without any database, run inventory-service with its
in-memory repository, then seed and drive it:

```bash
# Terminal 1 — inventory-service in-memory (data lost on restart)
cd inventory-service
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/run_inmemory.py            # -> http://localhost:8000/docs

# Terminal 2 — seed + use the service
python scripts/seed_items.py
```

## End-to-end example

Create a job that counts **both** cartons and pallets from one camera and
restocks the matching inventory items:

```bash
curl -X POST http://localhost:8001/api/v1/jobs \
  -H 'Content-Type: application/json' \
  -d '{
    "source": "rtsp://admin:pass@10.0.0.5:554/stream",
    "targets": [
      {"name": "carton", "class_names": ["carton","box"],     "target_sku": "CARTON-001", "report_mode": "restock"},
      {"name": "pallet", "class_names": ["pallet","wooden pallet"], "target_sku": "PALLET-001", "report_mode": "restock"}
    ],
    "frame_sample_interval": 5,
    "report_interval_seconds": 10
  }'
```

Poll the job and its audit trail:

```bash
curl http://localhost:8001/api/v1/jobs/<job_id>
curl http://localhost:8001/api/v1/jobs/<job_id>/events
```

Check the resulting stock in inventory-service:

```bash
curl http://localhost:8000/api/v1/inventory-items
```

## Why tracking instead of per-frame detection?

Counting in every frame would multiply-count the **same** box as it moves
through the scene. The service uses `model.track(persist=True)` (ByteTrack)
which assigns each object a stable **track ID**. The pipeline only increments
a category's counter when a *new* track ID whose class matches that category
appears — so each physical carton/pallet is counted exactly once.

## About the YOLO11 model

`yolo11n.pt` (COCO, auto-downloaded) has no "carton"/"pallet" class — it is a
placeholder so the service boots. For real counting, fine-tune YOLO11 on
carton + pallet data and set `DEFAULT_MODEL_PATH=runs/detect/train/weights/best.pt`
(or pass `model_path` per job). Each job's `targets[].class_names` must match
the classes your model emits.

## Configuration

Each service is env-driven (see `inventory-service/.env.example` and
`vision-service/.env.example`). The compose file wires them together with
sensible defaults; override via the environment as needed.
