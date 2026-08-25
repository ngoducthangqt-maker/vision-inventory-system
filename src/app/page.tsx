"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Boxes, Camera, Database, Layers, Package, Play, RefreshCw, Square, Trash2, Zap } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";

import {
  deleteJob,
  errorMessage,
  listEvents,
  listInventory,
  listJobs,
  startJob,
  stopJob,
  type DetectionEvent,
  type InventoryItem,
  type Job,
  type JobStatus,
} from "@/lib/services";

const DEMO_JOB_PAYLOAD = {
  source: "demo://warehouse-line-1",
  source_type: "auto",
  targets: [
    { name: "carton", class_names: ["carton", "box"], target_sku: "CARTON-001", report_mode: "restock" },
    { name: "pallet", class_names: ["pallet", "wooden pallet"], target_sku: "PALLET-001", report_mode: "restock" },
  ],
  frame_sample_interval: 1,
  report_interval_seconds: 1,
};

// --------------------------------------------------------------------------- //
// Small UI helpers                                                             //
// --------------------------------------------------------------------------- //
function statusVariant(status: JobStatus): "default" | "secondary" | "destructive" | "outline" {
  switch (status) {
    case "running":
      return "default";
    case "pending":
      return "secondary";
    case "error":
      return "destructive";
    default:
      return "outline";
  }
}

function statusDot(status: JobStatus) {
  const colour =
    status === "running"
      ? "bg-emerald-500"
      : status === "error"
        ? "bg-red-500"
        : status === "pending"
          ? "bg-amber-500"
          : "bg-slate-400";
  return <span className={`inline-block h-2 w-2 rounded-full ${colour} ${status === "running" ? "animate-pulse" : ""}`} />;
}

function targetColour(name: string) {
  return name === "carton" ? "text-amber-600" : name === "pallet" ? "text-slate-600" : "text-foreground";
}

function fmtTime(iso: string | null) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleTimeString();
}

