// Typed API client. All calls go through the /api/v1 envelope. The UI NEVER makes
// generation decisions locally — it renders whatever the compliance endpoint says.

import type { ApiResponse } from "@rams/shared-types";

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

function token(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("rams_token");
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token() ? { Authorization: `Bearer ${token()}` } : {}),
      ...(init.headers ?? {}),
    },
  });
  const body = (await res.json()) as ApiResponse<T>;
  if (!body.success || body.error) {
    throw new Error(body.error?.message ?? `Request failed: ${res.status}`);
  }
  return body.data as T;
}

export const api = {
  login: (email: string, password: string, otp_code?: string) =>
    request<{ access_token: string; role: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password, otp_code }),
    }),

  listModels: () => request<import("@rams/shared-types").Model[]>("/models"),
  listProjects: () => request<import("@rams/shared-types").Project[]>("/projects"),

  runComplianceCheck: (projectId: string, modelId: string, prompt?: string) =>
    request<import("@rams/shared-types").ComplianceResult>(
      `/projects/${projectId}/compliance-check`,
      { method: "POST", body: JSON.stringify({ model_id: modelId, prompt_text: prompt }) },
    ),

  createGeneration: (payload: Record<string, unknown>) =>
    request<{ generation_id: string; status: string }>("/generations", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};
