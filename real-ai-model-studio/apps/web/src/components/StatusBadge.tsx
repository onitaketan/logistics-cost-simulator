import type { ComplianceStatus } from "@rams/shared-types";

const LABEL: Record<ComplianceStatus, string> = {
  ok: "OK 生成可能",
  conditional: "条件付き",
  ng: "NG 生成不可",
  prohibited: "絶対禁止",
};

export function StatusBadge({ status }: { status: ComplianceStatus }) {
  return <span className={`badge ${status}`}>{LABEL[status]}</span>;
}
