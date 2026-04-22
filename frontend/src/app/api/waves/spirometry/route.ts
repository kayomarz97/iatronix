import { NextRequest, NextResponse } from "next/server";

const INTERNAL_API_URL = process.env.INTERNAL_API_URL || "http://iatronix-backend:8000";

export async function POST(request: NextRequest) {
  const authHeader = request.headers.get("authorization");
  if (!authHeader) {
    return NextResponse.json({ detail: "Missing authorization" }, { status: 401 });
  }

  try {
    const formData = await request.formData();

    const response = await fetch(`${INTERNAL_API_URL}/api/v1/waves/spirometry`, {
      method: "POST",
      headers: { Authorization: authHeader },
      body: formData,
      signal: AbortSignal.timeout(120000),
    });

    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    if (error instanceof Error && error.name === "TimeoutError") {
      return NextResponse.json({ detail: "Analysis timed out — try a smaller image" }, { status: 504 });
    }
    return NextResponse.json({ detail: "Network error" }, { status: 500 });
  }
}
