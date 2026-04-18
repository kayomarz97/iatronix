import { NextRequest, NextResponse } from "next/server";

const INTERNAL_API_URL =
  process.env.INTERNAL_API_URL || "http://iatronix-backend:8000";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const authHeader = request.headers.get("authorization");

    if (!authHeader) {
      return NextResponse.json({ detail: "Missing authorization" }, { status: 401 });
    }

    const response = await fetch(`${INTERNAL_API_URL}/api/v1/query`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": authHeader,
      },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(130000), // 130s to match Traefik
    });

    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    if (error instanceof Error && error.name === "TimeoutError") {
      return NextResponse.json(
        { detail: "Backend request timed out" },
        { status: 504 }
      );
    }
    console.error("Proxy error:", error);
    return NextResponse.json(
      { detail: "Internal proxy error" },
      { status: 502 }
    );
  }
}
