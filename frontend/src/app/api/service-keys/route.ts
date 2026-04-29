import { NextRequest, NextResponse } from "next/server";

const INTERNAL_API_URL =
  process.env.INTERNAL_API_URL || "http://iatronix-backend:8000";

function authHeader(request: NextRequest): Record<string, string> {
  const auth = request.headers.get("authorization");
  return auth ? { "Authorization": auth } : {};
}

export async function GET(request: NextRequest) {
  try {
    const res = await fetch(`${INTERNAL_API_URL}/api/v1/service_keys`, {
      headers: authHeader(request),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (error) {
    console.error('Service keys GET error:', error);
    return NextResponse.json({ detail: 'Internal server error' }, { status: 500 });
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const res = await fetch(`${INTERNAL_API_URL}/api/v1/service_keys`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...authHeader(request),
      },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (error) {
    console.error('Service keys POST error:', error);
    return NextResponse.json({ detail: 'Internal server error' }, { status: 500 });
  }
}
