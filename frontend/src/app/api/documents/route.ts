import { NextRequest, NextResponse } from "next/server";

const INTERNAL_API_URL =
  process.env.INTERNAL_API_URL || "http://iatronix-backend:8000";

export async function GET(request: NextRequest) {
  try {
    const authHeader = request.headers.get("authorization");
    const headers: Record<string, string> = {};
    if (authHeader) headers["Authorization"] = authHeader;

    const response = await fetch(`${INTERNAL_API_URL}/api/v1/documents`, {
      headers,
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
