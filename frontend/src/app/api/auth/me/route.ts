import { backendJsonWithAuth } from "../../_lib/proxy";

export async function GET() {
  return backendJsonWithAuth("/api/auth/me");
}

export async function PATCH(request: Request) {
  const body = await request.text();
  return backendJsonWithAuth("/api/auth/me", {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body,
  });
}
