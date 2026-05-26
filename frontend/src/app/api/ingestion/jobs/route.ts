import { backendJson } from "../../_lib/proxy";

export async function POST(request: Request) {
  const body = await request.text();
  return backendJson("/api/ingestion/jobs", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body,
  });
}