// --------------------------------------------------------------------------- //
// Main page                                                                    //
// --------------------------------------------------------------------------- //
export default function Page() {
  const [items, setItems] = useState<InventoryItem[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [eventsByJob, setEventsByJob] = useState<Record<string, DetectionEvent[]>>({});
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [expandedJob, setExpandedJob] = useState<string | null>(null);
  const [now, setNow] = useState(Date.now());
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const refreshAll = useCallback(async () => {
    try {
      const [inv, jb] = await Promise.all([listInventory(), listJobs()]);
      setItems(inv.items);
      setJobs(jb.jobs);
    } catch (err) {
      // Silent on background polls; toast on first load.
      if (loading) toast.error("Cannot reach services", { description: errorMessage(err) });
    } finally {
      setLoading(false);
    }
  }, [loading]);

  // Initial load + polling while there are running/pending jobs.
  useEffect(() => {
    refreshAll();
  }, [refreshAll]);

  const hasActive = jobs.some((j) => j.status === "running" || j.status === "pending");
  useEffect(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    if (hasActive) {
      pollRef.current = setInterval(() => {
        setNow(Date.now());
        refreshAll();
      }, 2000);
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [hasActive, refreshAll]);

  // Load events for the expanded job whenever jobs refresh.
  useEffect(() => {
    if (!expandedJob) return;
    let cancelled = false;
    listEvents(expandedJob)
      .then((r) => {
        if (!cancelled) setEventsByJob((prev) => ({ ...prev, [expandedJob]: r.events }));
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [expandedJob, now]);

  const handleStartDemo = useCallback(async () => {
    setCreating(true);
    try {
      await startJob(DEMO_JOB_PAYLOAD);
      toast.success("Demo job started", { description: "Counting cartons + pallets from the simulated camera…" });
      await refreshAll();
    } catch (err) {
      toast.error("Failed to start job", { description: errorMessage(err) });
    } finally {
      setCreating(false);
    }
  }, [refreshAll]);

  const handleStop = useCallback(async (id: string) => {
    try {
      await stopJob(id);
      toast.info("Stop requested", { description: "Flushing final count delta…" });
      await refreshAll();
    } catch (err) {
      toast.error("Failed to stop job", { description: errorMessage(err) });
    }
  }, [refreshAll]);

  const handleDelete = useCallback(async (id: string) => {
    try {
      await deleteJob(id);
      setEventsByJob((prev) => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
      if (expandedJob === id) setExpandedJob(null);
      await refreshAll();
    } catch (err) {
      toast.error("Failed to delete job", { description: errorMessage(err) });
    }
  }, [refreshAll, expandedJob]);

  const cartonItem = useMemo(() => items.find((i) => i.sku === "CARTON-001"), [items]);
  const palletItem = useMemo(() => items.find((i) => i.sku === "PALLET-001"), [items]);
  const activeCount = jobs.filter((j) => j.status === "running" || j.status === "pending").length;
  const totalReported = jobs.reduce((s, j) => s + j.total_last_reported, 0);

  return (
    <div className="flex min-h-screen flex-col bg-muted/30">
      {/* Header */}
      <header className="sticky top-0 z-10 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <Boxes className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-base font-semibold leading-tight">Vision Inventory System</h1>
              <p className="text-xs text-muted-foreground">Camera → YOLO → Inventory API → Postgres</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant={activeCount > 0 ? "default" : "secondary"} className="gap-1.5">
              {activeCount > 0 ? <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-300" /> : null}
              {activeCount} active
            </Badge>
            <Button variant="outline" size="sm" onClick={() => refreshAll()} className="gap-1.5">
              <RefreshCw className="h-4 w-4" /> Refresh
            </Button>
          </div>
        </div>
      </header>

      {/* Data flow strip */}
      <section className="border-b bg-background">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-2 px-4 py-3 text-xs">
          <FlowChip icon={<Camera className="h-3.5 w-3.5" />} label="Camera (RTSP)" tone="text-sky-600" />
          <Arrow />
          <FlowChip icon={<Zap className="h-3.5 w-3.5" />} label="YOLO11 tracking" tone="text-violet-600" />
          <Arrow />
          <FlowChip icon={<Package className="h-3.5 w-3.5" />} label="Inventory API (REST)" tone="text-emerald-600" />
          <Arrow />
          <FlowChip icon={<Database className="h-3.5 w-3.5" />} label="Postgres (audit)" tone="text-amber-600" />
          <span className="ml-auto text-muted-foreground">Demo mode: simulated camera + in-memory stores</span>
        </div>
      </section>

      {/* Main content */}
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">
        {/* KPI cards */}
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <KpiCard label="Carton stock" value={cartonItem?.quantity ?? 0} icon={<Package className="h-4 w-4" />} tone="text-amber-600" />
          <KpiCard label="Pallet stock" value={palletItem?.quantity ?? 0} icon={<Layers className="h-4 w-4" />} tone="text-slate-600" />
          <KpiCard label="Detection jobs" value={jobs.length} icon={<Camera className="h-4 w-4" />} tone="text-sky-600" />
          <KpiCard label="Total reported" value={totalReported} icon={<Database className="h-4 w-4" />} tone="text-emerald-600" />
        </div>

        <div className="mt-6 flex flex-col gap-4 lg:flex-row">
          {/* Inventory panel */}
          <Card className="lg:w-[360px] lg:shrink-0">
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-sm">
                <Package className="h-4 w-4 text-emerald-600" /> Inventory
              </CardTitle>
              <CardDescription>Live stock updated by vision-service via REST</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {loading ? (
                <Skeleton className="h-24 w-full" />
              ) : items.length === 0 ? (
                <p className="text-sm text-muted-foreground">No inventory items yet.</p>
              ) : (
                items.map((it) => (
                  <div key={it.id} className="rounded-lg border bg-card p-3">
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-xs text-muted-foreground">{it.sku}</span>
                      {it.is_low_stock ? (
                        <Badge variant="destructive" className="text-[10px]">low stock</Badge>
                      ) : (
                        <Badge variant="outline" className="text-[10px]">in stock</Badge>
                      )}
                    </div>
                    <div className="mt-1 flex items-end justify-between">
                      <span className="text-sm font-medium">{it.name}</span>
                      <span className={`text-2xl font-semibold tabular-nums ${it.quantity > 0 ? "text-emerald-600" : "text-muted-foreground"}`}>
                        {it.quantity}
                      </span>
                    </div>
                    <div className="mt-1 flex items-center justify-between text-[11px] text-muted-foreground">
                      <span>threshold {it.low_stock_threshold}</span>
                      <span>${it.price}</span>
                    </div>
                  </div>
                ))
              )}
            </CardContent>
          </Card>

          {/* Jobs panel */}
          <Card className="flex-1">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="flex items-center gap-2 text-sm">
                    <Camera className="h-4 w-4 text-sky-600" /> Detection jobs
                  </CardTitle>
                  <CardDescription>Each job counts cartons + pallets and reports deltas upstream</CardDescription>
                </div>
                <Button size="sm" onClick={handleStartDemo} disabled={creating} className="gap-1.5">
                  <Play className="h-4 w-4" /> {creating ? "Starting…" : "Start demo"}
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="space-y-2">
                  <Skeleton className="h-20 w-full" />
                  <Skeleton className="h-20 w-full" />
                </div>
              ) : jobs.length === 0 ? (
                <div className="flex flex-col items-center justify-center gap-2 py-10 text-center">
                  <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted">
                    <Camera className="h-6 w-6 text-muted-foreground" />
                  </div>
                  <p className="text-sm font-medium">No detection jobs yet</p>
                  <p className="text-xs text-muted-foreground">Click “Start demo” to simulate a camera feed counting cartons + pallets.</p>
                </div>
              ) : (
                <div className="max-h-[28rem] space-y-3 overflow-y-auto pr-1">
                  {jobs.map((job) => {
                    const expanded = expandedJob === job.id;
                    const events = eventsByJob[job.id] ?? [];
                    return (
                      <div key={job.id} className="rounded-lg border bg-card">
                        <button
                          type="button"
                          onClick={() => setExpandedJob(expanded ? null : job.id)}
                          className="flex w-full items-center gap-3 p-3 text-left"
                        >
                          <span className="flex items-center gap-2">
                            {statusDot(job.status)}
                            <Badge variant={statusVariant(job.status)} className="text-[10px] uppercase">{job.status}</Badge>
                          </span>
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2">
                              {job.targets.map((t) => (
                                <span key={t.name} className={`text-sm font-semibold tabular-nums ${targetColour(t.name)}`}>
                                  {t.current_count} {t.name}s
                                </span>
                              ))}
                            </div>
                            <div className="mt-0.5 truncate text-[11px] text-muted-foreground">
                              {job.frames_processed} frames · reported {job.total_last_reported} · {fmtTime(job.started_at)}
                            </div>
                          </div>
                          <div className="flex shrink-0 items-center gap-1" onClick={(e) => e.stopPropagation()}>
                            {(job.status === "running" || job.status === "pending") && (
                              <Button size="sm" variant="outline" onClick={() => handleStop(job.id)} className="h-7 gap-1 px-2 text-xs">
                                <Square className="h-3 w-3" /> Stop
                              </Button>
                            )}
                            <Button size="sm" variant="ghost" onClick={() => handleDelete(job.id)} className="h-7 px-2 text-xs text-muted-foreground hover:text-destructive">
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          </div>
                        </button>

                        {expanded && (
                          <>
                            <Separator />
                            <div className="p-3">
                              <div className="mb-2 flex items-center justify-between">
                                <h4 className="text-xs font-semibold uppercase text-muted-foreground">Detection events (audit trail)</h4>
                                <span className="text-[11px] text-muted-foreground">{events.length} reports</span>
                              </div>
                              {events.length === 0 ? (
                                <p className="py-4 text-center text-xs text-muted-foreground">No reports sent yet.</p>
                              ) : (
                                <div className="max-h-48 space-y-1.5 overflow-y-auto">
                                  {events.map((e) => (
                                    <div key={e.id} className="flex items-center gap-2 rounded border bg-muted/40 px-2 py-1.5 text-xs">
                                      <span className={`font-medium ${targetColour(e.target_name)}`}>{e.target_name}</span>
                                      <Badge variant="outline" className="text-[10px]">+{e.delta}</Badge>
                                      <Badge variant={e.report_mode === "restock" ? "default" : "secondary"} className="text-[10px]">{e.report_mode}</Badge>
                                      <Badge variant={e.status === "success" ? "default" : "destructive"} className="text-[10px]">{e.status}</Badge>
                                      <span className="ml-auto font-mono text-[10px] text-muted-foreground">{fmtTime(e.created_at)}</span>
                                    </div>
                                  ))}
                                </div>
                              )}
                              {job.error && (
                                <p className="mt-2 rounded bg-destructive/10 p-2 text-xs text-destructive">{job.error}</p>
                              )}
                            </div>
                          </>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </main>

      {/* Footer */}
      <footer className="mt-auto border-t bg-background">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-2 px-4 py-3 text-xs text-muted-foreground sm:flex-row">
          <span>inventory-service :8000 · vision-service :8001 · Next.js :3000</span>
          <span>Demo mode — data is in-memory and reset on restart</span>
        </div>
      </footer>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Presentational sub-components                                               //
// --------------------------------------------------------------------------- //
function FlowChip({ icon, label, tone }: { icon: React.ReactNode; label: string; tone: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border bg-card px-2.5 py-1 font-medium">
      <span className={tone}>{icon}</span> {label}
    </span>
  );
}

function Arrow() {
  return <span className="text-muted-foreground">→</span>;
}

function KpiCard({ label, value, icon, tone }: { label: string; value: number; icon: React.ReactNode; tone: string }) {
  return (
    <Card className="overflow-hidden">
      <CardContent className="p-4">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium text-muted-foreground">{label}</span>
          <span className={tone}>{icon}</span>
        </div>
        <div className="mt-2 text-3xl font-semibold tabular-nums">{value}</div>
      </CardContent>
    </Card>
  );
}
