import { backendJsonWithAuth } from "../../../_lib/proxy";

export async function POST(request: Request) {
  const formData = await request.formData();
  return backendJsonWithAuth("/api/admin/knowledge/upload", {
    method: "POST",
    body: formData,
  });
}
