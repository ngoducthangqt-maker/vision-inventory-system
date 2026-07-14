#!/usr/bin/env bash
# Start both Python microservices in demo mode (no Postgres, no torch/camera).
#  - inventory-service on port 8000 (in-memory repository)
#  - vision-service    on port 8001 (in-memory repository + demo detector)
#
# Logs are written to /tmp/inventory-service.log and /tmp/vision-service.log.
# Re-run to restart (old processes are killed first).
set -u

ROOT=/home/z/my-project

pkill -9 -f _inmemory_launcher 2>/dev/null
pkill -9 -f "vision-service/.venv/bin/uvicorn" 2>/dev/null
sleep 1

# ---- inventory-service (port 8000, in-memory repo) ----
cd "$ROOT/inventory-service"
setsid .venv/bin/python scripts/run_inmemory.py > /tmp/inventory-service.log 2>&1 < /dev/null &
echo "inventory-service starting (pid $!)"

# Wait for health
for i in $(seq 1 40); do
  if .venv/bin/python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status==200 else 1)" 2>/dev/null; then
    echo "  -> inventory-service healthy after $i tries"; break
  fi
  sleep 0.25
done

# ---- vision-service (port 8001, in-memory repo + demo mode) ----
cd "$ROOT/vision-service"
ENVIRONMENT=development \
REPOSITORY_MODE=inmemory \
INVENTORY_SERVICE_URL=http://127.0.0.1:8000 \
INVENTORY_API_PREFIX=/api/v1 \
DEFAULT_MODEL_PATH=demo.pt \
setsid .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --log-level warning \
  > /tmp/vision-service.log 2>&1 < /dev/null &
echo "vision-service starting (pid $!)"

for i in $(seq 1 40); do
  if .venv/bin/python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8001/health', timeout=2).status==200 else 1)" 2>/dev/null; then
    echo "  -> vision-service healthy after $i tries"; break
  fi
  sleep 0.25
done

echo
echo "=== Services running ==="
echo "  inventory-service : http://127.0.0.1:8000/docs"
echo "  vision-service    : http://127.0.0.1:8001/docs"
echo "  inventory log     : /tmp/inventory-service.log"
echo "  vision log        : /tmp/vision-service.log"
