import { backendJsonWithAuth } from "../../_lib/proxy";

export async function POST(request: Request) {
  const formData = await request.formData();
  return backendJsonWithAuth("/api/knowledge/upload", {
    method: "POST",
    body: formData,
  });
}
