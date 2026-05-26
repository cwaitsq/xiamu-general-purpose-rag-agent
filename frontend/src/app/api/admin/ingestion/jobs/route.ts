import { backendJsonWithAuth } from "../../../_lib/proxy";

export async function GET() {
  return backendJsonWithAuth("/api/admin/ingestion/jobs");
}

export async function POST(request: Request) {
  const body = await request.text();
  return backendJsonWithAuth("/api/admin/ingestion/jobs", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body,
  });
}
