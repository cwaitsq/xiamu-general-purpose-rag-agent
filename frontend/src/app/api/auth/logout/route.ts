import { AUTH_COOKIE_NAME, backendJsonWithAuth } from "../../_lib/proxy";

export async function POST() {
  const response = await backendJsonWithAuth("/api/auth/logout", {
    method: "POST",
  });
  response.cookies.set({
    name: AUTH_COOKIE_NAME,
    value: "",
    httpOnly: true,
    sameSite: "lax",
    secure: false,
    path: "/",
    maxAge: 0,
  });
  return response;
}
