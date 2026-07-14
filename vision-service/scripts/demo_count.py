"""Demo CLI: create a carton+pallet counting job and poll its status.

This is a convenience client for the vision-service REST API. It creates a
job that counts BOTH cartons and pallets from an RTSP stream or video file,
then polls the job status until it finishes (or the user interrupts),
printing live per-category counters and the final inventory impact.

Prerequisites:
  * inventory-service running (and seeded with CARTON-001 + PALLET-001 — see
    ``inventory-service/scripts/seed_items.py``)
  * vision-service running (``uvicorn app.main:app --port 8001``)
  * a YOLO11 model that emits "carton"/"pallet" classes (set --model-path)

Usage::

    # Count from an RTSP camera
    python scripts/demo_count.py --source rtsp://admin:pass@10.0.0.5:554/stream

    # Count from a local video file (great for testing)
    python scripts/demo_count.py --source /data/warehouse.mp4 --model-path runs/weights/best.pt

    # Use item ids instead of SKUs
    python scripts/demo_count.py \
        --source /data/warehouse.mp4 \
        --carton-item-id 550e8400-e29b-41d4-a716-446655440000 \
        --pallet-item-id 660e8400-e29b-41d4-a716-446655440000

    # Polling stops automatically after --max-seconds (default 120).
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from uuid import UUID

import httpx

DEFAULT_VISION_URL = os.environ.get("VISION_SERVICE_URL", "http://localhost:8001")
API_PREFIX = "/api/v1"


def _build_targets(args: argparse.Namespace) -> list[dict]:
    """Build the two counting targets (carton + pallet) from CLI args."""
    carton_target = {
        "name": "carton",
        "class_names": args.carton_classes.split(","),
        "report_mode": args.carton_mode,
    }
    if args.carton_item_id:
        carton_target["target_item_id"] = args.carton_item_id
    else:
        carton_target["target_sku"] = args.carton_sku

    pallet_target = {
        "name": "pallet",
        "class_names": args.pallet_classes.split(","),
        "report_mode": args.pallet_mode,
    }
    if args.pallet_item_id:
        pallet_target["target_item_id"] = args.pallet_item_id
    else:
        pallet_target["target_sku"] = args.pallet_sku

    return [carton_target, pallet_target]


def _create_job(client: httpx.Client, payload: dict) -> dict:
    response = client.post(f"{API_PREFIX}/jobs", json=payload)
    if response.status_code >= 400:
        print(f"ERROR creating job ({response.status_code}): {response.text}", file=sys.stderr)
        sys.exit(1)
    return response.json()


def _get_job(client: httpx.Client, job_id: str) -> dict:
    response = client.get(f"{API_PREFIX}/jobs/{job_id}")
    response.raise_for_status()
    return response.json()


def _stop_job(client: httpx.Client, job_id: str) -> dict:
    response = client.post(f"{API_PREFIX}/jobs/{job_id}/stop")
    response.raise_for_status()
    return response.json()


def _format_target(t: dict) -> str:
    return (
        f"{t['name']:7s} count={t['current_count']:>3d} "
        f"reported={t['last_reported_count']:>3d} "
        f"mode={t['report_mode']:8s} item={t.get('resolved_item_id') or t.get('target_sku') or t.get('target_item_id')}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Demo: count cartons + pallets via vision-service.")
    parser.add_argument("--source", required=True, help="RTSP URL or path to a video file.")
    parser.add_argument("--vision-url", default=DEFAULT_VISION_URL, help="vision-service base URL.")
    parser.add_argument("--model-path", default=None, help="YOLO11 model path (e.g. runs/weights/best.pt).")
    parser.add_argument("--frame-sample", type=int, default=5, help="Process 1 frame every N.")
    parser.add_argument("--report-interval", type=float, default=10.0, help="Seconds between reports.")
    parser.add_argument("--poll-interval", type=float, default=2.0, help="Status poll interval (s).")
    parser.add_argument("--max-seconds", type=float, default=120.0, help="Stop polling after N seconds.")
    parser.add_argument("--no-auto-start", action="store_true", help="Create job without starting it.")

    # Carton target
    parser.add_argument("--carton-sku", default="CARTON-001")
    parser.add_argument("--carton-item-id", default=None)
    parser.add_argument("--carton-classes", default="carton,box")
    parser.add_argument("--carton-mode", default="restock", choices=["restock", "consume"])

    # Pallet target
    parser.add_argument("--pallet-sku", default="PALLET-001")
    parser.add_argument("--pallet-item-id", default=None)
    parser.add_argument("--pallet-classes", default="pallet,wooden pallet")
    parser.add_argument("--pallet-mode", default="restock", choices=["restock", "consume"])

    args = parser.parse_args()

    payload = {
        "source": args.source,
        "source_type": "auto",
        "targets": _build_targets(args),
        "frame_sample_interval": args.frame_sample,
        "report_interval_seconds": args.report_interval,
        "auto_start": not args.no_auto_start,
    }
    if args.model_path:
        payload["model_path"] = args.model_path

    print(f"Creating counting job at {args.vision_url} ...")
    print(f"  source : {args.source}")
    print(f"  targets: carton (sku={args.carton_sku}, mode={args.carton_mode}), "
          f"pallet (sku={args.pallet_sku}, mode={args.pallet_mode})")

    with httpx.Client(base_url=args.vision_url, timeout=15.0) as client:
        # Health check
        try:
            client.get("/health").raise_for_status()
        except httpx.HTTPError as exc:
            print(f"ERROR: cannot reach vision-service at {args.vision_url}: {exc}", file=sys.stderr)
            return 1

        job = _create_job(client, payload)
        job_id = job["id"]
        print(f"\nJob created: id={job_id}  status={job['status']}\n")

        deadline = time.monotonic() + args.max_seconds
        last_status = None
        try:
            while time.monotonic() < deadline:
                current = _get_job(client, job_id)
                status = current["status"]
                if status != last_status:
                    print(f"[{status}]")
                    last_status = status

                print(f"  frames={current['frames_processed']:>5d}  "
                      f"total={current['total_count']:>3d}  "
                      f"reported={current['total_last_reported']:>3d}")
                for t in current["targets"]:
                    print("    " + _format_target(t))

                if status in ("stopped", "error"):
                    break
                time.sleep(args.poll_interval)
            else:
                # Timed out -> request a graceful stop.
                print("\nMax seconds reached; stopping job ...")
                _stop_job(client, job_id)
                time.sleep(1.0)
                current = _get_job(client, job_id)
        except KeyboardInterrupt:
            print("\nInterrupted by user; stopping job ...")
            _stop_job(client, job_id)
            time.sleep(1.0)
            current = _get_job(client, job_id)

        # Final summary + events.
        print("\n=== Final job state ===")
        print(f"  status           : {current['status']}")
        print(f"  frames_processed : {current['frames_processed']}")
        print(f"  total_count      : {current['total_count']}")
        if current.get("error"):
            print(f"  error            : {current['error']}")
        for t in current["targets"]:
            print("    " + _format_target(t))

        events_resp = client.get(f"{API_PREFIX}/jobs/{job_id}/events")
        if events_resp.status_code == 200:
            events = events_resp.json().get("events", [])
            print(f"\n=== Detection events (audit trail) ===")
            print(f"  total events: {len(events)}")
            for e in events:
                print(f"    {e['target_name']:7s} delta={e['delta']:>3d} "
                      f"{e['report_mode']:8s} {e['status']:7s} at {e['created_at']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
