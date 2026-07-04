"use client";

// Generation Studio (docs/02 §9). The Generate button is DISABLED unless a
// compliance check id exists with status ok/conditional. This is a UI courtesy
// only — the backend re-validates and the DB trigger enforces regardless.

import { useState } from "react";
import { api } from "@/lib/api";
import type { ComplianceResult } from "@rams/shared-types";

export default function GenerationStudio() {
  const [projectId, setProjectId] = useState("");
  const [modelId, setModelId] = useState("");
  const [prompt, setPrompt] = useState("");
  const [check, setCheck] = useState<ComplianceResult | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const canGenerate =
    !!check?.compliance_check_id &&
    (check.check_status === "ok" || check.check_status === "conditional");

  async function runCheck() {
    setError(null);
    try {
      setCheck(await api.runComplianceCheck(projectId, modelId, prompt));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function generate() {
    setError(null);
    try {
      const res = await api.createGeneration({
        project_id: projectId,
        model_id: modelId,
        compliance_check_id: check!.compliance_check_id,
        prompt_text: prompt,
        generation_params: { output_count: 4, width: 1024, height: 1280 },
      });
      setStatus(`generation ${res.generation_id}: ${res.status}`);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 16 }}>
      <div>
        <h2>Generation Studio</h2>
        <div className="card">
          <input placeholder="project_id" value={projectId} onChange={(e) => setProjectId(e.target.value)}
            style={{ padding: 8, marginRight: 8, width: 240 }} />
          <input placeholder="model_id" value={modelId} onChange={(e) => setModelId(e.target.value)}
            style={{ padding: 8, width: 240 }} />
          <textarea placeholder="プロンプト（許諾範囲内の広告表現）" value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            style={{ width: "100%", padding: 8, minHeight: 100, marginTop: 8 }} />
          <div style={{ marginTop: 8, display: "flex", gap: 8 }}>
            <button onClick={runCheck}>コンプライアンス判定</button>
            <button onClick={generate} disabled={!canGenerate}>生成する</button>
          </div>
        </div>
        {status && <div className="card">{status}</div>}
        {error && <p style={{ color: "var(--ng)" }}>{error}</p>}
      </div>

      <aside className="card">
        <h3>判定サマリ</h3>
        {check ? (
          <>
            <p>ステータス: <span className={`badge ${check.check_status}`}>{check.check_status}</span></p>
            <p>{check.check_summary}</p>
          </>
        ) : (
          <p style={{ color: "#889" }}>先に判定を実行してください。判定を通過しない限り生成できません。</p>
        )}
      </aside>
    </div>
  );
}
