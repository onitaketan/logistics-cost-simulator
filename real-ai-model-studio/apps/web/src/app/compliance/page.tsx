"use client";

// Compliance Check screen (docs/02 §8): three columns — project requirements,
// model permissions, judgement result. The judgement is fetched from the backend
// engine; the UI only displays it and shows the reasons. Project/model are picked
// from dropdowns (no raw UUIDs). The UI carries NO compliance logic.

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import type { ComplianceResult, Model, Project } from "@rams/shared-types";

export default function CompliancePage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [models, setModels] = useState<Model[]>([]);
  const [projectId, setProjectId] = useState("");
  const [modelId, setModelId] = useState("");
  const [prompt, setPrompt] = useState("");
  const [result, setResult] = useState<ComplianceResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.listProjects().then(setProjects).catch((e) => setError((e as Error).message));
    api.listModels().then(setModels).catch((e) => setError((e as Error).message));
  }, []);

  // Reset the judgement whenever the selection changes — a stale verdict must not
  // linger against a different project/model pair.
  function pickProject(v: string) {
    setProjectId(v);
    setResult(null);
  }
  function pickModel(v: string) {
    setModelId(v);
    setResult(null);
  }

  const project = projects.find((p) => p.id === projectId);
  const model = models.find((m) => m.id === modelId);

  async function check() {
    setError(null);
    setBusy(true);
    try {
      setResult(await api.runComplianceCheck(projectId, modelId, prompt || undefined));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h2>Compliance Check</h2>
      <div className="card">
        <div className="cols-3" style={{ gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <label className="field">
            <span>案件</span>
            <select value={projectId} onChange={(e) => pickProject(e.target.value)}>
              <option value="">選択してください</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.project_name}
                  {p.client_name ? `（${p.client_name}）` : ""}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>モデル</span>
            <select value={modelId} onChange={(e) => pickModel(e.target.value)}>
              <option value="">選択してください</option>
              {models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.stage_name}
                  {m.adult_verified ? "" : "（未成人確認）"}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div style={{ margin: "8px 0" }}>
          <textarea
            placeholder="生成プロンプト（禁止/要注意語句をスクリーニング）"
            value={prompt}
            onChange={(e) => {
              setPrompt(e.target.value);
              setResult(null);
            }}
            style={{ width: "100%", padding: 8, minHeight: 60 }}
          />
        </div>
        <button onClick={check} disabled={busy || !projectId || !modelId}>
          {busy ? "判定中…" : "判定する"}
        </button>
        {model && !model.adult_verified && (
          <p className="muted" style={{ fontSize: 12, marginBottom: 0 }}>
            ※ このモデルは未成人確認です。バックエンドが生成不可を返します。
          </p>
        )}
      </div>

      {error && <p className="error">{error}</p>}

      {result && (
        <div className="cols-3">
          <div className="card">
            <h3>案件要件</h3>
            {project ? (
              <>
                <p>案件: {project.project_name}</p>
                <p>クライアント: {project.client_name ?? "—"}</p>
                <p>商品カテゴリ: {project.product_category ?? "—"}</p>
                <p>ステータス: {project.project_status}</p>
              </>
            ) : (
              <p className="muted">—</p>
            )}
          </div>
          <div className="card">
            <h3>モデル許諾</h3>
            {model ? (
              <>
                <p>芸名: {model.stage_name}</p>
                <p>事務所: {model.agency_name ?? "—"}</p>
                <p>
                  成人確認:{" "}
                  {model.adult_verified ? (
                    <span className="badge ok">確認済</span>
                  ) : (
                    <span className="badge ng">未確認</span>
                  )}
                </p>
              </>
            ) : (
              <p className="muted">—</p>
            )}
          </div>
          <div className="card">
            <h3>判定結果</h3>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <StatusBadge status={result.check_status} />
              <strong>risk: {result.risk_level}</strong>
            </div>
            <p>{result.check_summary}</p>
            {result.required_approvals.length > 0 && (
              <p>必要承認: {result.required_approvals.join(" ・ ")}</p>
            )}
            {result.compliance_check_id && (
              <p className="muted" style={{ fontSize: 12 }}>
                compliance_check_id: {result.compliance_check_id}（生成APIに必須）
              </p>
            )}
          </div>
        </div>
      )}

      {result && result.violations.length > 0 && (
        <div className="card">
          <h3>違反・要注意項目</h3>
          <table>
            <thead>
              <tr>
                <th>項目</th>
                <th>判定</th>
                <th>理由</th>
              </tr>
            </thead>
            <tbody>
              {result.violations.map((v, i) => (
                <tr key={i}>
                  <td>{v.field}</td>
                  <td>{v.result}</td>
                  <td>{v.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
