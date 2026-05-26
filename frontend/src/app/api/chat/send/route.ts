import { backendJsonWithAuth } from "../../_lib/proxy";

export async function POST(request: Request) {
  const contentType = request.headers.get("content-type") || "";

  if (contentType.includes("multipart/form-data")) {
    const formData = await request.formData();
    return backendJsonWithAuth("/api/chat/send", {
      method: "POST",
      body: formData,
    });
  }

  const body = await request.text();
  return backendJsonWithAuth("/api/chat/send", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body,
  });
}
