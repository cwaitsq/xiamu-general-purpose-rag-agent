import { backendJsonWithAuth } from "../../../_lib/proxy";

export async function GET(
  _request: Request,
  context: { params: Promise<{ knowledgeId: string }> }
) {
  const { knowledgeId } = await context.params;
  return backendJsonWithAuth(`/api/admin/knowledge/${encodeURIComponent(knowledgeId)}`);
}

export async function PATCH(
  request: Request,
  context: { params: Promise<{ knowledgeId: string }> }
) {
  const { knowledgeId } = await context.params;
  const body = await request.text();
  return backendJsonWithAuth(`/api/admin/knowledge/${encodeURIComponent(knowledgeId)}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body,
  });
}

export async function DELETE(
  _request: Request,
  context: { params: Promise<{ knowledgeId: string }> }
) {
  const { knowledgeId } = await context.params;
  return backendJsonWithAuth(`/api/admin/knowledge/${encodeURIComponent(knowledgeId)}`, {
    method: "DELETE",
  });
}
