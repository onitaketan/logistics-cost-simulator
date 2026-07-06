// Typed API client. All calls go through the /api/v1 envelope. The UI NEVER makes
// generation/compliance decisions locally — it renders whatever the backend says
// and only mirrors (defense in depth) the disables the API would enforce anyway.

import type {
  ApiResponse,
  ComplianceResult,
  Model,
  Project,
} from "@rams/shared-types";
import type {
  ApprovalItem,
  ApprovalResult,
  Asset,
  AuditLog,
  Contract,
  Delivery,
  DeliverySummary,
  ExpiringContract,
  GenerationDetail,
  GenerationSummary,
  Output,
  Permission,
  ReviewItem,
  User,
} from "@/types";
import { clearAuth, getToken, redirectToLogin } from "@/lib/auth";

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const tok = getToken();
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(tok ? { Authorization: `Bearer ${tok}` } : {}),
      ...(init.headers ?? {}),
    },
  });

  // 401 => session invalid/expired. Clear the token and bounce to /login.
  if (res.status === 401) {
    clearAuth();
    redirectToLogin();
    throw new Error("認証が切れました。再度ログインしてください。");
  }

  const body = (await res.json()) as ApiResponse<T>;
  if (!body.success || body.error) {
    throw new Error(body.error?.message ?? `Request failed: ${res.status}`);
  }
  return body.data as T;
}

// multipart request for asset upload (no JSON Content-Type; browser sets boundary).
async function upload<T>(path: string, form: FormData): Promise<T> {
  const tok = getToken();
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    body: form,
    headers: { ...(tok ? { Authorization: `Bearer ${tok}` } : {}) },
  });
  if (res.status === 401) {
    clearAuth();
    redirectToLogin();
    throw new Error("認証が切れました。再度ログインしてください。");
  }
  const body = (await res.json()) as ApiResponse<T>;
  if (!body.success || body.error) {
    throw new Error(body.error?.message ?? `Request failed: ${res.status}`);
  }
  return body.data as T;
}

export interface GenerationParams {
  output_count: number;
  width: number;
  height: number;
  [key: string]: unknown;
}

export interface CreateGenerationPayload {
  project_id: string;
  model_id: string;
  compliance_check_id: string;
  prompt_text: string;
  negative_prompt_text?: string;
  generation_params: GenerationParams;
}

export interface CreateDeliveryPayload {
  project_id: string;
  output_id: string;
  delivered_to: string;
  delivery_method: string;
  usage_media?: string[];
  usage_region?: string[];
  usage_start?: string;
  usage_end?: string;
}

export interface CreateUserPayload {
  name: string;
  email: string;
  password: string;
  role: string;
  department?: string;
}

export interface UpdateUserPayload {
  name?: string;
  role?: string;
  status?: string;
  department?: string;
}

