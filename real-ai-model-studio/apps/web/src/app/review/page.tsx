"use client";

// Review & Approval (docs/02 §10). Pick a project → its generations → an output.
// Per output: set status, add a review, add an approval, and DISPLAY existing
// reviews/approvals. The approvals call returns required_approvals +
// missing_approvals — we surface those so the user sees "まだ全承認が揃っていない"
// until the backend says it is fully approved. The UI carries NO approval logic.

import { useEffect, useState } from "react";
import { api, resolveFileUrl } from "@/lib/api";
import type { ApprovalLevel, OutputStatus, Project } from "@rams/shared-types";
import type {
  ApprovalItem,
  ApprovalResult,
  GenerationSummary,
  Output,
  ReviewItem,
} from "@/types";

// Selection statuses only — 'approved' is granted exclusively by the approval
// gate and 'delivered' by delivery. The backend rejects them here too.
const OUTPUT_STATUSES: OutputStatus[] = ["candidate", "selected", "rejected"];
const APPROVAL_LEVELS: ApprovalLevel[] = ["internal", "legal", "agency", "person", "admin"];
const DECISIONS = ["approved", "conditional", "rejected"];

export default function ReviewPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("");
  const [generations, setGenerations] = useState<GenerationSummary[]>([]);
  const [genId, setGenId] = useState("");
  const [outputs, setOutputs] = useState<Output[]>([]);
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
      <h2>Review &amp; Approval</h2>
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
      </div>
      {error && <p className="error">{error}</p>}

      {outputs.map((o) => (
        <OutputReviewCard key={o.id} output={o} onError={setError} />
      ))}
      {genId && outputs.length === 0 && !error && (
        <p className="muted">この生成ジョブには出力がありません。</p>
      )}
      {!genId && !error && (
        <p className="muted">案件と生成ジョブを選択して出力を読み込んでください。</p>
      )}
    </div>
  );
}

