import { NextRequest, NextResponse } from "next/server";

const INTERNAL_API_URL = process.env.INTERNAL_API_URL || "http://iatronix-backend:8000";

export async function GET(request: NextRequest) {
  const q = request.nextUrl.searchParams.get("q") ?? "";
  if (q.length < 2) return NextResponse.json({ suggestions: [] });

  try {
    const authHeader = request.headers.get("authorization") ?? "";
    const response = await fetch(
      `${INTERNAL_API_URL}/api/v1/suggestions?q=${encodeURIComponent(q)}&limit=5`,
      {
        headers: authHeader ? { Authorization: authHeader } : {},
        signal: AbortSignal.timeout(4000),
      }
    );
    const data = await response.json();
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ suggestions: [] });
  }
}
