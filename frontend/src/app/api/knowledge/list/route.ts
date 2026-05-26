import { backendJsonWithAuth } from "../../_lib/proxy";

export async function GET(request: Request) {
  const { search } = new URL(request.url);
  return backendJsonWithAuth(`/api/knowledge/list${search}`, {
    method: "GET",
  });
}
