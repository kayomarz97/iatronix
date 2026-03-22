import { NextRequest, NextResponse } from "next/server";

const INTERNAL_API_URL =
  process.env.INTERNAL_API_URL || "http://iatronix-backend:8000";

export async function GET(request: NextRequest) {
  try {
    const apiKey = request.headers.get("x-api-key") || "";
    const response = await fetch(`${INTERNAL_API_URL}/api/v1/documents`, {
      headers: { "X-API-Key": apiKey },
    });
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch {
    return NextResponse.json(
      { detail: "Internal proxy error" },
      { status: 502 }
    );
  }
}
