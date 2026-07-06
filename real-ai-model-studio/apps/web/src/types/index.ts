// Local UI-only types for apps/web. These mirror backend response shapes that are
// NOT (yet) part of @rams/shared-types. The shared package is the canonical source
// for the compliance vocabulary; these are convenience shapes for screens only and
// carry NO compliance logic.

import type {
  ApprovalLevel,
  ComplianceStatus,
  OutputStatus,
  Role,
  RiskLevel,
} from "@rams/shared-types";

// GET /models/{id}/contracts (list) — mirrors the enriched backend response
export interface Contract {
  id: string;
  contract_number?: string;
  contract_type: string | null;
  contract_start: string | null;
  contract_end: string | null;
  ai_generation_allowed: boolean;
  ai_training_allowed: boolean;
  post_contract_use_allowed?: boolean;
}

// GET /models/{id}/permissions (list) — mirrors the enriched backend response
export interface Permission {
  id: string;
  contract_id: string;
  media_scope: string[];
  region_scope: string[];
  product_scope?: string[];
  prohibited_product_scope?: string[];
  swimwear_allowed: boolean;
  underwear_allowed: boolean;
  bath_allowed: string; // yes | no | conditional
  exposure_level_max: number;
  overseas_allowed?: boolean;
  approval_required_level: ApprovalLevel | string;
}

// GET /models/{id}/assets — mirrors backend list_assets response
export interface Asset {
  id: string;
  asset_type: string;
  usage_type: string;
  original_filename: string | null;
  consent_confirmed: boolean;
}

// GET /generations/{id}
export interface GenerationDetail {
  id: string;
  status: string; // queued | running | completed | failed
  output_count: number;
}

// GET /generations/{id}/outputs
export interface Output {
  id: string;
  file_path: string | null;
  output_status: OutputStatus;
  width: number | null;
  height: number | null;
}

// POST /outputs/{id}/approvals -> approval result
export interface ApprovalResult {
  output_status: OutputStatus;
  required_approvals: ApprovalLevel[];
  missing_approvals: ApprovalLevel[];
}

// GET /dashboard/expiring-contracts — contracts nearing their end date (P1-007)
export interface ExpiringContract {
  contract_id: string;
  model_id: string;
  stage_name: string;
  contract_number: string;
  contract_end: string;
  days_left: number;
}

// GET /audit-logs
export interface AuditLog {
  id: string;
  user_id: string | null;
  action_type: string;
  target_type: string;
  target_id: string | null;
  created_at: string;
}

// POST /deliveries
export interface Delivery {
  id: string;
  project_id: string;
  output_id: string;
  delivered_to: string;
  delivery_method: string;
  usage_media: string[] | null;
  usage_region: string[] | null;
  usage_start: string | null;
  usage_end: string | null;
}

// GET /users?role=&status_= (admin only) — user management (docs/02 §11)
export interface User {
  id: string;
  name: string;
  email: string;
  role: Role | string;
  status: string; // active | suspended
  department?: string | null;
  created_at?: string | null;
}

// GET /generations?project_id= — generation history for a project
export interface GenerationSummary {
  id: string;
  project_id: string;
  model_id: string;
  status: string; // queued | running | completed | failed
  output_count: number;
  prompt_text: string | null;
  generated_at: string | null;
}

// GET /deliveries?project_id= — deliveries for a project
export interface DeliverySummary {
  id: string;
  project_id: string;
  output_id: string;
  delivered_to: string;
  delivery_method: string;
  usage_media: string[] | string | null;
  usage_region: string[] | string | null;
  usage_start: string | null;
  usage_end: string | null;
  status: string;
  created_at: string | null;
}

// GET /outputs/{id}/reviews — existing reviews for an output
export interface ReviewItem {
  id: string;
  review_type: string;
  status: string;
  comment: string | null;
  reviewer_id: string | null;
  created_at: string | null;
}

// GET /outputs/{id}/approvals — existing approvals for an output
export interface ApprovalItem {
  id: string;
  approval_level: ApprovalLevel | string;
  approval_status: string;
  approval_comment: string | null;
  approver_id: string | null;
  approved_at: string | null;
}

// GET /outputs/{id}/approval-requests — external sign-off links (agency/person)
// issued for an output. The single-use token is NOT part of this shape; it is
// returned exactly once by POST /outputs/{id}/approval-requests.
export interface ApprovalRequest {
  id: string;
  level: "agency" | "person";
  status: string; // pending | approved | conditional | rejected | expired
  contact_name: string | null;
  contact_email: string | null;
  expires_at: string;
  created_at: string;
  decided_at: string | null;
}

// GET /portal/approvals/{token} — UNAUTHENTICATED view the external approver sees.
// No session; the token IS the credential. preview_url is a signed, short-lived URL.
export interface PortalApprovalView {
  level: string; // agency | person
  output_id: string;
  preview_url: string | null;
  project_name: string;
  status: string; // pending | approved | conditional | rejected | expired
  expires_at: string;
  already_decided: boolean;
}

// GET /prompt-templates — reusable prompt templates (P1-004)
export interface PromptTemplate {
  id: string;
  name: string;
  body: string;
  negative_body: string | null;
  tags: string[];
  is_active: boolean;
  created_at: string;
}

// Re-export commonly used unions for screen code convenience.
export type { ComplianceStatus, OutputStatus, RiskLevel, ApprovalLevel, Role };
