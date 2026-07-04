// Local UI-only types for apps/web. These mirror backend response shapes that are
// NOT (yet) part of @rams/shared-types. The shared package is the canonical source
// for the compliance vocabulary; these are convenience shapes for screens only and
// carry NO compliance logic.

import type {
  ApprovalLevel,
  ComplianceStatus,
  OutputStatus,
  RiskLevel,
} from "@rams/shared-types";

// POST /models/{id}/contracts ; GET /models/{id}/contracts
export interface Contract {
  id: string;
  model_id: string;
  contract_type: string | null;
  contract_start: string | null;
  contract_end: string | null;
  ai_generation_allowed: boolean;
  ai_training_allowed: boolean;
  overseas_allowed: boolean;
  notes: string | null;
}

// GET /models/{id}/permissions
export interface Permission {
  id: string;
  model_id: string;
  scope_type: string; // e.g. "swimwear" | "underwear" | "bath" | "body_edit" ...
  allowed: string; // "yes" | "no" | "conditional"
  approval_level: ApprovalLevel | null;
  notes: string | null;
}

// GET /models/{id}/assets
export interface Asset {
  id: string;
  model_id: string;
  asset_type: string;
  usage_type: string;
  file_path: string | null;
  consent_confirmed: boolean;
  created_at: string | null;
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
  usage_media: string | null;
  usage_region: string | null;
  usage_start: string | null;
  usage_end: string | null;
}

// Re-export commonly used unions for screen code convenience.
export type { ComplianceStatus, OutputStatus, RiskLevel, ApprovalLevel };
