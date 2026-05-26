import { backendJson } from "../../../_lib/proxy";

export async function GET(
  request: Request,
  context: { params: Promise<{ jobId: string }> }
) {
  const { jobId } = await context.params;
  const { search } = new URL(request.url);
  return backendJson(`/api/ingestion/jobs/${jobId}${search}`, {
    method: "GET",
  });
}
