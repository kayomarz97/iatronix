import { NextRequest, NextResponse } from "next/server";

const INTERNAL_API_URL =
  process.env.INTERNAL_API_URL || "http://iatronix-backend:8000";

export async function POST(request: NextRequest) {
  try {
    const authHeader = request.headers.get("authorization");
    const contentType = request.headers.get("content-type") || "";

    // Stream the raw body through to the backend — avoids Node.js
    // FormData re-encoding issues with file uploads.
    const body = await request.arrayBuffer();

    const response = await fetch(
      `${INTERNAL_API_URL}/api/v1/documents/upload`,
      {
        method: "POST",
        headers: {
          ...(authHeader ? { "Authorization": authHeader } : {}),
          "Content-Type": contentType,
        },
        body: body,
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
