"use client";

// Output Compare (P1-005, docs/01 §3 screen #12 "Image Compare & Revise"). Pick a
// project → its generations, then render that generation's outputs side by side in a
// grid so a reviewer can compare candidates at a glance, adjust status, and kick off
// a revision. Uses ONLY existing endpoints — the UI carries NO compliance/approval
// logic; the backend re-gates every action.

import { useEffect, useState } from "react";
import { api, resolveFileUrl } from "@/lib/api";
import type { OutputStatus, Project } from "@rams/shared-types";
import type { GenerationSummary, Output } from "@/types";

// Selection statuses only — 'approved'/'delivered' are granted elsewhere and the
// backend rejects them here too.
const OUTPUT_STATUSES: OutputStatus[] = ["candidate", "selected", "rejected"];
const COLUMN_OPTIONS = [2, 4] as const;

export default function ComparePage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [generations, setGenerations] = useState<GenerationSummary[]>([]);
  const [genId, setGenId] = useState("");
  const [outputs, setOutputs] = useState<Output[]>([]);
  const [columns, setColumns] = useState<number>(2);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listProjects().then(setProjects).catch((e) => setError((e as Error).message));
  }, []);

  async function pickProject(v: string) {
    setProjectId(v);
    setGenId("");
    setGenerations([]);
    setOutputs([]);
    setError(null);
    if (!v) return;
    try {
      setGenerations(await api.listGenerations(v));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function pickGeneration(v: string) {
    setGenId(v);
    setOutputs([]);
    setError(null);
    if (!v) return;
    try {
      setOutputs(await api.listOutputs(v));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div>
      <h2>出力比較</h2>
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
            <span>生成ジョブ</span>
            <select
              value={genId}
              onChange={(e) => pickGeneration(e.target.value)}
              disabled={!projectId}
            >
              <option value="">選択してください</option>
              {generations.map((g) => (
                <option key={g.id} value={g.id}>
                  {(g.generated_at ?? g.id).slice(0, 19)} — {g.status}（{g.output_count}枚）
                </option>
              ))}
            </select>
          </label>
        </div>
        {projectId && generations.length === 0 && (
          <p className="muted" style={{ marginBottom: 0 }}>
            この案件には生成ジョブがありません。
          </p>
        )}
        {outputs.length > 0 && (
          <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 4 }}>
            <span className="muted" style={{ fontSize: 12 }}>表示列数</span>
            {COLUMN_OPTIONS.map((c) => (
              <button
                key={c}
                className={`small ${columns === c ? "" : "ghost"}`.trim()}
                onClick={() => setColumns(c)}
              >
                {c}列
              </button>
            ))}
          </div>
        )}
      </div>
      {error && <p className="error">{error}</p>}

      {outputs.length > 0 && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`,
            gap: 12,
          }}
        >
          {outputs.map((o) => (
            <OutputCompareCell key={o.id} output={o} onError={setError} />
          ))}
        </div>
      )}
      {genId && outputs.length === 0 && !error && (
        <p className="muted">この生成ジョブには出力がありません。</p>
      )}
      {!genId && !error && (
        <p className="muted">案件と生成ジョブを選択して出力を読み込んでください。</p>
      )}
    </div>
  );
}

function OutputCompareCell({
  output,
  onError,
}: {
  output: Output;
  onError: (m: string) => void;
}) {
  const [status, setStatus] = useState<OutputStatus>(output.output_status);
  const [currentStatus, setCurrentStatus] = useState<OutputStatus>(output.output_status);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  const [revisePrompt, setRevisePrompt] = useState("");
  const [reviseBusy, setReviseBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    // Signed, short-lived, audited preview so the reviewer can SEE the candidate
    // (mock outputs return null and keep the placeholder box).
    api
      .getOutputPreview(output.id)
      .then((r) => setPreviewUrl(r.preview_url ? resolveFileUrl(r.preview_url) : null))
      .catch(() => setPreviewUrl(null));
  }, [output.id]);

  async function applyStatus() {
    onError("");
    try {
      const updated = await api.setOutputStatus(output.id, status);
      setCurrentStatus(updated.output_status);
      setNotice("ステータスを更新しました。");
    } catch (e) {
      onError((e as Error).message);
    }
  }

  return (
    <div className="card" style={{ margin: 0 }}>
      <div style={{ textAlign: "center" }}>
        {previewUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={previewUrl} alt="生成画像プレビュー" className="thumb" />
        ) : (
          <div className="thumb" />
        )}
        <div className="muted" style={{ fontSize: 11 }}>
          {output.width ?? "?"}×{output.height ?? "?"}
        </div>
      </div>

      <p style={{ margin: "8px 0", fontSize: 13 }}>
        現状態: <span className="badge neutral">{currentStatus}</span>
      </p>

      {/* Quick status change */}
      <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 10 }}>
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value as OutputStatus)}
          style={{ flex: 1 }}
        >
          {OUTPUT_STATUSES.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <button className="small" onClick={applyStatus}>更新</button>
      </div>

      {/* Revision generation: new job reusing the parent's compliance check — the
          backend re-gates it (request-time / DB trigger / worker). */}
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <input
          placeholder="修正指示（例: 背景を高級感のある照明に）"
          value={revisePrompt}
          onChange={(e) => setRevisePrompt(e.target.value)}
          style={{ padding: 6, flex: 1, minWidth: 140 }}
        />
        <button
          className="small ghost"
          disabled={reviseBusy || !revisePrompt.trim()}
          onClick={async () => {
            onError("");
            setReviseBusy(true);
            try {
              const r = await api.reviseOutput(output.id, { revision_prompt: revisePrompt });
              setNotice(`修正生成を開始しました（generation: ${String(r.generation_id ?? "").slice(0, 8)}…）。`);
              setRevisePrompt("");
            } catch (e) {
              onError((e as Error).message);
            } finally {
              setReviseBusy(false);
            }
          }}
        >
          {reviseBusy ? "生成中…" : "修正生成"}
        </button>
      </div>

      {notice && <p style={{ color: "var(--ok)", fontSize: 12 }}>{notice}</p>}
    </div>
  );
}
