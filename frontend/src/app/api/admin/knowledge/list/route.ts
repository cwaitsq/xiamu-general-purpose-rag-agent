import { backendJsonWithAuth } from "../../../_lib/proxy";

export async function GET() {
  return backendJsonWithAuth("/api/admin/knowledge/list");
}
