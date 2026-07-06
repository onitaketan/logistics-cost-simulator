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
  ApprovalRequest,
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
  PortalApprovalView,
  PromptTemplate,
  ReviewItem,
  User,
} from "@/types";
import { clearAuth, getToken, redirectToLogin } from "@/lib/auth";

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

// Signed URLs from the backend are absolute for S3/R2 (presigned) but relative
// ("/api/v1/files?...") for the local backend — resolve those against the API host.
export function resolveFileUrl(url: string): string {
  if (url.startsWith("http://") || url.startsWith("https://")) return url;
  return BASE.replace(/\/api\/v1$/, "") + url;
}

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

// Unauthenticated request for the external approval PORTAL. A portal visitor has
// NO session, so this sends no Authorization header and — critically — does NOT
// clear auth or redirect to /login on 401 (that would wrongly bounce a valid
// portal visitor who is simply not a logged-in user). It still unwraps the
// {success,data,error} envelope and throws error.message on failure.
async function portalRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  });
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
  prompt_template_id?: string;
}

export interface PromptTemplatePayload {
  name?: string;
  body?: string;
  negative_body?: string;
  tags?: string[];
  is_active?: boolean;
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

export interface IssueApprovalRequestPayload {
  level: "agency" | "person";
  contact_name?: string;
  contact_email?: string;
  expires_in_days?: number;
}

export interface SubmitPortalApprovalPayload {
  decision: "approved" | "conditional" | "rejected";
  comment?: string;
  approver_name?: string;
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
  password?: string; // admin reset — hashed server-side, min 8 chars
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
  getOutputDownload: (outputId: string) =>
    request<{ download_url: string }>(`/outputs/${outputId}/download`),
  // Review preview: signed URL to SEE a candidate image (pre-approval, audited).
  getOutputPreview: (outputId: string) =>
    request<{ preview_url: string | null }>(`/outputs/${outputId}/preview`),
  listOutputReviews: (outputId: string) =>
    request<ReviewItem[]>(`/outputs/${outputId}/reviews`),
  listOutputApprovals: (outputId: string) =>
    request<ApprovalItem[]>(`/outputs/${outputId}/approvals`),

  // ---- External approval requests (agency/person sign-off links, docs/05 §9) ----
  // Issues a single-use, expiring portal link. The token is returned ONCE here.
  issueApprovalRequest: (outputId: string, payload: IssueApprovalRequestPayload) =>
    request<{
      id: string;
      token: string;
      portal_path: string;
      level: "agency" | "person";
      expires_at: string;
    }>(`/outputs/${outputId}/approval-requests`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  listApprovalRequests: (outputId: string) =>
    request<ApprovalRequest[]>(`/outputs/${outputId}/approval-requests`),

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
    from?: string; // YYYY-MM-DD
    to?: string;
    limit?: number;
  } = {}) => {
    const q = new URLSearchParams();
    if (filters.target_type) q.set("target_type", filters.target_type);
    if (filters.action_type) q.set("action_type", filters.action_type);
    if (filters.from) q.set("from", filters.from);
    if (filters.to) q.set("to", filters.to);
    if (filters.limit) q.set("limit", String(filters.limit));
    const qs = q.toString();
    return request<AuditLog[]>(`/audit-logs${qs ? `?${qs}` : ""}`);
  },

  // CSV export (P1-003) — raw fetch since the response is text/csv, not the JSON envelope.
  exportAuditCsv: async (filters: {
    target_type?: string;
    action_type?: string;
    from?: string;
    to?: string;
  } = {}): Promise<Blob> => {
    const q = new URLSearchParams();
    if (filters.target_type) q.set("target_type", filters.target_type);
    if (filters.action_type) q.set("action_type", filters.action_type);
    if (filters.from) q.set("from", filters.from);
    if (filters.to) q.set("to", filters.to);
    const tok = getToken();
    const res = await fetch(`${BASE}/audit-logs/export?${q.toString()}`, {
      headers: { ...(tok ? { Authorization: `Bearer ${tok}` } : {}) },
    });
    if (!res.ok) throw new Error(`CSVエクスポートに失敗しました (${res.status})`);
    return res.blob();
  },

  // ---- Prompt templates (P1-004) ----
  listPromptTemplates: (activeOnly?: boolean) => {
    const q = new URLSearchParams();
    if (activeOnly) q.set("active_only", "true");
    const qs = q.toString();
    return request<PromptTemplate[]>(`/prompt-templates${qs ? `?${qs}` : ""}`);
  },
  getPromptTemplate: (id: string) =>
    request<PromptTemplate>(`/prompt-templates/${id}`),
  createPromptTemplate: (payload: {
    name: string;
    body: string;
    negative_body?: string;
    tags?: string[];
  }) =>
    request<PromptTemplate>("/prompt-templates", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updatePromptTemplate: (id: string, payload: PromptTemplatePayload) =>
    request<PromptTemplate>(`/prompt-templates/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  deletePromptTemplate: (id: string) =>
    request<{ id: string; disabled: boolean }>(`/prompt-templates/${id}`, {
      method: "DELETE",
    }),

  // ---- External approval PORTAL (UNAUTHENTICATED — token is the credential) ----
  // These MUST NOT carry a Bearer token nor redirect on 401; a portal visitor has
  // no session. They go through portalRequest().
  getPortalApproval: (token: string) =>
    portalRequest<PortalApprovalView>(
      `/portal/approvals/${encodeURIComponent(token)}`,
    ),
  submitPortalApproval: (token: string, payload: SubmitPortalApprovalPayload) =>
    portalRequest<{ output_status: string; recorded: true }>(
      `/portal/approvals/${encodeURIComponent(token)}`,
      { method: "POST", body: JSON.stringify(payload) },
    ),
};
