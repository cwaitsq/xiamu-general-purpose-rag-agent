import { NextResponse } from "next/server";

import { BACKEND_BASE_URL, GATEWAY_BASE_URL } from "../../_lib/proxy";

export async function GET() {
  const [backendResult, gatewayResult] = await Promise.allSettled([
    fetch(`${BACKEND_BASE_URL}/health`, { cache: "no-store" }).then((response) => response.json()),
    fetch(`${GATEWAY_BASE_URL}/health`, { cache: "no-store" }).then((response) => response.json()),
  ]);

  return NextResponse.json({
    code: 0,
    message: "ok",
    data: {
      backend: backendResult.status === "fulfilled" ? backendResult.value.data || backendResult.value : null,
      gateway: gatewayResult.status === "fulfilled" ? gatewayResult.value : null,
    },
  });
}
