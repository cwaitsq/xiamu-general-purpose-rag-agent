import { backendJsonWithAuth } from "../../../../_lib/proxy";

export async function GET(
  _request: Request,
  context: { params: Promise<{ logId: string }> }
) {
  const { logId } = await context.params;
  return backendJsonWithAuth(`/api/admin/logs/qa/${encodeURIComponent(logId)}`);
}

export async function PATCH(
  request: Request,
  context: { params: Promise<{ logId: string }> }
) {
  const { logId } = await context.params;
  const body = await request.text();
  return backendJsonWithAuth(`/api/admin/logs/qa/${encodeURIComponent(logId)}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body,
  });
}

export async function DELETE(
  _request: Request,
  context: { params: Promise<{ logId: string }> }
) {
  const { logId } = await context.params;
  return backendJsonWithAuth(`/api/admin/logs/qa/${encodeURIComponent(logId)}`, {
    method: "DELETE",
  });
}
