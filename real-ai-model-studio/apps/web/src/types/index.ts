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
