/**
 * Typed client for the Python services, reached through the Next.js proxy
 * route (`/api/svc/<service>/<path>`).
 *
 * Every caller needs the same no-store fetch, JSON headers and `detail`/`error`
 * unwrapping, so the request plumbing and the response types live here rather
 * than in the components that use them.
 */

export { errorMessage } from "@/lib/utils";

// --------------------------------------------------------------------------- //
// Types (mirror the Python services' Pydantic schemas)                         //
// --------------------------------------------------------------------------- //
export type InventoryItem = {
  id: string;
  sku: string;
  name: string;
  description?: string | null;
  quantity: number;
  price: string;
  category?: string | null;
  low_stock_threshold: number;
  is_low_stock: boolean;
  is_in_stock: boolean;
  created_at: string;
  updated_at: string;
};

export type CountingTarget = {
  name: string;
  class_names: string[];
  target_item_id: string | null;
  target_sku: string | null;
  resolved_item_id: string | null;
  report_mode: "restock" | "consume";
  current_count: number;
  last_reported_count: number;
};

export type JobStatus = "pending" | "running" | "stopped" | "error";

export type Job = {
  id: string;
  source: string;
  source_type: string;
  targets: CountingTarget[];
  model_path: string;
  frame_sample_interval: number;
  report_interval_seconds: number;
  status: JobStatus;
  total_count: number;
  total_last_reported: number;
  frames_processed: number;
  started_at: string | null;
  last_report_at: string | null;
  stopped_at: string | null;
  error: string | null;
  created_at: string;
};

export type DetectionEvent = {
  id: string;
  job_id: string;
  target_name: string;
  delta: number;
  item_id: string;
  report_mode: "restock" | "consume";
  status: "success" | "failed";
  error: string | null;
  created_at: string;
};

export type ServiceName = "inventory" | "vision";

// --------------------------------------------------------------------------- //
// Request plumbing                                                             //
// --------------------------------------------------------------------------- //
export async function api<T>(service: ServiceName, path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api/svc/${service}/${path}`, {
    cache: "no-store",
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      detail = body.detail ?? body.error ?? detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// --------------------------------------------------------------------------- //
// Endpoints                                                                    //
// --------------------------------------------------------------------------- //
export const listInventory = () =>
  api<{ items: InventoryItem[]; total: number }>("inventory", "inventory-items");
export const listJobs = () => api<{ jobs: Job[]; total: number }>("vision", "jobs");
export const getJob = (id: string) => api<Job>("vision", `jobs/${id}`);
export const listEvents = (id: string) =>
  api<{ events: DetectionEvent[]; total: number }>("vision", `jobs/${id}/events`);
export const startJob = (payload: unknown) =>
  api<Job>("vision", "jobs", { method: "POST", body: JSON.stringify(payload) });
export const stopJob = (id: string) => api<Job>("vision", `jobs/${id}/stop`, { method: "POST" });
export const deleteJob = (id: string) => api<void>("vision", `jobs/${id}`, { method: "DELETE" });
