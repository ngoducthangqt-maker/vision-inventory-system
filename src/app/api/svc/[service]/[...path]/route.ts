import { type NextRequest, NextResponse } from "next/server";

/**
 * Generic proxy to the Python microservices.
 *
 *   /api/svc/inventory/inventory-items
 *     -> GET  http://127.0.0.1:8000/api/v1/inventory-items
 *   /api/svc/vision/jobs
 *     -> POST http://127.0.0.1:8001/api/v1/jobs
 *   /api/svc/vision/jobs/<id>/events
 *     -> GET  http://127.0.0.1:8001/api/v1/jobs/<id>/events
 *
 * The HTTP method, query string and JSON body are forwarded; responses
 * (including status codes) are passed straight back to the browser.
 *
 * The upstream services are only reachable through this route, so it is the
 * enforcement point: path segments are restricted to a safe character set so
 * no request can escape the `/api/v1` prefix, bodies are size-capped, and the
 * server-side API key is attached here (never exposed to the browser).
 */

const SERVICE_PORTS: Record<string, string> = {
  inventory: "8000",
  vision: "8001",
};

const API_PREFIX = "/api/v1";
const MAX_BODY_BYTES = 64 * 1024;
// Path segments are ids, resource names and actions only: no slashes, no dot
// segments, nothing that could traverse out of API_PREFIX.
const SAFE_SEGMENT = /^[A-Za-z0-9._~-]{1,128}$/;

function isSafeSegment(segment: string): boolean {
  return SAFE_SEGMENT.test(segment) && segment !== "." && segment !== "..";
}

async function forward(
  req: NextRequest,
  service: string,
  pathSegments: string[],
): Promise<NextResponse> {
  const port = SERVICE_PORTS[service];
  if (!port) {
    return NextResponse.json(
      { error: `Unknown service: ${service}` },
      { status: 400 },
    );
  }

  if (pathSegments.length === 0 || !pathSegments.every(isSafeSegment)) {
    return NextResponse.json({ error: "Invalid request path" }, { status: 400 });
  }

  const path = pathSegments.join("/");
  // Preserve the original query string.
  const search = req.nextUrl.search ?? "";
  const url = `http://127.0.0.1:${port}${API_PREFIX}/${path}${search}`;

  // Forward the JSON body for non-GET requests (when present).
  let body: BodyInit | undefined;
  const headers: Record<string, string> = {
    Accept: "application/json",
  };
  const apiKey = process.env.SERVICE_API_KEY ?? "";
  if (apiKey) {
    headers["X-API-Key"] = apiKey;
  }
  if (req.method !== "GET" && req.method !== "HEAD") {
    const contentType = req.headers.get("content-type") ?? "";
    if (contentType.includes("application/json")) {
      const text = await req.text();
      if (text.length > MAX_BODY_BYTES) {
        return NextResponse.json(
          { error: "Request body too large" },
          { status: 413 },
        );
      }
      if (text) {
        body = text;
        headers["Content-Type"] = "application/json";
      }
    }
  }

  let upstream: Response;
  try {
    upstream = await fetch(url, {
      method: req.method,
      headers,
      body,
      cache: "no-store",
    });
  } catch (exc) {
    // The upstream message can leak internal details, so log it server-side
    // and return a generic error to the caller.
    console.error(`Proxy to ${service}-service failed`, exc);
    return NextResponse.json(
      { error: `Cannot reach ${service}-service` },
      { status: 502 },
    );
  }

  // Pass the body through verbatim and preserve the status code.
  const responseText = await upstream.text();
  const responseHeaders = new Headers();
  const upstreamContentType = upstream.headers.get("content-type");
  if (upstreamContentType) {
    responseHeaders.set("content-type", upstreamContentType);
  }
  return new NextResponse(responseText, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

type RouteContext = {
  params: Promise<{ service: string; path: string[] }>;
};

export async function GET(req: NextRequest, ctx: RouteContext) {
  const { service, path } = await ctx.params;
  return forward(req, service, path);
}

export async function POST(req: NextRequest, ctx: RouteContext) {
  const { service, path } = await ctx.params;
  return forward(req, service, path);
}

export async function PATCH(req: NextRequest, ctx: RouteContext) {
  const { service, path } = await ctx.params;
  return forward(req, service, path);
}

export async function DELETE(req: NextRequest, ctx: RouteContext) {
  const { service, path } = await ctx.params;
  return forward(req, service, path);
}