export const api = {
  // ---- Auth ----
  login: (email: string, password: string, otp_code?: string) =>
    request<{ access_token: string; role: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password, otp_code }),
    }),
  logout: () => request<Record<string, never>>("/auth/logout", { method: "POST" }),

  // ---- Models ----
  listModels: () => request<Model[]>("/models"),
  getModel: (id: string) => request<Model>(`/models/${id}`),
  createModel: (payload: {
    stage_name: string;
    real_name: string;
    agency_name?: string;
    birth_date?: string;
    notes?: string;
  }) => request<Model>("/models", { method: "POST", body: JSON.stringify(payload) }),
  updateModel: (id: string, payload: Partial<Model>) =>
    request<Model>(`/models/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  setAdultVerification: (id: string, adult_verified: boolean) =>
    request<Model>(`/models/${id}/adult-verification`, {
      method: "POST",
      body: JSON.stringify({ adult_verified }),
    }),

  // ---- Contracts / Permissions / Assets ----
  listContracts: (modelId: string) =>
    request<Contract[]>(`/models/${modelId}/contracts`),
  createContract: (modelId: string, payload: Partial<Contract>) =>
    request<Contract>(`/models/${modelId}/contracts`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  listPermissions: (modelId: string) =>
    request<Permission[]>(`/models/${modelId}/permissions`),
  createPermission: (modelId: string, payload: Partial<Permission>) =>
    request<Permission>(`/models/${modelId}/permissions`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  listAssets: (modelId: string) => request<Asset[]>(`/models/${modelId}/assets`),
  uploadAsset: (
    modelId: string,
    file: File,
    asset_type: string,
    usage_type: string,
    consent_confirmed: boolean,
  ) => {
    const form = new FormData();
    form.append("file", file);
    form.append("asset_type", asset_type);
    form.append("usage_type", usage_type);
    form.append("consent_confirmed", String(consent_confirmed));
    return upload<Asset>(`/models/${modelId}/assets`, form);
  },
  deleteAsset: (assetId: string) =>
    request<Record<string, never>>(`/assets/${assetId}`, { method: "DELETE" }),

  // ---- Projects ----
  listProjects: () => request<Project[]>("/projects"),
  getProject: (id: string) => request<Project>(`/projects/${id}`),
  createProject: (payload: {
    project_name: string;
    client_name?: string;
    product_category?: string;
    deadline?: string;
  }) => request<Project>("/projects", { method: "POST", body: JSON.stringify(payload) }),
  addRequirements: (projectId: string, payload: Record<string, unknown>) =>
    request<Project>(`/projects/${projectId}/requirements`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  assignModel: (projectId: string, model_id: string, usage_role: string) =>
    request<Record<string, unknown>>(`/projects/${projectId}/models`, {
      method: "POST",
      body: JSON.stringify({ model_id, usage_role }),
    }),

  // ---- Compliance ----
  runComplianceCheck: (
    projectId: string,
    modelId: string,
    prompt?: string,
    trainingRequested?: boolean,
  ) =>
    request<ComplianceResult>(`/projects/${projectId}/compliance-check`, {
      method: "POST",
      body: JSON.stringify({
        model_id: modelId,
        prompt_text: prompt,
        training_requested: trainingRequested,
      }),
    }),

  // ---- Generation ----
  createGeneration: (payload: CreateGenerationPayload) =>
    request<{ generation_id: string; status: string }>("/generations", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getGeneration: (id: string) => request<GenerationDetail>(`/generations/${id}`),
  listOutputs: (generationId: string) =>
    request<Output[]>(`/generations/${generationId}/outputs`),

  // ---- Outputs: review / approval / delivery ----
  setOutputStatus: (outputId: string, output_status: string) =>
    request<Output>(`/outputs/${outputId}/status`, {
      method: "PATCH",
      body: JSON.stringify({ output_status }),
    }),
  reviseOutput: (outputId: string, payload: Record<string, unknown> = {}) =>
    request<{ generation_id?: string; status?: string }>(
      `/outputs/${outputId}/revise`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
  addReview: (
    outputId: string,
    review_type: string,
    status: string,
    comment?: string,
  ) =>
    request<Record<string, unknown>>(`/outputs/${outputId}/reviews`, {
      method: "POST",
      body: JSON.stringify({ review_type, status, comment }),
    }),
  addApproval: (
    outputId: string,
    approval_level: string,
    approval_status: string,
    approval_comment?: string,
  ) =>
    request<ApprovalResult>(`/outputs/${outputId}/approvals`, {
      method: "POST",
      body: JSON.stringify({ approval_level, approval_status, approval_comment }),
    }),
  downloadOutput: (outputId: string) =>
    request<{ download_url: string }>(`/outputs/${outputId}/download`),
  getOutputDownload: (outputId: string) =>
    request<{ download_url: string }>(`/outputs/${outputId}/download`),
  listOutputReviews: (outputId: string) =>
    request<ReviewItem[]>(`/outputs/${outputId}/reviews`),
  listOutputApprovals: (outputId: string) =>
    request<ApprovalItem[]>(`/outputs/${outputId}/approvals`),

  // ---- Generations (list) ----
  listGenerations: (projectId?: string) =>
    request<GenerationSummary[]>(
      `/generations${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ""}`,
    ),

  // ---- Deliveries ----
  createDelivery: (payload: CreateDeliveryPayload) =>
    request<Delivery>("/deliveries", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  listDeliveries: (projectId?: string) =>
    request<DeliverySummary[]>(
      `/deliveries${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ""}`,
    ),

  // ---- Users (admin) ----
  listUsers: (filters: { role?: string; status_?: string; limit?: number; offset?: number } = {}) => {
    const q = new URLSearchParams();
    if (filters.role) q.set("role", filters.role);
    if (filters.status_) q.set("status_", filters.status_);
    if (filters.limit) q.set("limit", String(filters.limit));
    if (filters.offset) q.set("offset", String(filters.offset));
    const qs = q.toString();
    return request<User[]>(`/users${qs ? `?${qs}` : ""}`);
  },
  createUser: (payload: CreateUserPayload) =>
    request<User>("/users", { method: "POST", body: JSON.stringify(payload) }),
  updateUser: (id: string, payload: UpdateUserPayload) =>
    request<User>(`/users/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),

  // ---- Dashboard ----
  expiringContracts: (days?: number) =>
    request<ExpiringContract[]>(
      `/dashboard/expiring-contracts${days ? `?days=${days}` : ""}`,
    ),

  // ---- Audit ----
  listAuditLogs: (filters: {
    target_type?: string;
    action_type?: string;
    limit?: number;
  } = {}) => {
    const q = new URLSearchParams();
    if (filters.target_type) q.set("target_type", filters.target_type);
    if (filters.action_type) q.set("action_type", filters.action_type);
    if (filters.limit) q.set("limit", String(filters.limit));
    const qs = q.toString();
    return request<AuditLog[]>(`/audit-logs${qs ? `?${qs}` : ""}`);
  },
};
