"use client";

// Compliance Check screen (docs/02 §8): three columns — project requirements,
// model permissions, judgement result. The judgement is fetched from the backend
// engine; the UI only displays it and shows the reasons.

import { useState } from "react";
import { api } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import type { ComplianceResult } from "@rams/shared-types";

export default function CompliancePage() {
  const [projectId, setProjectId] = useState("");
  const [modelId, setModelId] = useState("");
  const [prompt, setPrompt] = useState("");
  const [result, setResult] = useState<ComplianceResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function check() {
    setError(null);
    try {
      setResult(await api.runComplianceCheck(projectId, modelId, prompt));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div>
      <h2>Compliance Check</h2>
      <div className="card">
        <input placeholder="project_id" value={projectId} onChange={(e) => setProjectId(e.target.value)}
          style={{ padding: 8, marginRight: 8, width: 320 }} />
        <input placeholder="model_id" value={modelId} onChange={(e) => setModelId(e.target.value)}
          style={{ padding: 8, marginRight: 8, width: 320 }} />
        <div style={{ margin: "8px 0" }}>
          <textarea placeholder="生成プロンプト（禁止/要注意語句をスクリーニング）" value={prompt}
            onChange={(e) => setPrompt(e.target.value)} style={{ width: "100%", padding: 8, minHeight: 60 }} />
        </div>
        <button onClick={check}>判定する</button>
      </div>

      {error && <p style={{ color: "var(--ng)" }}>{error}</p>}

      {result && (
        <div className="card">
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <StatusBadge status={result.check_status} />
            <strong>risk: {result.risk_level}</strong>
          </div>
          <p>{result.check_summary}</p>
          {result.required_approvals.length > 0 && (
            <p>必要承認: {result.required_approvals.join(" ・ ")}</p>
          )}
          {result.violations.length > 0 && (
            <table>
              <thead><tr><th>項目</th><th>判定</th><th>理由</th></tr></thead>
              <tbody>
                {result.violations.map((v, i) => (
                  <tr key={i}><td>{v.field}</td><td>{v.result}</td><td>{v.message}</td></tr>
                ))}
              </tbody>
            </table>
          )}
          {result.compliance_check_id && (
            <p style={{ color: "#889", fontSize: 12 }}>
              compliance_check_id: {result.compliance_check_id}（生成APIに必須）
            </p>
          )}
        </div>
      )}
    </div>
  );
}