function OutputReviewCard({
  output,
  onError,
}: {
  output: Output;
  onError: (m: string) => void;
}) {
  const [status, setStatus] = useState<OutputStatus>(output.output_status);
  const [currentStatus, setCurrentStatus] = useState<OutputStatus>(output.output_status);

  const [reviewType, setReviewType] = useState("internal");
  const [reviewDecision, setReviewDecision] = useState("approved");
  const [reviewComment, setReviewComment] = useState("");

  const [approvalLevel, setApprovalLevel] = useState<ApprovalLevel>("internal");
  const [approvalDecision, setApprovalDecision] = useState("approved");
  const [approvalComment, setApprovalComment] = useState("");
  const [approvalResult, setApprovalResult] = useState<ApprovalResult | null>(null);

  const [reviews, setReviews] = useState<ReviewItem[]>([]);
  const [approvals, setApprovals] = useState<ApprovalItem[]>([]);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  const [revisePrompt, setRevisePrompt] = useState("");
  const [reviseBusy, setReviseBusy] = useState(false);

  const [notice, setNotice] = useState<string | null>(null);

  function loadReviews() {
    api.listOutputReviews(output.id).then(setReviews).catch(() => setReviews([]));
  }
  function loadApprovals() {
    api.listOutputApprovals(output.id).then(setApprovals).catch(() => setApprovals([]));
  }

  useEffect(() => {
    loadReviews();
    loadApprovals();
    // Signed, short-lived, audited preview so the reviewer can SEE the candidate
    // (mock outputs return null and keep the placeholder box).
    api
      .getOutputPreview(output.id)
      .then((r) => setPreviewUrl(r.preview_url ? resolveFileUrl(r.preview_url) : null))
      .catch(() => setPreviewUrl(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
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

  async function submitReview() {
    onError("");
    try {
      await api.addReview(output.id, reviewType, reviewDecision, reviewComment || undefined);
      setNotice("レビューを登録しました。");
      setReviewComment("");
      loadReviews();
    } catch (e) {
      onError((e as Error).message);
    }
  }

  async function submitApproval() {
    onError("");
    try {
      const res = await api.addApproval(
        output.id,
        approvalLevel,
        approvalDecision,
        approvalComment || undefined,
      );
      setApprovalResult(res);
      setCurrentStatus(res.output_status);
      setApprovalComment("");
      loadApprovals();
    } catch (e) {
      onError((e as Error).message);
    }
  }

  return (
    <div className="card">
      <div style={{ display: "flex", gap: 16 }}>
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
        <div style={{ flex: 1 }}>
          <p style={{ marginTop: 0 }}>
            output: {output.id} — 現状態:{" "}
            <span className="badge neutral">{currentStatus}</span>
          </p>

          {/* Set status */}
          <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 10 }}>
            <select value={status} onChange={(e) => setStatus(e.target.value as OutputStatus)}>
              {OUTPUT_STATUSES.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
            <button className="small" onClick={applyStatus}>状態を更新</button>
          </div>

          {/* Add review */}
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 10 }}>
            <select value={reviewType} onChange={(e) => setReviewType(e.target.value)}>
              <option value="internal">internal</option>
              <option value="legal">legal</option>
            </select>
            <select value={reviewDecision} onChange={(e) => setReviewDecision(e.target.value)}>
              {DECISIONS.map((d) => (
                <option key={d} value={d}>{d}</option>
              ))}
            </select>
            <input placeholder="コメント" value={reviewComment}
              onChange={(e) => setReviewComment(e.target.value)} style={{ padding: 6, flex: 1, minWidth: 160 }} />
            <button className="small" onClick={submitReview}>レビュー追加</button>
          </div>

          {/* Add approval */}
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <select value={approvalLevel} onChange={(e) => setApprovalLevel(e.target.value as ApprovalLevel)}>
              {APPROVAL_LEVELS.map((l) => (
                <option key={l} value={l}>{l}</option>
              ))}
            </select>
            <select value={approvalDecision} onChange={(e) => setApprovalDecision(e.target.value)}>
              {DECISIONS.map((d) => (
                <option key={d} value={d}>{d}</option>
              ))}
            </select>
            <input placeholder="コメント" value={approvalComment}
              onChange={(e) => setApprovalComment(e.target.value)} style={{ padding: 6, flex: 1, minWidth: 160 }} />
            <button className="small" onClick={submitApproval}>承認追加</button>
          </div>

          {approvalResult && (
            <div style={{ marginTop: 10, fontSize: 13 }}>
              <p style={{ margin: "4px 0" }}>
                出力状態: <span className="badge neutral">{approvalResult.output_status}</span>
              </p>
              <p style={{ margin: "4px 0" }}>
                必要承認: {approvalResult.required_approvals.join(" ・ ") || "—"}
              </p>
              {approvalResult.missing_approvals.length > 0 ? (
                <p className="error" style={{ margin: "4px 0" }}>
                  未承認: {approvalResult.missing_approvals.join(" ・ ")}（全承認が揃っていません）
                </p>
              ) : (
                <p style={{ color: "var(--ok)", margin: "4px 0" }}>全承認が揃いました。</p>
              )}
            </div>
          )}

          {/* Existing reviews / approvals */}
          <div className="cols-3" style={{ gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 12 }}>
            <div>
              <p className="muted" style={{ fontSize: 12, margin: "0 0 4px" }}>レビュー履歴</p>
              {reviews.length === 0 ? (
                <p className="muted" style={{ fontSize: 12 }}>—</p>
              ) : (
                <table>
                  <thead><tr><th>種別</th><th>判定</th><th>コメント</th></tr></thead>
                  <tbody>
                    {reviews.map((r) => (
                      <tr key={r.id}>
                        <td>{r.review_type}</td>
                        <td>{r.status}</td>
                        <td>{r.comment ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
            <div>
              <p className="muted" style={{ fontSize: 12, margin: "0 0 4px" }}>承認履歴</p>
              {approvals.length === 0 ? (
                <p className="muted" style={{ fontSize: 12 }}>—</p>
              ) : (
                <table>
                  <thead><tr><th>レベル</th><th>判定</th><th>コメント</th></tr></thead>
                  <tbody>
                    {approvals.map((a) => (
                      <tr key={a.id}>
                        <td>{a.approval_level}</td>
                        <td>{a.approval_status}</td>
                        <td>{a.approval_comment ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>

          {/* Revision generation (P1-006): new job reusing the parent's compliance
              check — the backend re-gates it (request-time / DB trigger / worker). */}
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginTop: 12 }}>
            <input
              placeholder="修正指示（例: 背景を高級感のある照明に。人物は変更しない）"
              value={revisePrompt}
              onChange={(e) => setRevisePrompt(e.target.value)}
              style={{ padding: 6, flex: 1, minWidth: 220 }}
            />
            <button
              className="small ghost"
              disabled={reviseBusy || !revisePrompt.trim()}
              onClick={async () => {
                onError("");
                setReviseBusy(true);
                try {
                  const r = await api.reviseOutput(output.id, { revision_prompt: revisePrompt });
                  setNotice(`修正生成を開始しました（generation: ${String(r.generation_id ?? "").slice(0, 8)}… / ${r.status ?? ""}）。生成ジョブ一覧を再選択すると確認できます。`);
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
      </div>
    </div>
  );
}
