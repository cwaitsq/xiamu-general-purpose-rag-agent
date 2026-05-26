import { backendJsonWithAuth } from "../../../_lib/proxy";

export async function PATCH(request: Request, context: { params: Promise<{ userId: string }> }) {
  const { userId } = await context.params;
  const body = await request.text();
  return backendJsonWithAuth(`/api/admin/users/${encodeURIComponent(userId)}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body,
  });
}

export async function DELETE(_request: Request, context: { params: Promise<{ userId: string }> }) {
  const { userId } = await context.params;
  return backendJsonWithAuth(`/api/admin/users/${encodeURIComponent(userId)}`, {
    method: "DELETE",
  });
}
