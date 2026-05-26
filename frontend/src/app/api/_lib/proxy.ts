import { cookies } from "next/headers";
import { NextResponse } from "next/server";

const BACKEND_BASE_URL = process.env.BACKEND_BASE_URL || "http://127.0.0.1:8877";
const GATEWAY_BASE_URL =
  process.env.GATEWAY_BASE_URL || "http://127.0.0.1:8765/gateways/rag_kefu_gateway";
const AUTH_COOKIE_NAME = "ft_session";
const AUTH_COOKIE_MAX_AGE = 60 * 60 * 72;

async function parseResponse(response: Response) {
  const text = await response.text();
  if (!text) {
    return null;
  }

  try {
    return JSON.parse(text);
  } catch {
    return {
      code: response.ok ? 0 : 5000,
      message: text,
      data: null,
    };
  }
}

export async function backendFetch(path: string, init?: RequestInit) {
  return fetch(`${BACKEND_BASE_URL}${path}`, {
    ...init,
    cache: "no-store",
  });
}

export async function backendJson(path: string, init?: RequestInit) {
  try {
    const response = await backendFetch(path, init);
    const data = await parseResponse(response);
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      {
        code: 5001,
        message: error instanceof Error ? error.message : "backend_unreachable",
        data: null,
      },
      { status: 502 }
    );
  }
}

export async function backendRequest(path: string, init?: RequestInit) {
  const response = await backendFetch(path, init);
  const data = await parseResponse(response);
  return { response, data };
}

export async function backendJsonWithAuth(path: string, init?: RequestInit) {
  try {
    const cookieStore = await cookies();
    const token = cookieStore.get(AUTH_COOKIE_NAME)?.value;
    const headers = new Headers(init?.headers);
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }
    const response = await backendFetch(path, {
      ...init,
      headers,
    });
    const data = await parseResponse(response);
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      {
        code: 5001,
        message: error instanceof Error ? error.message : "backend_unreachable",
        data: null,
      },
      { status: 502 }
    );
  }
}

export async function gatewayJson(path: string, init?: RequestInit) {
  try {
    const response = await fetch(`${GATEWAY_BASE_URL}${path}`, {
      ...init,
      cache: "no-store",
    });
    const data = await parseResponse(response);
    return { status: response.status, data };
  } catch (error) {
    return {
      status: 502,
      data: {
        code: 5001,
        message: error instanceof Error ? error.message : "gateway_unreachable",
        data: null,
      },
    };
  }
}

export { AUTH_COOKIE_MAX_AGE, AUTH_COOKIE_NAME, BACKEND_BASE_URL, GATEWAY_BASE_URL, parseResponse };
