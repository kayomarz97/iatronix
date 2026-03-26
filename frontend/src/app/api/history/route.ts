import { NextRequest, NextResponse } from "next/server";

const INTERNAL_API_URL =
  process.env.INTERNAL_API_URL || "http://iatronix-backend:8000";

function extractApiKey(request: NextRequest): string | null {
  const auth = request.headers.get("authorization");
  if (auth?.startsWith("Bearer ")) return auth.slice(7);
  return request.headers.get("x-api-key");
}

export async function GET(request: NextRequest) {
  try {
    const apiKey = extractApiKey(request);
    if (!apiKey) {
      return NextResponse.json({ detail: "Missing API key" }, { status: 401 });
    }

    const { searchParams } = new URL(request.url);
    const limit = searchParams.get("limit") || "50";
    const offset = searchParams.get("offset") || "0";

    const response = await fetch(
      `${INTERNAL_API_URL}/api/v1/history?limit=${limit}&offset=${offset}`,
      {
        headers: { "X-API-Key": apiKey },
        signal: AbortSignal.timeout(10000),
      }
    );

    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch {
    return NextResponse.json(
      { detail: "Failed to fetch history" },
      { status: 502 }
    );
  }
}

export async function DELETE(request: NextRequest) {
  try {
    const apiKey = extractApiKey(request);
    if (!apiKey) {
      return NextResponse.json({ detail: "Missing API key" }, { status: 401 });
    }

    const response = await fetch(`${INTERNAL_API_URL}/api/v1/history`, {
      method: "DELETE",
      headers: { "X-API-Key": apiKey },
      signal: AbortSignal.timeout(10000),
    });

    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch {
    return NextResponse.json(
      { detail: "Failed to clear history" },
      { status: 502 }
    );
  }
}
