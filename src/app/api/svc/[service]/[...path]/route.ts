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
 * The HTTP method, query string and JSON body are all forwarded. Responses
 * (including status codes) are passed straight back to the browser.
 */

const SERVICE_PORTS: Record<string, string> = {
  inventory: "8000",
  vision: "8001",
};

const API_PREFIX = "/api/v1";

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

  const path = pathSegments.join("/");
  // Preserve the original query string.
  const search = req.nextUrl.search ?? "";
  const url = `http://127.0.0.1:${port}${API_PREFIX}/${path}${search}`;

  // Forward the JSON body for non-GET requests (when present).
  let body: BodyInit | undefined;
  const headers: Record<string, string> = {
    Accept: "application/json",
  };
  if (req.method !== "GET" && req.method !== "HEAD") {
    const contentType = req.headers.get("content-type") ?? "";
    if (contentType.includes("application/json")) {
      const text = await req.text();
      if (text) {
        body = text;
        headers["Content-Type"] = "application/json";
      }
    }
  }

  let upstream: Response;
  let responseText: string;
  try {
    upstream = await fetch(url, {
      method: req.method,
      headers,
      body,
      cache: "no-store",
    });
    responseText = await upstream.text();
  } catch (exc) {
    const message = exc instanceof Error ? exc.message : String(exc);
    return NextResponse.json(
      {
        error: `Cannot reach ${service}-service on port ${port}: ${message}`,
      },
      { status: 502 },
    );
  }

  // Pass the body through verbatim and preserve the status code.
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
