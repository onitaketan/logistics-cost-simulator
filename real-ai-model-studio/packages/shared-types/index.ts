// Shared types & vocabularies used by both web and (as reference for) api.
// The compliance vocabulary here MUST stay in sync with the backend engine and
// the scope_vocabulary table. Treat this as the canonical enum set for the UI.

export type Role = "admin" | "legal" | "sales" | "creative" | "approver" | "viewer";

export type ComplianceStatus = "ok" | "conditional" | "ng" | "prohibited";
export type RiskLevel = "low" | "middle" | "high" | "prohibited";
export type ApprovalLevel = "internal" | "legal" | "agency" | "person" | "admin";

export type OutputStatus =
  | "candidate" | "selected" | "rejected" | "approved" | "delivered";

export type ProjectStatus =
  | "draft" | "generating" | "review" | "approved" | "delivered" | "closed";

export const MEDIA_SCOPE = ["web", "sns", "ec", "print", "outdoor", "video"] as const;
export const REGION_SCOPE = ["japan", "asia", "eu", "global"] as const;
export const EXPOSURE_LEVELS = [0, 1, 2, 3, 4, 5] as const;

// API envelope (docs/03_api_spec.md §2)
export interface ApiResponse<T> {
  success: boolean;
  data: T | null;
  error: { code: string; message: string } | null;
}

export interface Violation {
  field: string;
  message: string;
  result: ComplianceStatus;
}

export interface ComplianceResult {
  check_status: ComplianceStatus;
  risk_level: RiskLevel;
  violations: Violation[];
  required_approvals: ApprovalLevel[];
  check_summary: string;
  compliance_check_id?: string;
}

export interface Model {
  id: string;
  stage_name: string;
  agency_name: string | null;
  adult_verified: boolean;
  status: string;
  birth_date: string | null;
}

export interface Project {
  id: string;
  project_name: string;
  client_name: string | null;
  product_category: string | null;
  project_status: ProjectStatus;
  risk_level: RiskLevel | null;
  deadline: string | null;
}

// UI helper: badge color per compliance status
export const STATUS_COLOR: Record<ComplianceStatus, string> = {
  ok: "#1a7f37",         // green
  conditional: "#9a6700", // amber
  ng: "#cf222e",         // red
  prohibited: "#82071e", // dark red
};
