import { backendJsonWithAuth } from "../../../../_lib/proxy";

export async function GET(
  _request: Request,
  context: { params: Promise<{ jobId: string }> }
) {
  const { jobId } = await context.params;
  return backendJsonWithAuth(`/api/admin/ingestion/jobs/${encodeURIComponent(jobId)}`);
}

export async function PATCH(
  request: Request,
  context: { params: Promise<{ jobId: string }> }
) {
  const { jobId } = await context.params;
  const body = await request.text();
  return backendJsonWithAuth(`/api/admin/ingestion/jobs/${encodeURIComponent(jobId)}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body,
  });
}

export async function DELETE(
  _request: Request,
  context: { params: Promise<{ jobId: string }> }
) {
  const { jobId } = await context.params;
  return backendJsonWithAuth(`/api/admin/ingestion/jobs/${encodeURIComponent(jobId)}`, {
    method: "DELETE",
  });
}
