import { NextRequest, NextResponse } from "next/server";

const INTERNAL_API_URL =
  process.env.INTERNAL_API_URL || "http://iatronix-backend:8000";

function extractApiKey(request: NextRequest): string | null {
  const auth = request.headers.get("authorization");
  if (auth?.startsWith("Bearer ")) return auth.slice(7);
  return request.headers.get("x-api-key");
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const apiKey = extractApiKey(request);
    if (!apiKey) {
      return NextResponse.json({ detail: "Missing API key" }, { status: 401 });
    }

    const { id } = await params;

    const response = await fetch(
      `${INTERNAL_API_URL}/api/v1/history/${id}`,
      {
        method: "DELETE",
        headers: { "Authorization": `Bearer ${apiKey}` },
        signal: AbortSignal.timeout(10000),
      }
    );

    const text = await response.text();
    const data = text ? JSON.parse(text) : {};
    return NextResponse.json(data, { status: response.status });
  } catch {
    return NextResponse.json(
      { detail: "Failed to delete history item" },
      { status: 502 }
    );
  }
}
