import "server-only";

import { cookies } from "next/headers";

const BACKEND_BASE_URL = process.env.BACKEND_BASE_URL || "http://127.0.0.1:8877";
const AUTH_COOKIE_NAME = "ft_session";

type ApiEnvelope<T> = {
  code: number;
  message: string;
  data: T;
};

export type SessionUser = {
  id: string;
  tenant_id: string;
  email: string;
  display_name: string;
  role: "admin" | "user";
  status: "active" | "disabled";
  created_at: string;
  updated_at: string;
  last_login_at?: string | null;
};

export async function getCurrentUser(): Promise<SessionUser | null> {
  const cookieStore = await cookies();
  const token = cookieStore.get(AUTH_COOKIE_NAME)?.value;
  if (!token) {
    return null;
  }

  try {
    const response = await fetch(`${BACKEND_BASE_URL}/api/auth/me`, {
      cache: "no-store",
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });
    if (!response.ok) {
      return null;
    }
    const payload = (await response.json()) as ApiEnvelope<SessionUser>;
    return payload.data || null;
  } catch {
    return null;
  }
}
