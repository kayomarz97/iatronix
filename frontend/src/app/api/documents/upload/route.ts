import { NextRequest, NextResponse } from "next/server";

const INTERNAL_API_URL =
  process.env.INTERNAL_API_URL || "http://iatronix-backend:8000";

export async function POST(request: NextRequest) {
  try {
    const apiKey = request.headers.get("x-api-key") || "";
    const formData = await request.formData();

    const response = await fetch(
      `${INTERNAL_API_URL}/api/v1/documents/upload`,
      {
        method: "POST",
        headers: { "X-API-Key": apiKey },
        body: formData,
      }
    );

    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch {
    return NextResponse.json(
      { detail: "Internal proxy error" },
      { status: 502 }
    );
  }
}
