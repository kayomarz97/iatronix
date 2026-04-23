import { NextRequest } from "next/server";

const INTERNAL_API_URL =
  process.env.INTERNAL_API_URL || "http://iatronix-backend:8000";

export async function POST(request: NextRequest) {
  const authHeader = request.headers.get("authorization");
  if (!authHeader) {
    return new Response(JSON.stringify({ detail: "Missing authorization" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return new Response(JSON.stringify({ detail: "Invalid JSON body" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }

  const backendResponse = await fetch(
    `${INTERNAL_API_URL}/api/v1/query/stream`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: authHeader,
      },
      body: JSON.stringify(body),
    }
  );

  if (!backendResponse.ok || !backendResponse.body) {
    const errText = await backendResponse.text();
    return new Response(errText, {
      status: backendResponse.status,
      headers: { "Content-Type": "application/json" },
    });
  }

  // Pass the SSE stream directly through to the client
  return new Response(backendResponse.body, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      "X-Accel-Buffering": "no",
      Connection: "keep-alive",
    },
  });
}
