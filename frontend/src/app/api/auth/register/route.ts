import { NextResponse } from "next/server";

import { backendRequest } from "../../_lib/proxy";

export async function POST(request: Request) {
  const body = await request.text();
  const { response, data } = await backendRequest("/api/auth/register", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body,
  });

  return NextResponse.json(data, { status: response.status });
}
