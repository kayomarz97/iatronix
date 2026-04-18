import { NextRequest, NextResponse } from "next/server";

const INTERNAL_API_URL =
  process.env.INTERNAL_API_URL || "http://iatronix-backend:8000";

export async function DELETE(
  request: NextRequest,
  context: { params: Promise<{ service: string }> }
) {
  const { service } = await context.params;
  const auth = request.headers.get("authorization");
  const res = await fetch(
    `${INTERNAL_API_URL}/api/v1/service-keys/${service}`,
    {
      method: "DELETE",
      headers: auth ? { "Authorization": auth } : {},
    }
  );
  if (res.status === 204) {
    return new NextResponse(null, { status: 204 });
  }
  const data = await res.json().catch(() => ({}));
  return NextResponse.json(data, { status: res.status });
}
