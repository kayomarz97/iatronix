import { NextRequest, NextResponse } from "next/server";

const INTERNAL_API_URL =
  process.env.INTERNAL_API_URL || "http://iatronix-backend:8000";

function proxyHeaders(request: NextRequest): Record<string, string> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  const apiKey = request.headers.get("x-api-key");
  if (apiKey) headers["X-API-Key"] = apiKey;
  return headers;
}

export async function GET(request: NextRequest) {
  try {
    const response = await fetch(`${INTERNAL_API_URL}/api/v1/auth/llm-key`, {
      headers: proxyHeaders(request),
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

export async function PUT(request: NextRequest) {
  try {
    const body = await request.json();
    const response = await fetch(`${INTERNAL_API_URL}/api/v1/auth/llm-key`, {
      method: "PUT",
      headers: proxyHeaders(request),
      body: JSON.stringify(body),
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

export async function DELETE(request: NextRequest) {
  try {
    const response = await fetch(`${INTERNAL_API_URL}/api/v1/auth/llm-key`, {
      method: "DELETE",
      headers: proxyHeaders(request),
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
