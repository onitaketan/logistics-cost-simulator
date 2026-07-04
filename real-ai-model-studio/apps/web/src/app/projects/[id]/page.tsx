"use client";

// Project detail (docs/02 §7-8). Shows the project, lets the user add usage/
// expression requirements, assign a model, and run the compliance check. The
// judgement comes entirely from the backend engine; the UI only displays it.

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import {
  MEDIA_SCOPE,
  REGION_SCOPE,
  EXPOSURE_LEVELS,
} from "@rams/shared-types";
import type { ComplianceResult, Model, Project } from "@rams/shared-types";

export default function ProjectDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;

  const [project, setProject] = useState<Project | null>(null);
  const [models, setModels] = useState<Model[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // requirements form
  const [media, setMedia] = useState<string>(MEDIA_SCOPE[0]);
  const [region, setRegion] = useState<string>(REGION_SCOPE[0]);
  const [exposure, setExposure] = useState<number>(0);
  const [reqNote, setReqNote] = useState("");

  // model assignment + compliance
  const [modelId, setModelId] = useState("");
  const [usageRole, setUsageRole] = useState("main");
  const [prompt, setPrompt] = useState("");
  const [training, setTraining] = useState(false);
  const [result, setResult] = useState<ComplianceResult | null>(null);

  const loadProject = useCallback(() => {
    api.getProject(id).then(setProject).catch((e) => setError((e as Error).message));
  }, [id]);

  useEffect(() => {
    loadProject();
    api.listModels().then(setModels).catch(() => setModels([]));
  }, [id, loadProject]);

  async function addRequirements(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setNotice(null);
    try {
      await api.addRequirements(id, {
        // backend RequirementCreate expects arrays for media/region
        media: [media],
        region: [region],
        exposure_level: exposure,
        background_description: reqNote || undefined,
      });
      setNotice("要件を登録しました。");
      loadProject();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function assign() {
    setError(null);
    setNotice(null);
    try {
      await api.assignModel(id, modelId, usageRole);
      setNotice("モデルを紐づけました。");
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function runCheck() {
    setError(null);
    try {
      setResult(await api.runComplianceCheck(id, modelId, prompt || undefined, training));
    } catch (err) {
      setError((err as Error).message);
    }
  }

  if (!project) {
    return (
      <div>
        <Link href="/projects">← Projects</Link>
        {error ? <p className="error">{error}</p> : <p className="muted">読み込み中…</p>}
      </div>
    );
  }

  return (
    <div>
      <Link href="/projects">← Projects</Link>
      <h2>{project.project_name}</h2>
      {error && <p className="error">{error}</p>}
      {notice && <p style={{ color: "var(--ok)" }}>{notice}</p>}

      <div className="cols-3">
        {/* Left: project + requirements */}
        <div>
          <div className="card">
            <h3>案件情報</h3>
            <p>クライアント: {project.client_name ?? "—"}</p>
            <p>カテゴリ: {project.product_category ?? "—"}</p>
            <p>状態: {project.project_status}</p>
            <p>リスク: {project.risk_level ?? "—"}</p>
            <p>納期: {project.deadline ?? "—"}</p>
          </div>

          <div className="card">
            <h3>要件を追加</h3>
            <form onSubmit={addRequirements}>
              <label className="field">
                <span>媒体</span>
                <select value={media} onChange={(e) => setMedia(e.target.value)}>
                  {MEDIA_SCOPE.map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>地域</span>
                <select value={region} onChange={(e) => setRegion(e.target.value)}>
                  {REGION_SCOPE.map((r) => (
                    <option key={r} value={r}>{r}</option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>露出レベル</span>
                <select
                  value={exposure}
                  onChange={(e) => setExposure(Number(e.target.value))}
                >
                  {EXPOSURE_LEVELS.map((lv) => (
                    <option key={lv} value={lv}>{lv}</option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>備考</span>
                <textarea value={reqNote} onChange={(e) => setReqNote(e.target.value)} />
              </label>
              <button type="submit">要件を登録</button>
            </form>
          </div>
        </div>

        {/* Center: model assignment */}
        <div>
          <div className="card">
            <h3>モデル紐づけ</h3>
            <label className="field">
              <span>モデル</span>
              <select value={modelId} onChange={(e) => setModelId(e.target.value)}>
                <option value="">選択してください</option>
                {models.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.stage_name}
                    {m.adult_verified ? "" : "（未成人確認）"}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>役割</span>
              <select value={usageRole} onChange={(e) => setUsageRole(e.target.value)}>
                <option value="main">main</option>
                <option value="sub">sub</option>
              </select>
            </label>
            <button onClick={assign} disabled={!modelId}>紐づける</button>
          </div>

          <div className="card">
            <h3>コンプライアンス判定</h3>
            <label className="field">
              <span>プロンプト</span>
              <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} />
            </label>
            <label className="field" style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <input
                type="checkbox"
                checked={training}
                onChange={(e) => setTraining(e.target.checked)}
                style={{ width: "auto" }}
              />
              <span style={{ margin: 0 }}>AI学習を要求する</span>
            </label>
            <button onClick={runCheck} disabled={!modelId}>判定する</button>
          </div>
        </div>

        {/* Right: judgement */}
        <div>
          <div className="card">
            <h3>判定結果</h3>
            {result ? (
              <>
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
                    <thead>
                      <tr><th>項目</th><th>判定</th><th>理由</th></tr>
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
                )}
                {result.compliance_check_id && (
                  <p className="muted" style={{ fontSize: 12 }}>
                    compliance_check_id: {result.compliance_check_id}
                  </p>
                )}
              </>
            ) : (
              <p className="muted">モデルを選び、判定を実行してください。</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
