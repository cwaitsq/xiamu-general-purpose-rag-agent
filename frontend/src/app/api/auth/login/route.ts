import { NextResponse } from "next/server";

import { AUTH_COOKIE_MAX_AGE, AUTH_COOKIE_NAME, backendRequest } from "../../_lib/proxy";

function extractToken(payload: unknown) {
  if (!payload || typeof payload !== "object" || !("data" in payload)) {
    return null;
  }
  const data = payload.data;
  if (!data || typeof data !== "object" || !("token" in data)) {
    return null;
  }
  return typeof data.token === "string" ? data.token : null;
}

export async function POST(request: Request) {
  const body = await request.text();
  const { response, data } = await backendRequest("/api/auth/login", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body,
  });

  const result = NextResponse.json(data, { status: response.status });
  const token = extractToken(data);
  if (response.ok && token) {
    result.cookies.set({
      name: AUTH_COOKIE_NAME,
      value: token,
      httpOnly: true,
      sameSite: "lax",
      secure: false,
      path: "/",
      maxAge: AUTH_COOKIE_MAX_AGE,
    });
  }
  return result;
}
